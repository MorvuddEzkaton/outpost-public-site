#!/usr/bin/env python3
"""Guard unique primary SEO metadata across all public sitemap pages."""

from __future__ import annotations

from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
ORIGIN = "https://outpost.com.ua"


class SeoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.h1_parts: list[list[str]] = []
        self.description_values: list[str] = []
        self.meta: dict[str, list[str]] = defaultdict(list)
        self.canonicals: list[str] = []
        self.json_ld_scripts: list[str] = []
        self.details_items: list[tuple[str, str]] = []
        self._json_ld_current: list[str] | None = None
        self._in_title = False
        self._h1_depth = 0
        self._details_depth = 0
        self._summary_depth = 0
        self._details_summary_parts: list[str] = []
        self._details_body_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        data = {key.lower(): value for key, value in attrs}

        if tag == "script":
            script_type = (data.get("type") or "").strip().lower()
            if script_type == "application/ld+json":
                self._json_ld_current = []
                return
            self._skip_depth += 1
            return
        if tag in {"style", "template"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._h1_depth += 1
            self.h1_parts.append([])
        elif tag == "details":
            if self._details_depth == 0:
                self._details_summary_parts = []
                self._details_body_parts = []
            self._details_depth += 1
        elif tag == "summary" and self._details_depth:
            self._summary_depth += 1
        elif tag == "meta":
            name = (data.get("name") or "").strip().lower()
            prop = (data.get("property") or "").strip().lower()
            content = (data.get("content") or "").strip()
            if name:
                self.meta[name].append(content)
            if prop:
                self.meta[prop].append(content)
            if name == "description":
                self.description_values.append(content)
        elif tag == "link":
            rel = (data.get("rel") or "").strip().lower().split()
            if "canonical" in rel:
                self.canonicals.append((data.get("href") or "").strip())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script":
            if self._json_ld_current is not None:
                self.json_ld_scripts.append("".join(self._json_ld_current).strip())
                self._json_ld_current = None
                return
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if tag in {"style", "template"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return

        if tag == "title":
            self._in_title = False
        elif tag == "h1" and self._h1_depth:
            self._h1_depth -= 1
        elif tag == "summary" and self._summary_depth:
            self._summary_depth -= 1
        elif tag == "details" and self._details_depth:
            self._details_depth -= 1
            if self._details_depth == 0:
                summary = self.clean(self._details_summary_parts)
                body = self.clean(self._details_body_parts)
                if summary or body:
                    self.details_items.append((summary, body))

    def handle_data(self, data: str) -> None:
        if self._json_ld_current is not None:
            self._json_ld_current.append(data)
            return
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        if self._h1_depth and self.h1_parts:
            self.h1_parts[-1].append(data)
        if self._details_depth:
            if self._summary_depth:
                self._details_summary_parts.append(data)
            else:
                self._details_body_parts.append(data)

    @staticmethod
    def clean(parts: list[str]) -> str:
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    @property
    def title(self) -> str:
        return self.clean(self.title_parts)

    @property
    def h1_values(self) -> list[str]:
        return [self.clean(parts) for parts in self.h1_parts]


class VisibleBreadcrumbParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.trail_count = 0
        self.items: list[tuple[str | None, str]] = []
        self._trail_depth = 0
        self._active_tag: str | None = None
        self._active_href: str | None = None
        self._active_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        data = {key.lower(): (value or "") for key, value in attrs}

        if self._trail_depth:
            self._trail_depth += 1
            if self._trail_depth == 2 and tag in {"a", "span"}:
                self._active_tag = tag
                self._active_href = data.get("href") if tag == "a" else None
                self._active_parts = []
            return

        classes = set(data.get("class", "").split())
        if tag in {"div", "nav"} and classes.intersection({"crumbs", "breadcrumbs"}):
            self.trail_count += 1
            self._trail_depth = 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self._trail_depth:
            return

        if self._active_tag == tag and self._trail_depth == 2:
            text = re.sub(r"\s+", " ", " ".join(self._active_parts)).strip()
            if text and text != "/":
                self.items.append((self._active_href, text))
            self._active_tag = None
            self._active_href = None
            self._active_parts = []

        self._trail_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._trail_depth and self._active_tag is not None:
            self._active_parts.append(data)


def sitemap_routes(errors: list[str]) -> list[tuple[str, Path]]:
    try:
        root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        errors.append(f"site/sitemap.xml: cannot parse sitemap: {exc}")
        return []

    rows: list[tuple[str, Path]] = []
    for node in root:
        loc = next(
            (
                child.text.strip()
                for child in node
                if child.tag.rsplit("}", 1)[-1] == "loc" and child.text
            ),
            None,
        )
        if not loc:
            continue

        parsed = urlparse(loc)
        if parsed.scheme != "https" or parsed.netloc != "outpost.com.ua":
            errors.append(f"site/sitemap.xml: unexpected public origin in {loc!r}")
            continue

        route = parsed.path or "/"
        target = SITE / ("index.html" if route == "/" else route.strip("/") + ".html")
        rows.append((loc, target))

    if not rows:
        errors.append("site/sitemap.xml: no public pages found")
    return rows


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def guard_unique(
    label: str,
    values: list[tuple[str, str]],
    errors: list[str],
) -> None:
    owners: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for url, value in values:
        owners[normalized(value)].append((url, value))

    for group in owners.values():
        if len(group) <= 1:
            continue
        urls = ", ".join(item[0] for item in group)
        errors.append(f"duplicate {label} across sitemap pages: {group[0][1]!r} -> {urls}")


def main() -> int:
    errors: list[str] = []
    routes = sitemap_routes(errors)

    canonical_website: dict | None = None
    canonical_software: dict | None = None
    home_path = next((path for url, path in routes if url == f"{ORIGIN}/"), None)
    if home_path is not None and home_path.is_file():
        home_parser = SeoParser()
        home_parser.feed(home_path.read_text(encoding="utf-8"))
        home_parser.close()
        home_websites: list[dict] = []
        home_software: list[dict] = []
        for raw_json_ld in home_parser.json_ld_scripts:
            if not raw_json_ld:
                continue
            try:
                payload = json.loads(raw_json_ld)
            except json.JSONDecodeError:
                continue
            nodes = payload.get("@graph", [payload]) if isinstance(payload, dict) else []
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if node.get("@type") == "WebSite":
                    home_websites.append(node)
                elif node.get("@type") == "SoftwareApplication":
                    home_software.append(node)
        if len(home_websites) == 1:
            canonical_website = home_websites[0]
        if len(home_software) == 1:
            canonical_software = home_software[0]

    titles: list[tuple[str, str]] = []
    descriptions: list[tuple[str, str]] = []
    h1s: list[tuple[str, str]] = []

    for url, path in routes:
        if not path.is_file():
            errors.append(f"{url}: missing static target {path.relative_to(ROOT)}")
            continue

        text = path.read_text(encoding="utf-8")
        parser = SeoParser()
        parser.feed(text)
        parser.close()

        visible_breadcrumb = VisibleBreadcrumbParser()
        visible_breadcrumb.feed(text)
        visible_breadcrumb.close()

        if not parser.title:
            errors.append(f"{url}: missing non-empty <title>")
        else:
            titles.append((url, parser.title))

        if len(parser.description_values) != 1:
            errors.append(
                f"{url}: expected exactly one meta description, got {parser.description_values!r}"
            )
        elif not parser.description_values[0]:
            errors.append(f"{url}: meta description is empty")
        else:
            descriptions.append((url, parser.description_values[0]))

        h1_values = parser.h1_values
        if len(h1_values) != 1:
            errors.append(f"{url}: expected exactly one H1, got {h1_values!r}")
        elif not h1_values[0]:
            errors.append(f"{url}: H1 is empty")
        else:
            h1s.append((url, h1_values[0]))

        if parser.canonicals != [url]:
            errors.append(
                f"{url}: canonical must match sitemap URL exactly; got {parser.canonicals!r}"
            )

        og_titles = parser.meta.get("og:title", [])
        if og_titles != [parser.title]:
            errors.append(
                f"{url}: og:title must match <title> exactly; title={parser.title!r}, og:title={og_titles!r}"
            )

        expected_description = (
            parser.description_values[0] if len(parser.description_values) == 1 else None
        )
        og_descriptions = parser.meta.get("og:description", [])
        if expected_description is not None and og_descriptions != [expected_description]:
            errors.append(
                f"{url}: og:description must match meta description exactly; "
                f"description={expected_description!r}, og:description={og_descriptions!r}"
            )

        og_urls = parser.meta.get("og:url", [])
        if og_urls != [url]:
            errors.append(
                f"{url}: og:url must match sitemap/canonical URL exactly; got {og_urls!r}"
            )

        expected_robots = "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1"
        if parser.meta.get("robots", []) != [expected_robots]:
            errors.append(
                f"{url}: robots meta must be the public index/follow policy; "
                f"got {parser.meta.get('robots', [])!r}"
            )
        if parser.meta.get("og:type", []) != ["website"]:
            errors.append(f"{url}: og:type must be exactly 'website'")
        if parser.meta.get("og:locale", []) != ["uk_UA"]:
            errors.append(f"{url}: og:locale must be exactly 'uk_UA'")
        if parser.meta.get("og:site_name", []) != ["OutPOSt"]:
            errors.append(f"{url}: og:site_name must be exactly 'OutPOSt'")

        og_images = parser.meta.get("og:image", [])
        if len(og_images) != 1 or not re.fullmatch(
            r"https://outpost\.com\.ua/assets/[^\s]+", og_images[0] if og_images else ""
        ):
            errors.append(
                f"{url}: expected exactly one absolute production og:image under /assets; "
                f"got {og_images!r}"
            )

        image_widths = parser.meta.get("og:image:width", [])
        image_heights = parser.meta.get("og:image:height", [])
        if (
            len(image_widths) != 1
            or not image_widths[0].isdigit()
            or int(image_widths[0]) <= 0
            or len(image_heights) != 1
            or not image_heights[0].isdigit()
            or int(image_heights[0]) <= 0
        ):
            errors.append(
                f"{url}: og:image width/height must each be one positive integer; "
                f"got width={image_widths!r}, height={image_heights!r}"
            )

        image_alts = parser.meta.get("og:image:alt", [])
        if len(image_alts) != 1 or not image_alts[0].strip():
            errors.append(f"{url}: expected exactly one non-empty og:image:alt")

        if parser.meta.get("twitter:card", []) != ["summary_large_image"]:
            errors.append(f"{url}: twitter:card must be exactly 'summary_large_image'")

        web_pages: list[dict] = []
        breadcrumbs: list[dict] = []
        web_sites: list[dict] = []
        software_apps: list[dict] = []
        faq_pages: list[dict] = []
        for raw_json_ld in parser.json_ld_scripts:
            if not raw_json_ld:
                continue
            try:
                payload = json.loads(raw_json_ld)
            except json.JSONDecodeError as exc:
                errors.append(f"{url}: invalid JSON-LD in SEO parity guard: {exc}")
                continue

            nodes = payload.get("@graph", [payload]) if isinstance(payload, dict) else []
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if node.get("@type") == "WebPage":
                    web_pages.append(node)
                elif node.get("@type") == "BreadcrumbList":
                    breadcrumbs.append(node)
                elif node.get("@type") == "WebSite":
                    web_sites.append(node)
                elif node.get("@type") == "SoftwareApplication":
                    software_apps.append(node)
                elif node.get("@type") == "FAQPage":
                    faq_pages.append(node)

        is_home = url == f"{ORIGIN}/"
        if is_home:
            if len(web_pages) > 1:
                errors.append(f"{url}: expected at most one JSON-LD WebPage node, got {len(web_pages)}")
            if breadcrumbs:
                errors.append(f"{url}: homepage must not expose BreadcrumbList schema")
            if len(web_sites) != 1:
                errors.append(f"{url}: homepage must expose exactly one JSON-LD WebSite node, got {len(web_sites)}")
            if len(software_apps) != 1:
                errors.append(
                    f"{url}: homepage must expose exactly one JSON-LD SoftwareApplication node, "
                    f"got {len(software_apps)}"
                )
        else:
            if len(web_pages) != 1:
                errors.append(f"{url}: expected exactly one JSON-LD WebPage node, got {len(web_pages)}")
            if len(breadcrumbs) != 1:
                errors.append(f"{url}: expected exactly one JSON-LD BreadcrumbList node, got {len(breadcrumbs)}")

        if is_home and len(web_sites) == 1:
            web_site = web_sites[0]
            if web_site.get("@id") != f"{ORIGIN}/#website" or web_site.get("url") != f"{ORIGIN}/":
                errors.append(
                    f"{url}: homepage WebSite must use canonical @id/url "
                    f"{ORIGIN}/#website and {ORIGIN}/"
                )
            if web_site.get("inLanguage") != "uk":
                errors.append(
                    f"{url}: homepage WebSite.inLanguage must be 'uk'; "
                    f"got {web_site.get('inLanguage')!r}"
                )

        if is_home and len(software_apps) == 1:
            software = software_apps[0]
            if software.get("@id") != f"{ORIGIN}/#software" or software.get("url") != f"{ORIGIN}/":
                errors.append(
                    f"{url}: homepage SoftwareApplication must use canonical @id/url "
                    f"{ORIGIN}/#software and {ORIGIN}/"
                )
            if software.get("inLanguage") != "uk":
                errors.append(
                    f"{url}: homepage SoftwareApplication.inLanguage must be 'uk'; "
                    f"got {software.get('inLanguage')!r}"
                )
            if len(og_images) == 1 and software.get("image") != og_images[0]:
                errors.append(
                    f"{url}: homepage SoftwareApplication.image must match og:image exactly; "
                    f"og:image={og_images[0]!r}, SoftwareApplication.image={software.get('image')!r}"
                )

        if not is_home:
            for web_site in web_sites:
                if web_site.get("@id") != f"{ORIGIN}/#website" or web_site.get("url") != f"{ORIGIN}/":
                    errors.append(
                        f"{url}: embedded WebSite must reuse canonical homepage entity "
                        f"{ORIGIN}/#website"
                    )
                elif canonical_website is not None and web_site != canonical_website:
                    errors.append(
                        f"{url}: embedded WebSite #website differs semantically from homepage entity"
                    )
            for software in software_apps:
                if software.get("@id") != f"{ORIGIN}/#software" or software.get("url") != f"{ORIGIN}/":
                    errors.append(
                        f"{url}: embedded SoftwareApplication must reuse canonical product entity "
                        f"{ORIGIN}/#software"
                    )
                elif canonical_software is not None and software != canonical_software:
                    errors.append(
                        f"{url}: embedded SoftwareApplication #software differs semantically "
                        "from homepage entity"
                    )

        if len(web_pages) == 1:
            web_page = web_pages[0]
            if web_page.get("inLanguage") != "uk":
                errors.append(
                    f"{url}: JSON-LD WebPage.inLanguage must be 'uk'; "
                    f"got {web_page.get('inLanguage')!r}"
                )
            if web_page.get("url") != url:
                errors.append(
                    f"{url}: JSON-LD WebPage.url must match sitemap/canonical URL exactly; "
                    f"got {web_page.get('url')!r}"
                )
            if web_page.get("name") != parser.title:
                errors.append(
                    f"{url}: JSON-LD WebPage.name must match <title> exactly; "
                    f"title={parser.title!r}, WebPage.name={web_page.get('name')!r}"
                )
            if expected_description is not None and web_page.get("description") != expected_description:
                errors.append(
                    f"{url}: JSON-LD WebPage.description must match meta description exactly; "
                    f"description={expected_description!r}, "
                    f"WebPage.description={web_page.get('description')!r}"
                )

            if not is_home:
                expected_webpage_id = f"{url}#webpage"
                if web_page.get("@id") != expected_webpage_id:
                    errors.append(
                        f"{url}: JSON-LD WebPage @id must be {expected_webpage_id!r}; "
                        f"got {web_page.get('@id')!r}"
                    )

                expected_website_id = f"{ORIGIN}/#website"
                is_part_of = web_page.get("isPartOf")
                actual_website_id = is_part_of.get("@id") if isinstance(is_part_of, dict) else None
                if actual_website_id != expected_website_id:
                    errors.append(
                        f"{url}: JSON-LD WebPage.isPartOf must reference "
                        f"{expected_website_id!r}; got {actual_website_id!r}"
                    )

                expected_software_id = f"{ORIGIN}/#software"
                about = web_page.get("about")
                actual_software_id = about.get("@id") if isinstance(about, dict) else None
                if actual_software_id != expected_software_id:
                    errors.append(
                        f"{url}: JSON-LD WebPage.about must reference "
                        f"{expected_software_id!r}; got {actual_software_id!r}"
                    )

                expected_breadcrumb_id = f"{url}#breadcrumb"
                breadcrumb_ref = web_page.get("breadcrumb")
                actual_breadcrumb_ref = (
                    breadcrumb_ref.get("@id") if isinstance(breadcrumb_ref, dict) else None
                )
                if actual_breadcrumb_ref != expected_breadcrumb_id:
                    errors.append(
                        f"{url}: JSON-LD WebPage.breadcrumb must reference "
                        f"{expected_breadcrumb_id!r}; got {actual_breadcrumb_ref!r}"
                    )

        if len(faq_pages) > 1:
            errors.append(f"{url}: expected at most one JSON-LD FAQPage node, got {len(faq_pages)}")

        if len(faq_pages) == 1:
            structured_pairs: list[tuple[str, str]] = []
            main_entities = faq_pages[0].get("mainEntity")
            if not isinstance(main_entities, list) or not main_entities:
                errors.append(f"{url}: FAQPage.mainEntity must be a non-empty list")
            else:
                for index, entity in enumerate(main_entities, start=1):
                    if not isinstance(entity, dict) or entity.get("@type") != "Question":
                        errors.append(f"{url}: FAQPage item {index} must be a Question")
                        continue
                    question = entity.get("name")
                    answer = entity.get("acceptedAnswer")
                    answer_text = answer.get("text") if isinstance(answer, dict) else None
                    if not isinstance(answer, dict) or answer.get("@type") != "Answer":
                        errors.append(f"{url}: FAQPage item {index} must contain acceptedAnswer of type Answer")
                        continue
                    if not isinstance(question, str) or not question.strip():
                        errors.append(f"{url}: FAQPage item {index} has an empty question")
                        continue
                    if not isinstance(answer_text, str) or not answer_text.strip():
                        errors.append(f"{url}: FAQPage item {index} has an empty answer")
                        continue
                    structured_pairs.append(
                        (
                            re.sub(r"\s+", " ", question).strip(),
                            re.sub(r"\s+", " ", answer_text).strip(),
                        )
                    )

            visible_pairs = [
                (
                    re.sub(r"\s+", " ", question).strip(),
                    re.sub(r"\s+", " ", answer).strip(),
                )
                for question, answer in parser.details_items
                if question.strip() or answer.strip()
            ]
            if Counter(visible_pairs) != Counter(structured_pairs):
                errors.append(
                    f"{url}: visible <details> FAQ and JSON-LD FAQPage questions/answers differ; "
                    f"visible={len(visible_pairs)}, structured={len(structured_pairs)}"
                )

        if not is_home and len(breadcrumbs) == 1:
            breadcrumb = breadcrumbs[0]
            expected_breadcrumb_id = f"{url}#breadcrumb"
            if breadcrumb.get("@id") != expected_breadcrumb_id:
                errors.append(
                    f"{url}: BreadcrumbList @id must be {expected_breadcrumb_id!r}; "
                    f"got {breadcrumb.get('@id')!r}"
                )

            items = breadcrumb.get("itemListElement")
            if not isinstance(items, list) or len(items) < 2:
                errors.append(f"{url}: BreadcrumbList must contain at least home + current page")
            else:
                structured_items: list[tuple[str, str]] = []
                for index, item in enumerate(items, start=1):
                    if not isinstance(item, dict) or item.get("@type") != "ListItem":
                        errors.append(f"{url}: BreadcrumbList item {index} must be a ListItem")
                        continue
                    if item.get("position") != index:
                        errors.append(
                            f"{url}: BreadcrumbList item {index} position must be {index}; "
                            f"got {item.get('position')!r}"
                        )
                    name = item.get("name")
                    target = item.get("item")
                    if not isinstance(name, str) or not name.strip():
                        errors.append(f"{url}: BreadcrumbList item {index} has an empty name")
                        continue
                    if not isinstance(target, str) or not target.strip():
                        errors.append(f"{url}: BreadcrumbList item {index} has an empty item URL")
                        continue
                    structured_items.append(
                        (re.sub(r"\s+", " ", name).strip(), target.strip())
                    )

                if visible_breadcrumb.trail_count != 1:
                    errors.append(
                        f"{url}: expected exactly one visible breadcrumb trail; "
                        f"got {visible_breadcrumb.trail_count}"
                    )
                else:
                    visible_items: list[tuple[str, str]] = []
                    for index, (href, name) in enumerate(visible_breadcrumb.items, start=1):
                        if href is None:
                            target = url if index == len(visible_breadcrumb.items) else ""
                        else:
                            parsed_href = urlparse(href)
                            if parsed_href.scheme or parsed_href.netloc:
                                target = href
                            elif href == "/":
                                target = f"{ORIGIN}/"
                            else:
                                target = f"{ORIGIN}{href}"
                        visible_items.append((name, target))

                    if visible_items != structured_items:
                        errors.append(
                            f"{url}: visible breadcrumb and JSON-LD BreadcrumbList differ; "
                            f"visible={visible_items!r}, structured={structured_items!r}"
                        )

                first = items[0] if isinstance(items[0], dict) else {}
                last = items[-1] if isinstance(items[-1], dict) else {}
                if first.get("position") != 1 or first.get("item") != f"{ORIGIN}/":
                    errors.append(
                        f"{url}: BreadcrumbList first item must be position 1 and point to homepage"
                    )
                if last.get("position") != len(items) or last.get("item") != url:
                    errors.append(
                        f"{url}: BreadcrumbList last item must point to the canonical current page"
                    )

    guard_unique("title", titles, errors)
    guard_unique("meta description", descriptions, errors)
    guard_unique("H1", h1s, errors)

    unique_errors = list(dict.fromkeys(errors))
    if unique_errors:
        print(f"Public SEO uniqueness guard: FAIL ({len(unique_errors)} issue(s))")
        for error in unique_errors:
            print(f"  - {error}")
        return 1

    print("Public SEO uniqueness guard: PASS")
    print(f"  sitemap pages checked: {len(routes)}")
    print("  every sitemap page has exactly one non-empty title, description and H1")
    print("  title, description and H1 values are unique across public sitemap pages")
    print("  every canonical and og:url matches its sitemap URL exactly")
    print("  og:title/og:description exactly mirror title/meta description")
    print("  public robots/OpenGraph image metadata/Twitter card are complete and preview-safe")
    print("  homepage defines canonical WebSite + SoftwareApplication entities")
    print("  non-home sitemap pages have WebPage + BreadcrumbList schema linked by @id")
    print("  non-home WebPage nodes link to canonical #website and #software entities")
    print("  embedded WebSite/SoftwareApplication nodes exactly match canonical homepage entities")
    print("  canonical SoftwareApplication.image matches the verified Open Graph image")
    print("  FAQPage schema exactly mirrors visible <details> questions/answers, order-independent")
    print("  visible breadcrumb trails exactly mirror JSON-LD BreadcrumbList names, positions and URLs")
    print("  JSON-LD WebPage nodes mirror canonical/title/meta description and use inLanguage=uk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
