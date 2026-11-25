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
LITE_UK = ORIGIN + "/bezkoshtovna-programa-dlya-magazynu"
LITE_EN = ORIGIN + "/en/lite"
# Reviewed pairs activate independently only when their English URL enters the sitemap.
HOME_UK = ORIGIN + "/"
HOME_EN = ORIGIN + "/en"
DOWNLOAD_UK = ORIGIN + "/download"
DOWNLOAD_EN = ORIGIN + "/en/download"
SUPPORT_UK = ORIGIN + "/support"
SUPPORT_EN = ORIGIN + "/en/support"
FEATURES_UK = ORIGIN + "/features"
FEATURES_EN = ORIGIN + "/en/features"
LOCALE_PAIRS = (
    {"uk": LITE_UK, "en": LITE_EN},
    {"uk": HOME_UK, "en": HOME_EN},
    {"uk": DOWNLOAD_UK, "en": DOWNLOAD_EN},
    {"uk": SUPPORT_UK, "en": SUPPORT_EN},
    {"uk": FEATURES_UK, "en": FEATURES_EN},
)
OG_LOCALES = {"uk": "uk_UA", "en": "en_US"}


def locale_contract(url: str, sitemap_urls: set[str]) -> tuple[str, list[tuple[str, str]]]:
    for pair in LOCALE_PAIRS:
        if url not in pair.values():
            continue
        lang = next(lang for lang, target in pair.items() if target == url)
        if pair["en"] not in sitemap_urls:
            if lang == "en":
                raise ValueError("English URL is not active in sitemap")
            return lang, []
        if not set(pair.values()).issubset(sitemap_urls):
            raise ValueError("localized URL is missing its Ukrainian equivalent in sitemap")
        return lang, sorted(pair.items())
    if urlparse(url).path.rstrip("/") == "/en" or urlparse(url).path.startswith("/en/"):
        raise ValueError("English URL is outside the reviewed locale-pair registry")
    return "uk", []


def check_locale(url: str, sitemap_urls: set[str], html_languages: list[str],
                 alternates: list[tuple[str, str]], errors: list[str]) -> str:
    try:
        lang, expected = locale_contract(url, sitemap_urls)
    except ValueError as exc:
        errors.append(f"{url}: {exc}")
        return "uk"
    if html_languages != [lang]:
        errors.append(f"{url}: expected exactly one html lang={lang!r}, got {html_languages!r}")
    if sorted(alternates) != expected:
        errors.append(f"{url}: hreflang must match the complete reviewed reciprocal pair; "
                      f"expected {expected!r}, got {alternates!r}")
    return lang

def breadcrumb_home(url: str, sitemap_urls: set[str]) -> str:
    """Use the actual localized homepage only after its reviewed route is active."""
    if url != HOME_EN and urlparse(url).path.startswith("/en/") and HOME_EN in sitemap_urls:
        return HOME_EN
    return HOME_UK


def support_faq_review_errors(manifest: dict, source_pairs: list[tuple[str, str]],
                              target_pairs: list[tuple[str, str]]) -> list[str]:
    """Require explicit one-to-one review of both languages, not just equal counts."""
    if not isinstance(manifest, dict) or manifest.get("schema") != 1 or (
        manifest.get("source"), manifest.get("target")
    ) != ("site/support.html", "site/en/support.html"):
        return ["support FAQ review manifest schema or paths are invalid"]
    entries = manifest.get("pairs")
    if not isinstance(entries, list) or not entries:
        return ["support FAQ review manifest has no pairs"]
    reviewed = {"uk": [], "en": []}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"uk", "en"}:
            return ["support FAQ review manifest contains an invalid entry"]
        for lang in reviewed:
            pair = entry[lang]
            if not isinstance(pair, list) or len(pair) != 2 or not all(
                isinstance(value, str) and value.strip() for value in pair
            ):
                return ["support FAQ review manifest contains an invalid question/answer"]
            reviewed[lang].append(tuple(re.sub(r"\s+", " ", value).strip() for value in pair))
    errors = []
    for lang, actual in (("uk", source_pairs), ("en", target_pairs)):
        if len({question for question, _ in reviewed[lang]}) != len(reviewed[lang]):
            errors.append(f"support FAQ review: duplicate {lang} question")
        if Counter(reviewed[lang]) != Counter(actual):
            errors.append(f"support FAQ review: {lang} content changed; review and update the paired translation manifest")
    return errors


def test_support_faq_review() -> None:
    sample = {"schema": 1, "source": "site/support.html", "target": "site/en/support.html",
              "pairs": [{"uk": ["Q1", "A1"], "en": ["E1", "T1"]},
                        {"uk": ["Q2", "A2"], "en": ["E2", "T2"]}]}
    uk = [("Q1", "A1"), ("Q2", "A2")]
    en = [("E1", "T1"), ("E2", "T2")]
    cases = [
        (sample, uk, en, True),
        (sample, uk[::-1], en[::-1], True),
        (sample, [("Q1", "new"), uk[1]], en, False),
        (sample, uk, [("E1", "new"), en[1]], False),
        (sample, uk + [("Q3", "A3")], en, False),
        (sample, uk, en[:1], False),
        ({**sample, "pairs": [sample["pairs"][0]] * 2}, uk, en, False),
        ({**sample, "schema": 2}, uk, en, False),
        ({**sample, "pairs": [{"uk": ["Q1"], "en": ["E1", "T1"]}]}, uk, en, False),
    ]
    for manifest, source, target, valid in cases:
        if bool(support_faq_review_errors(manifest, source, target)) == valid:
            raise AssertionError("support FAQ review fixture mismatch")
    print("  support FAQ review: 9 synthetic cases passed")


def is_lite_software(node: dict, page_url: str) -> bool:
    page=LITE_UK
    return (page_url in {LITE_UK, LITE_EN} and node.get("@type")=="SoftwareApplication"
            and node.get("@id")==page+"#lite-software" and node.get("url")==page
            and node.get("name")=="OutPOSt Lite" and node.get("isAccessibleForFree") is True
            and re.fullmatch(re.escape(ORIGIN)+r"/downloads/OutPOSt-Lite-Setup-v\d+\.\d+\.\d+\.exe",str(node.get("downloadUrl",""))) is not None)


class SeoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.h1_parts: list[list[str]] = []
        self.description_values: list[str] = []
        self.meta: dict[str, list[str]] = defaultdict(list)
        self.canonicals: list[str] = []
        self.html_languages: list[str] = []
        self.alternates: list[tuple[str, str]] = []
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

        if tag == "html":
            self.html_languages.append((data.get("lang") or "").strip())
        elif tag == "title":
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
            if data.get("hreflang") is not None:
                self.alternates.append(((data.get("hreflang") or "").strip(),
                                        (data.get("href") or "").strip() if "alternate" in rel else ""))

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
    sitemap_urls = {url for url, _ in routes}
    support_pairs: dict[str, list[tuple[str, str]]] = {}

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

    lite_nodes: dict[str, dict] = {}
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

        lang = check_locale(url, sitemap_urls, parser.html_languages, parser.alternates, errors)

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
        if parser.meta.get("og:locale", []) != [OG_LOCALES[lang]]:
            errors.append(f"{url}: og:locale must be exactly {OG_LOCALES[lang]!r}")
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

        is_home = url == HOME_UK
        is_english_home = url == HOME_EN
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
            if is_english_home:
                if breadcrumbs:
                    errors.append(f"{url}: English homepage must not expose BreadcrumbList schema")
                if visible_breadcrumb.trail_count:
                    errors.append(f"{url}: English homepage must not expose a visible breadcrumb trail")
            elif len(breadcrumbs) != 1:
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
            if len(og_images) == 1:
                preview = og_images[0]
                if re.fullmatch(r"https://outpost\.com\.ua/assets/outpost-og-[0-9]{8}\.jpg", preview):
                    screenshot = f"{ORIGIN}/assets/screenshots/02410/sales.png"
                    if software.get("image") != screenshot:
                        errors.append(f"{url}: the shared SoftwareApplication must retain its product screenshot")
                    for key, values in {
                        "og:image:secure_url": [preview],
                        "og:image:type": ["image/jpeg"],
                        "og:image:width": ["1200"],
                        "og:image:height": ["630"],
                        "twitter:image": [preview],
                        "twitter:image:alt": image_alts,
                    }.items():
                        if parser.meta.get(key, []) != values:
                            errors.append(f"{url}: {key} must match the homepage social preview")
                elif software.get("image") != preview:
                    errors.append(f"{url}: homepage SoftwareApplication.image must match og:image exactly")

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
                if is_lite_software(software,url):
                    lite_nodes[url] = software
                    continue
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
            if web_page.get("inLanguage") != lang:
                errors.append(
                    f"{url}: JSON-LD WebPage.inLanguage must be {lang!r}; "
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
                if url in {LITE_UK, LITE_EN}:
                    expected_software_id=LITE_UK+"#lite-software"
                    if sum(is_lite_software(software,url) for software in software_apps)!=1:
                        errors.append(f"{url}: expected one identified free Lite software entity")
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
                if is_english_home:
                    if "breadcrumb" in web_page:
                        errors.append(f"{url}: English homepage WebPage must not reference a breadcrumb")
                elif actual_breadcrumb_ref != expected_breadcrumb_id:
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

            if url in {SUPPORT_UK, SUPPORT_EN}:
                support_pairs[url] = structured_pairs

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
                expected_home = breadcrumb_home(url, sitemap_urls)
                if first.get("position") != 1 or first.get("item") != expected_home:
                    errors.append(
                        f"{url}: BreadcrumbList first item must be position 1 and point to {expected_home}"
                    )
                if last.get("position") != len(items) or last.get("item") != url:
                    errors.append(
                        f"{url}: BreadcrumbList last item must point to the canonical current page"
                    )

    if LITE_EN in sitemap_urls:
        if LITE_UK not in lite_nodes or LITE_EN not in lite_nodes or lite_nodes[LITE_UK] != lite_nodes[LITE_EN]:
            errors.append("English Lite SoftwareApplication must exactly reuse the Ukrainian Lite product entity")

    if SUPPORT_EN in sitemap_urls:
        try:
            manifest = json.loads((ROOT / "docs/localization/support-faq-reviewed.json").read_text(encoding="utf-8"))
            if SUPPORT_UK not in support_pairs or SUPPORT_EN not in support_pairs:
                errors.append("support FAQ review: both languages require structured FAQ content")
            else:
                errors.extend(support_faq_review_errors(manifest, support_pairs[SUPPORT_UK], support_pairs[SUPPORT_EN]))
        except (OSError, ValueError) as exc:
            errors.append(f"support FAQ review manifest cannot be read: {exc}")

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
    print("  homepage social preview and canonical SoftwareApplication image are validated")
    print("  FAQPage schema exactly mirrors visible <details> questions/answers, order-independent")
    print("  visible breadcrumb trails exactly mirror JSON-LD BreadcrumbList names, positions and URLs")
    print("  JSON-LD WebPage nodes mirror canonical/title/meta description and use the reviewed page language")
    return 0


def test_locale_contract() -> None:
    uk_only = {ORIGIN + "/", LITE_UK}
    active = uk_only | {LITE_EN}
    def verify(url, urls, langs, alternates, valid):
        errors: list[str] = []
        check_locale(url, urls, langs, alternates, errors)
        if bool(errors) == valid:
            raise AssertionError(f"locale regression: {url}, {langs}, {alternates}, {errors}")
    pair = sorted([("uk", LITE_UK), ("en", LITE_EN)])
    verify(LITE_UK, uk_only, ["uk"], [], True)
    verify(LITE_UK, uk_only, ["uk"], pair, False)
    verify(LITE_UK, active, ["uk"], pair, True)
    verify(LITE_EN, active, ["en"], pair, True)
    verify(LITE_EN, active, ["uk"], pair, False)
    verify(LITE_EN, active, ["en"], [("en", LITE_EN)], False)
    verify(LITE_EN, active, ["en"], pair + [("en", LITE_EN)], False)
    verify(LITE_EN, active - {LITE_UK}, ["en"], pair, False)
    verify(ORIGIN + "/en/unknown", active, ["en"], [], False)
    verify(ORIGIN + "/", active, ["uk"], pair, False)
    parser = SeoParser()
    parser.feed('<html lang="en"><link rel="alternate" hreflang="en" href="' + LITE_EN +
                '"><link rel="alternate" hreflang="uk" href="' + LITE_UK + '">')
    parser.close()
    verify(LITE_EN, active, parser.html_languages, parser.alternates, True)
    home_pair = sorted([("uk", HOME_UK), ("en", HOME_EN)])
    both = active | {HOME_EN}
    # Each translation pair must activate independently, with no cross-pair links.
    verify(HOME_UK, uk_only, ["uk"], [], True)
    verify(HOME_UK, active, ["uk"], home_pair, False)
    verify(HOME_EN, active, ["en"], [], False)
    verify(HOME_UK, both, ["uk"], home_pair, True)
    verify(HOME_EN, both, ["en"], home_pair, True)
    verify(LITE_EN, both, ["en"], pair, True)
    verify(HOME_EN, both, ["en"], pair, False)
    verify(HOME_EN, both, ["en"], home_pair + pair, False)
    verify(HOME_EN, both - {HOME_UK}, ["en"], home_pair, False)
    verify(HOME_UK, both, ["en"], home_pair, False)
    verify(HOME_EN, both, ["en"], home_pair + [("en", HOME_EN)], False)
    verify(HOME_EN, both - {LITE_EN}, ["en"], home_pair, True)
    downloads = both | {DOWNLOAD_UK, DOWNLOAD_EN}
    download_pair = sorted([("uk", DOWNLOAD_UK), ("en", DOWNLOAD_EN)])
    verify(DOWNLOAD_UK, both | {DOWNLOAD_UK}, ["uk"], [], True)
    verify(DOWNLOAD_EN, both | {DOWNLOAD_UK}, ["en"], [], False)
    verify(DOWNLOAD_UK, downloads, ["uk"], download_pair, True)
    verify(DOWNLOAD_EN, downloads, ["en"], download_pair, True)
    verify(DOWNLOAD_EN, downloads, ["en"], home_pair, False)
    verify(DOWNLOAD_EN, downloads - {DOWNLOAD_UK}, ["en"], download_pair, False)
    support = downloads | {SUPPORT_UK, SUPPORT_EN}
    support_pair = sorted([("uk", SUPPORT_UK), ("en", SUPPORT_EN)])
    verify(SUPPORT_UK, downloads | {SUPPORT_UK}, ["uk"], [], True)
    verify(SUPPORT_EN, downloads | {SUPPORT_UK}, ["en"], [], False)
    verify(SUPPORT_UK, support, ["uk"], support_pair, True)
    verify(SUPPORT_EN, support, ["en"], support_pair, True)
    verify(SUPPORT_EN, support, ["en"], download_pair, False)
    verify(SUPPORT_EN, support - {SUPPORT_UK}, ["en"], support_pair, False)
    features = support | {FEATURES_UK, FEATURES_EN}
    feature_pair = sorted([("uk", FEATURES_UK), ("en", FEATURES_EN)])
    verify(FEATURES_UK, support | {FEATURES_UK}, ["uk"], [], True)
    verify(FEATURES_EN, support | {FEATURES_UK}, ["en"], [], False)
    verify(FEATURES_UK, features, ["uk"], feature_pair, True)
    verify(FEATURES_EN, features, ["en"], feature_pair, True)
    verify(FEATURES_EN, features, ["en"], support_pair, False)
    verify(FEATURES_EN, features - {FEATURES_UK}, ["en"], feature_pair, False)
    print("  locale contract: 41 synthetic cases passed")
    for url, urls, expected in (
        (LITE_EN, active, HOME_UK),
        (LITE_EN, both, HOME_EN),
        (LITE_UK, both, HOME_UK),
        (HOME_EN, both, HOME_UK),
    ):
        if breadcrumb_home(url, urls) != expected:
            raise AssertionError(f"localized breadcrumb home regression: {url}, {urls}")
    print("  localized breadcrumb routing: 4 synthetic cases passed")


if __name__ == "__main__":
    test_support_faq_review()
    test_locale_contract()
    sys.exit(main())
