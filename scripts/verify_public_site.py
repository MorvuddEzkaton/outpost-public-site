#!/usr/bin/env python3
"""OutPOSt public-site smoke checks.

Standard-library only. Run from the repository root:
    python scripts/verify_public_site.py

The validator is intentionally read-only. It checks static public-site integrity and
protected web integration boundaries without calling production APIs or D1.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import json
import re
import sys
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "site"
PUBLIC_ORIGIN = "https://outpost.com.ua"
CABINET_ORIGIN = "https://cabinet.outpost.com.ua"

REQUIRED_FILES = [
    "index.html",
    "features.html",
    "interfeis.html",
    "download.html",
    "mini-t400.html",
    "prro-checkbox.html",
    "buhgalteriya.html",
    "robots.txt",
    "sitemap.xml",
    "script.js",
    "_worker.js",
    "_headers",
]

REQUIRED_CANONICALS = {
    "index.html": f"{PUBLIC_ORIGIN}/",
    "features.html": f"{PUBLIC_ORIGIN}/features",
    "interfeis.html": f"{PUBLIC_ORIGIN}/interfeis",
    "download.html": f"{PUBLIC_ORIGIN}/download",
    "mini-t400.html": f"{PUBLIC_ORIGIN}/mini-t400",
    "prro-checkbox.html": f"{PUBLIC_ORIGIN}/prro-checkbox",
    "buhgalteriya.html": f"{PUBLIC_ORIGIN}/buhgalteriya",
}

REQUIRED_SITEMAP_URLS = set(REQUIRED_CANONICALS.values())
CORE_PUBLIC_PAGES = list(REQUIRED_CANONICALS)

SPECIAL_NON_SITEMAP_HTML = {
    "404.html",
    "demo.html",
    "google2c445dfee2b7ddee.html",
}
GOOGLE_VERIFICATION_FILE = "google2c445dfee2b7ddee.html"
GOOGLE_VERIFICATION_CONTENT = "google-site-verification: google2c445dfee2b7ddee.html"

PROTECTED_WORKER_MARKERS = [
    'const PUBLIC_QUESTION_PATH = "/api/public-question";',
    'const CUSTOMER_PORTAL_ORIGIN = "https://cabinet.outpost.com.ua";',
    "return proxyPublicQuestion(request);",
    "env.ASSETS.fetch(request)",
]

SCRIPT_MARKERS = [
    'const href = "/buhgalteriya";',
    "1 ліцензія = 1 робочий ПК.",
    "Скільки комп’ютерів покриває одна ліцензія?",
    "Чи входить OutPOSt Бухгалтерія у вартість програми?",
    'if (location.pathname !== "/programa-dlya-fop") return;',
    "OutPOSt уже закриває операційну роботу магазину.",
    "Без рекламного відстеження",
]

DISALLOWED_PUBLIC_SOURCE_MARKERS = [
    "http://localhost",
    "https://localhost",
    "staging.outpost-web.pages.dev",
]

SHARED_SCRIPT_RE = re.compile(
    r'<script\b[^>]*\bsrc=["\']/?script\.js(?:\?[^"\']*)?["\']',
    re.IGNORECASE,
)
JSON_LD_SCRIPT_RE = re.compile(
    r'<script\b[^>]*\btype=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
    re.IGNORECASE,
)

SITEMAP_CHANGEFREQ_VALUES = {
    "always",
    "hourly",
    "daily",
    "weekly",
    "monthly",
    "yearly",
    "never",
}

REQUIRED_SOCIAL_META = (
    "description",
    "og:title",
    "og:description",
    "og:url",
    "og:image",
    "og:image:width",
    "og:image:height",
    "og:image:alt",
    "twitter:card",
)

DEMO_REVALIDATE_ASSETS = (
    "/assets/outpost-demo-v1.css",
    "/assets/outpost-demo-v1.js",
    "/assets/outpost-demo-modules-v1.js",
    "/assets/outpost-demo-returns-v1.js",
    "/assets/outpost-demo-products-v1.js",
)
DEMO_REVALIDATE_HEADER = "Cache-Control: no-cache, max-age=0, must-revalidate"

SEO_INTENT_CONTRACTS = {
    "avtomatyzatsiya-magazynu.html": {
        "required": (
            "Автоматизація магазину: каса, склад і облік | OutPOSt",
            'id="store-automation-scenarios"',
            "<h1>Автоматизація магазину на Windows з OutPOSt</h1>",
            'href="/avtomatyzatsiya-zakupivel-i-skladu"',
            'href="/avtomatyzatsiya-rozdribnoi-torgivli"',
        ),
        "forbidden_head": (
            "автоматизація роздрібної торгівлі",
            "автоматизація закупівель і складу",
        ),
    },
    "avtomatyzatsiya-zakupivel-i-skladu.html": {
        "required": (
            "Автоматизація закупівель і складу магазину | OutPOSt",
            'id="procurement-workflow"',
            "<h1>Автоматизація закупівель і складу для магазину</h1>",
        ),
        "forbidden_head": (),
    },
    "avtomatyzatsiya-rozdribnoi-torgivli.html": {
        "required": (
            "Автоматизація роздрібної торгівлі: каса й продажі | OutPOSt",
            'id="retail-sales-workflow"',
            "<h1>Автоматизація роздрібної торгівлі для магазину</h1>",
        ),
        "forbidden_head": (),
    },
}


class DialogContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.dialogs: list[tuple[str, set[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "dialog":
            return
        data = {key.lower(): (value or "") for key, value in attrs}
        dialog_id = data.get("id", "").strip()
        classes = set(data.get("class", "").split())
        self.dialogs.append((dialog_id, classes))


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.anchors: list[str] = []
        self.canonicals: list[str] = []
        self.robots: list[str] = []
        self.meta: dict[str, list[str]] = defaultdict(list)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (data.get("property") or data.get("name") or "").lower()
            if key:
                self.meta[key].append(data.get("content", "").strip())
            if data.get("name", "").lower() == "robots":
                self.robots.append(data.get("content", "").lower())

        if tag == "a" and data.get("href"):
            self.links.append(("href", data["href"]))
            self.anchors.append(data["href"])
        elif tag in {"img", "script"} and data.get("src"):
            self.links.append(("src", data["src"]))
        elif tag == "link" and data.get("href"):
            rel = data.get("rel", "").lower()
            if "canonical" in rel:
                self.canonicals.append(data["href"])
            elif any(token in rel for token in ("stylesheet", "icon", "apple-touch-icon")):
                self.links.append(("href", data["href"]))


def collect_json_ld_question_names(value: object) -> list[str]:
    names: list[str] = []
    if isinstance(value, dict):
        type_value = value.get("@type")
        is_question = type_value == "Question" or (
            isinstance(type_value, list) and "Question" in type_value
        )
        if is_question:
            name = value.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
        for child in value.values():
            names.extend(collect_json_ld_question_names(child))
    elif isinstance(value, list):
        for child in value:
            names.extend(collect_json_ld_question_names(child))
    return names


def validate_faq_schema_question_uniqueness(filename: str, text: str) -> list[str]:
    errors: list[str] = []
    names: list[str] = []

    for index, raw in enumerate(JSON_LD_SCRIPT_RE.findall(text), start=1):
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(
                f"site/{filename}: malformed JSON-LD script #{index}: "
                f"{exc.msg} at line {exc.lineno} column {exc.colno}"
            )
            continue
        names.extend(collect_json_ld_question_names(document))

    for name, count in sorted(Counter(names).items()):
        if count > 1:
            errors.append(
                f"site/{filename}: duplicate FAQ Question.name {name!r} appears {count} times in JSON-LD"
            )

    return errors


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        header = path.read_bytes()[:24]
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return (
        int.from_bytes(header[16:20], "big"),
        int.from_bytes(header[20:24], "big"),
    )


def validate_demo_dialog_contract(text: str) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    parser = DialogContractParser()
    parser.feed(text)

    for index, (dialog_id, classes) in enumerate(parser.dialogs, start=1):
        label = f"dialog #{dialog_id}" if dialog_id else f"dialog #{index}"

        if not dialog_id:
            errors.append(f"site/demo.html: {label} must have a stable id")
        elif dialog_id in seen_ids:
            errors.append(f"site/demo.html: duplicate dialog id: {dialog_id}")
        else:
            seen_ids.add(dialog_id)

        if "demo-dialog" not in classes:
            errors.append(
                f"site/demo.html: {label} must include class 'demo-dialog' so global F1-F7 modal isolation applies"
            )

    if not parser.dialogs:
        errors.append("site/demo.html: no dialog elements found; modal keyboard contract disappeared")

    return errors

def check_demo_dialog_contract(errors: list[str]) -> None:
    path = SITE / "demo.html"
    if not path.is_file():
        return
    errors.extend(validate_demo_dialog_contract(read_text(path)))


def normalize_internal_path(raw: str) -> str | None:
    raw = raw.strip()
    if not raw or raw.startswith(("#", "mailto:", "tel:", "data:", "javascript:")):
        return None

    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme != "https" or parsed.netloc not in {"outpost.com.ua", "www.outpost.com.ua"}:
            return None
        path = parsed.path
    else:
        path = parsed.path

    if not path or path == "/":
        return "index.html"
    if path.startswith(("/api/", "/cdn-cgi/")):
        return None

    clean = path.lstrip("/")
    if not clean:
        return "index.html"

    suffix = Path(clean).suffix
    if suffix:
        return clean

    return f"{clean}.html"


def target_exists(resolved: str) -> bool:
    target = SITE / resolved
    if target.is_file():
        return True

    clean = resolved[:-5] if resolved.endswith(".html") else resolved
    return (SITE / clean / "index.html").is_file()


def resolve_target_file(resolved: str) -> Path | None:
    direct = SITE / resolved
    if direct.is_file():
        return direct
    clean = resolved[:-5] if resolved.endswith(".html") else resolved
    nested = SITE / clean / "index.html"
    return nested if nested.is_file() else None


def canonical_is_public(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "outpost.com.ua"
        and not parsed.query
        and not parsed.fragment
    )


def check_required_files(errors: list[str]) -> None:
    for relative in REQUIRED_FILES:
        if not (SITE / relative).is_file():
            errors.append(f"missing required file: site/{relative}")


def check_html_pages(errors: list[str]) -> int:
    html_pages = sorted(SITE.glob("*.html"))
    canonical_owners: dict[str, list[str]] = defaultdict(list)

    for path in html_pages:
        name = path.name
        text = read_text(path)
        parser = LinkCollector()
        parser.feed(text)

        expected = REQUIRED_CANONICALS.get(name)
        if expected is not None and parser.canonicals != [expected]:
            errors.append(
                f"site/{name}: canonical mismatch; expected exactly {expected!r}, got {parser.canonicals!r}"
            )

        if name != "404.html":
            if len(parser.canonicals) > 1:
                errors.append(f"site/{name}: multiple canonical URLs found: {parser.canonicals!r}")
            elif len(parser.canonicals) == 1:
                canonical = parser.canonicals[0]
                if not canonical_is_public(canonical):
                    errors.append(f"site/{name}: non-production canonical URL: {canonical}")
                canonical_owners[canonical].append(name)

        for marker in DISALLOWED_PUBLIC_SOURCE_MARKERS:
            if marker in text:
                errors.append(f"site/{name}: disallowed public-source marker found: {marker}")

        for raw in parser.anchors:
            href = raw.strip()
            parsed_href = urlparse(href)
            if (
                parsed_href.scheme in {"http", "https"}
                and parsed_href.netloc in {"outpost.com.ua", "www.outpost.com.ua"}
            ):
                errors.append(
                    f"site/{name}: public-site anchor must use a relative canonical path, got {href!r}"
                )
                continue

            if not href.startswith("/"):
                continue

            path_only = parsed_href.path
            if path_only != "/" and path_only.endswith(".html"):
                errors.append(
                    f"site/{name}: internal anchor must not expose .html route variant: {href!r}"
                )
            if len(path_only) > 1 and path_only.endswith("/"):
                errors.append(
                    f"site/{name}: internal anchor must not expose trailing-slash route variant: {href!r}"
                )

        for _, raw in parser.links:
            resolved = normalize_internal_path(raw)
            if resolved is None:
                continue
            if not target_exists(resolved):
                errors.append(f"site/{name}: broken internal reference {raw!r} -> site/{resolved}")

    for canonical, owners in sorted(canonical_owners.items()):
        if len(owners) > 1:
            errors.append(f"duplicate canonical {canonical!r} used by: {', '.join(owners)}")

    return len(html_pages)


def check_homepage_semantics(errors: list[str]) -> None:
    """Keep the full homepage content in the primary landmark, before the global footer."""
    text = read_text(SITE / "index.html")
    positions = {
        "main_open": text.find("<main"),
        "main_close": text.find("</main>"),
        "extra_questions": text.find('<section class="faq-section-new seo-depth-section">'),
        "footer_open": text.find('<footer class="footer">'),
        "footer_close": text.find("</footer>"),
    }
    if any(value < 0 for value in positions.values()) or not (
        positions["main_open"] < positions["extra_questions"]
        < positions["main_close"] < positions["footer_open"] < positions["footer_close"]
    ) or text.count("</main>") != 1 or text.count('<footer class="footer">') != 1:
        errors.append("site/index.html: homepage main must enclose the extra FAQ and close before the global footer")

    for page in ("index.html", "oblik-tovariv-u-magazyni.html",
                 "avtomatyzatsiya-zakupivel-i-skladu.html"):
        if '<a href="/tsinnyky-ta-etyketky">Цінники та етикетки</a>' not in read_text(SITE / page):
            errors.append(f"site/{page}: missing contextual link to the labels module")


def check_cabinet_boundary(errors: list[str]) -> None:
    for name in ("index.html", "features.html", "buhgalteriya.html"):
        path = SITE / name
        if path.is_file() and CABINET_ORIGIN not in read_text(path):
            errors.append(f"site/{name}: canonical cabinet link is missing")

    worker = SITE / "_worker.js"
    if not worker.is_file():
        return
    text = read_text(worker)
    for marker in PROTECTED_WORKER_MARKERS:
        if marker not in text:
            errors.append(f"site/_worker.js: protected contract marker missing: {marker}")

    suspicious = re.findall(r"https://[^\"'\s]+", text)
    allowed = {
        "https://cabinet.outpost.com.ua",
        "https://outpost.com.ua",
    }
    for url in suspicious:
        normalized = url.rstrip("/);,.")
        if normalized not in allowed:
            errors.append(f"site/_worker.js: unexpected absolute upstream URL: {normalized}")


def check_script_contract(errors: list[str]) -> None:
    path = SITE / "script.js"
    if not path.is_file():
        return
    text = read_text(path)
    for marker in SCRIPT_MARKERS:
        if marker not in text:
            errors.append(f"site/script.js: expected public-site marker missing: {marker}")


def check_seo_intent_separation(errors: list[str]) -> None:
    for filename, contract in SEO_INTENT_CONTRACTS.items():
        path = SITE / filename
        if not path.is_file():
            errors.append(f"site/{filename}: missing SEO-intent source")
            continue
        text = read_text(path)
        head = text.split("</head>", 1)[0].lower()
        for marker in contract["required"]:
            if marker not in text:
                errors.append(f"site/{filename}: missing SEO-intent marker: {marker}")
        for marker in contract["forbidden_head"]:
            if marker.lower() in head:
                errors.append(
                    f"site/{filename}: specialist SEO intent leaked into hub <head>: {marker}"
                )


def check_social_metadata(url: str, parser: LinkCollector, errors: list[str]) -> None:
    for key in REQUIRED_SOCIAL_META:
        values = parser.meta.get(key, [])
        if len(values) != 1:
            errors.append(f"site/sitemap.xml: {url} must have exactly one {key} meta value; got {values!r}")
            continue
        if not values[0].strip():
            errors.append(f"site/sitemap.xml: {url} has an empty {key} meta value")

    og_url = parser.meta.get("og:url", [])
    if og_url and og_url != [url]:
        errors.append(f"site/sitemap.xml: {url} og:url must match canonical exactly; got {og_url!r}")

    og_image = parser.meta.get("og:image", [])
    if len(og_image) == 1 and og_image[0]:
        parsed = urlparse(og_image[0])
        if parsed.scheme != "https" or parsed.netloc != "outpost.com.ua" or not parsed.path.startswith("/"):
            errors.append(
                f"site/sitemap.xml: {url} og:image must be an absolute HTTPS outpost.com.ua URL; got {og_image[0]!r}"
            )
        else:
            relative = parsed.path.lstrip("/")
            if ".." in Path(relative).parts:
                errors.append(f"site/sitemap.xml: {url} og:image path traversal is forbidden")
            else:
                asset_path = SITE / relative
                if not asset_path.is_file():
                    errors.append(
                        f"site/sitemap.xml: {url} og:image source asset is missing: {asset_path.relative_to(REPO_ROOT)}"
                    )
                elif asset_path.suffix.lower() == ".png":
                    actual = png_dimensions(asset_path)
                    if actual is None:
                        errors.append(
                            f"site/sitemap.xml: {url} og:image PNG has invalid signature/IHDR"
                        )
                    else:
                        widths = parser.meta.get("og:image:width", [])
                        heights = parser.meta.get("og:image:height", [])
                        if len(widths) == 1 and len(heights) == 1:
                            try:
                                declared = (int(widths[0]), int(heights[0]))
                            except ValueError:
                                errors.append(
                                    f"site/sitemap.xml: {url} og:image dimensions must be integers"
                                )
                            else:
                                if declared != actual:
                                    errors.append(
                                        f"site/sitemap.xml: {url} og:image dimensions mismatch; "
                                        f"declared={declared[0]}x{declared[1]} actual={actual[0]}x{actual[1]}"
                                    )

    twitter_card = parser.meta.get("twitter:card", [])
    if twitter_card and twitter_card != ["summary_large_image"]:
        errors.append(
            f"site/sitemap.xml: {url} twitter:card must be 'summary_large_image'; got {twitter_card!r}"
        )


def check_html_sitemap_coverage(errors: list[str]) -> None:
    sitemap_path = SITE / "sitemap.xml"
    if not sitemap_path.is_file():
        return
    try:
        root = ET.fromstring(read_text(sitemap_path))
    except ET.ParseError:
        return

    sitemap_html: set[str] = set()
    for elem in root.iter():
        if not elem.tag.endswith("loc") or not elem.text:
            continue
        raw = elem.text.strip()
        parsed = urlparse(raw)
        if parsed.scheme != "https" or parsed.netloc != "outpost.com.ua":
            continue
        route = parsed.path or "/"
        target = "index.html" if route == "/" else route.strip("/") + ".html"
        sitemap_html.add(target)

    actual_html = {path.name for path in SITE.glob("*.html")}
    unexpected = sorted(actual_html - sitemap_html - SPECIAL_NON_SITEMAP_HTML)
    for filename in unexpected:
        errors.append(
            f"site/{filename}: root HTML page is outside sitemap and special-page allowlist; "
            "add it to the canonical sitemap or explicitly classify it"
        )

    missing_special = sorted(SPECIAL_NON_SITEMAP_HTML - actual_html)
    for filename in missing_special:
        errors.append(f"site/{filename}: expected special non-sitemap HTML file is missing")

    for filename in ("404.html", "demo.html"):
        path = SITE / filename
        if not path.is_file():
            continue
        parser = LinkCollector()
        parser.feed(read_text(path))
        if not parser.robots or not any("noindex" in value for value in parser.robots):
            errors.append(f"site/{filename}: special non-sitemap page must remain noindex")

    verification = SITE / GOOGLE_VERIFICATION_FILE
    if verification.is_file():
        actual = read_text(verification).strip()
        if actual != GOOGLE_VERIFICATION_CONTENT:
            errors.append(
                f"site/{GOOGLE_VERIFICATION_FILE}: Google verification content changed unexpectedly"
            )


def check_sitemap(errors: list[str]) -> int:
    path = SITE / "sitemap.xml"
    if not path.is_file():
        return 0
    try:
        root = ET.fromstring(read_text(path))
    except ET.ParseError as exc:
        errors.append(f"site/sitemap.xml: invalid XML: {exc}")
        return 0

    url_list = [
        elem.text.strip()
        for elem in root.iter()
        if elem.tag.endswith("loc") and elem.text and elem.text.strip()
    ]
    urls = set(url_list)

    for index, url_node in enumerate(list(root), start=1):
        fields: dict[str, list[str]] = defaultdict(list)
        for child in list(url_node):
            key = child.tag.rsplit("}", 1)[-1]
            fields[key].append((child.text or "").strip())

        for required in ("loc", "lastmod", "changefreq", "priority"):
            values = fields.get(required, [])
            if len(values) != 1 or not values[0]:
                errors.append(
                    f"site/sitemap.xml: entry #{index} must have exactly one non-empty "
                    f"<{required}>; got {values!r}"
                )

        lastmods = fields.get("lastmod", [])
        if len(lastmods) == 1 and lastmods[0]:
            try:
                date.fromisoformat(lastmods[0])
            except ValueError:
                errors.append(
                    f"site/sitemap.xml: entry #{index} has invalid ISO lastmod {lastmods[0]!r}"
                )

        frequencies = fields.get("changefreq", [])
        if (
            len(frequencies) == 1
            and frequencies[0]
            and frequencies[0] not in SITEMAP_CHANGEFREQ_VALUES
        ):
            errors.append(
                f"site/sitemap.xml: entry #{index} has invalid changefreq {frequencies[0]!r}"
            )

        priorities = fields.get("priority", [])
        if len(priorities) == 1 and priorities[0]:
            try:
                priority = float(priorities[0])
            except ValueError:
                errors.append(
                    f"site/sitemap.xml: entry #{index} has non-numeric priority {priorities[0]!r}"
                )
            else:
                if not 0.0 <= priority <= 1.0:
                    errors.append(
                        f"site/sitemap.xml: entry #{index} priority must be between 0 and 1; "
                        f"got {priorities[0]!r}"
                    )

    duplicates = sorted(url for url, count in Counter(url_list).items() if count > 1)
    for url in duplicates:
        errors.append(f"site/sitemap.xml: duplicate URL: {url}")

    for required in sorted(REQUIRED_SITEMAP_URLS):
        if required not in urls:
            errors.append(f"site/sitemap.xml: missing {required}")

    for url in sorted(urls):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "outpost.com.ua" or parsed.query or parsed.fragment:
            errors.append(f"site/sitemap.xml: non-canonical URL: {url}")
            continue

        resolved = normalize_internal_path(url)
        if resolved is None or not target_exists(resolved):
            errors.append(f"site/sitemap.xml: URL has no static target: {url}")
            continue

        target = resolve_target_file(resolved)
        if target is None or target.suffix.lower() != ".html":
            errors.append(f"site/sitemap.xml: URL does not resolve to an HTML page: {url}")
            continue

        target_text = read_text(target)
        errors.extend(validate_faq_schema_question_uniqueness(target.name, target_text))
        parser = LinkCollector()
        parser.feed(target_text)
        if parser.canonicals != [url]:
            errors.append(
                f"site/sitemap.xml: {url} must have exactly one matching canonical; got {parser.canonicals!r}"
            )
        if any("noindex" in value for value in parser.robots):
            errors.append(f"site/sitemap.xml: {url} is listed but source meta robots contains noindex: {parser.robots!r}")

        check_social_metadata(url, parser, errors)

        demo_link_count = sum(
            1
            for kind, raw in parser.links
            if kind == "href" and urlparse(raw).path == "/demo"
        )
        if demo_link_count < 2:
            errors.append(
                f"site/sitemap.xml: {url} must expose /demo from shared navigation/footer; "
                f"found {demo_link_count} link(s)"
            )

        shared_script_count = len(SHARED_SCRIPT_RE.findall(target_text))
        if shared_script_count != 1:
            errors.append(
                f"site/sitemap.xml: {url} must include shared script.js exactly once; found {shared_script_count}"
            )

    return len(url_list)


def check_robots(errors: list[str]) -> None:
    path = SITE / "robots.txt"
    if not path.is_file():
        return

    directives = [
        raw.strip()
        for raw in read_text(path).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if raw.strip() and not raw.strip().startswith("#")
    ]
    required = {
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        f"Sitemap: {PUBLIC_ORIGIN}/sitemap.xml",
    }
    missing = sorted(required - set(directives))
    for directive in missing:
        errors.append(f"site/robots.txt: missing required directive {directive!r}")

    sitemap_lines = [line for line in directives if line.lower().startswith("sitemap:")]
    expected_sitemap = [f"Sitemap: {PUBLIC_ORIGIN}/sitemap.xml"]
    if sitemap_lines != expected_sitemap:
        errors.append(
            f"site/robots.txt: expected exactly one canonical sitemap directive; got {sitemap_lines!r}"
        )

    disallows = [line for line in directives if line.lower().startswith("disallow:")]
    if "Disallow: /" in disallows:
        errors.append("site/robots.txt: public root must not be disallowed")


def check_demo_runtime_cache(errors: list[str]) -> None:
    headers_path = SITE / "_headers"
    demo_path = SITE / "demo.html"
    if not headers_path.is_file() or not demo_path.is_file():
        return

    headers = read_text(headers_path)
    for asset in DEMO_REVALIDATE_ASSETS:
        block = f"{asset}\n  {DEMO_REVALIDATE_HEADER}"
        if block not in headers:
            errors.append(f"site/_headers: demo runtime asset must revalidate: {asset}")

    demo = read_text(demo_path)
    if '/assets/outpost-demo-v1.js?v=month-20261018' not in demo:
        errors.append("site/demo.html: primary demo runtime cache key must be month-20261018")
    if '/assets/outpost-demo-v1.css?v=month-20261018' not in demo:
        errors.append("site/demo.html: demo stylesheet cache key must be month-20261018")
    if '/assets/outpost-demo-modules-v1.js?v=month-20261018' not in demo:
        errors.append("site/demo.html: demo module cache key must be month-20261018")


def main() -> int:
    errors: list[str] = []

    check_required_files(errors)
    html_count = check_html_pages(errors)
    check_homepage_semantics(errors)
    check_cabinet_boundary(errors)
    check_script_contract(errors)
    check_seo_intent_separation(errors)
    check_demo_runtime_cache(errors)
    check_demo_dialog_contract(errors)
    check_html_sitemap_coverage(errors)
    sitemap_count = check_sitemap(errors)
    check_robots(errors)

    unique_errors = list(dict.fromkeys(errors))
    if unique_errors:
        print(f"OutPOSt public-site smoke check: FAIL ({len(unique_errors)} issue(s))")
        for item in unique_errors:
            print(f"  - {item}")
        return 1

    print("OutPOSt public-site smoke check: PASS")
    print(f"  checked {html_count} public HTML files ({len(CORE_PUBLIC_PAGES)} core canonical contracts)")
    print(f"  checked {sitemap_count} sitemap URL entries")
    print("  sitemap entries have one loc/lastmod/changefreq/priority with valid ISO/range values")
    print("  local PNG og:image assets exist and declared dimensions match PNG IHDR")
    print("  all sitemap pages have exact canonical, indexable robots and shared script.js exactly once")
    print("  all sitemap pages retain description + Open Graph URL/image/title/description + Twitter large-card metadata")
    print("  sitemap-page JSON-LD parses cleanly and FAQ Question.name values are unique per page")
    print("  every root HTML file is either in sitemap or an explicitly guarded special page")
    print("  404/demo remain noindex and the Google verification file content is pinned")
    print("  all sitemap pages expose /demo through shared navigation/footer")
    print("  protected cabinet/public-question boundary markers present")
    print("  automation SEO hub/specialist page intents remain separated")
    print("  online demo runtime assets revalidate instead of serving stale keyboard/UI code")
    print("  online demo dialogs all participate in the global F1-F7 modal-isolation contract")
    print("  internal anchors use relative canonical routes without .html/trailing-slash variants")
    print("  robots.txt allows public crawling, blocks /admin and declares one canonical sitemap")
    print("  public links, canonicals, sitemap and robots.txt are internally consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
