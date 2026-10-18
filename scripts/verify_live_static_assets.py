#!/usr/bin/env python3
"""Verify live delivery of public static assets and online-demo cache safety.

Read-only production check. It derives public asset URLs from sitemap source
HTML/CSS and explicitly adds the noindex online-demo runtime assets. Cloudflare
must serve every asset directly with HTTP 200 and the expected MIME type; demo
runtime assets must additionally use a revalidating Cache-Control policy.
Protected/backend routes and downloadable installer artifacts are excluded.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import os
import re
import sys
import time
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ORIGIN = "https://outpost.com.ua"

DEMO_REVALIDATE_PATHS = {
    "/assets/outpost-demo-v1.css",
    "/assets/outpost-demo-v1.js",
    "/assets/outpost-demo-modules-v1.js",
    "/assets/outpost-demo-returns-v1.js",
    "/assets/outpost-demo-products-v1.js",
}

EXCLUDED_PREFIXES = (
    "/downloads/",
    "/admin",
    "/api/",
    "/cdn-cgi/",
    "/functions/",
)

STATIC_EXTENSIONS = {
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
}

EXPECTED_CONTENT_TYPES = {
    ".css": {"text/css"},
    ".js": {"application/javascript", "text/javascript"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
    ".svg": {"image/svg+xml"},
    ".gif": {"image/gif"},
    ".ico": {"image/x-icon", "image/vnd.microsoft.icon", "image/ico"},
    ".woff": {"font/woff", "application/font-woff", "application/octet-stream"},
    ".woff2": {"font/woff2", "application/octet-stream"},
    ".ttf": {"font/ttf", "application/octet-stream"},
}

CSS_URL_RE = re.compile(r"url\(\s*([\"']?)(.*?)\1\s*\)", re.IGNORECASE)


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


class AssetCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        tag = tag.lower()

        if tag in {"img", "script"} and data.get("src"):
            self.refs.append(data["src"])
            return

        if tag == "link" and data.get("href"):
            rel = set(data.get("rel", "").lower().split())
            if rel & {"stylesheet", "icon", "apple-touch-icon", "preload"}:
                self.refs.append(data["href"])
            return

        if tag == "meta":
            key = (data.get("property") or data.get("name") or "").lower()
            if key in {"og:image", "twitter:image"} and data.get("content"):
                self.refs.append(data["content"])


def env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise SystemExit(f"{name} must be an integer, got {raw!r}")
    if value < minimum:
        raise SystemExit(f"{name} must be >= {minimum}, got {value}")
    return value


def source_path_for_public_url(url: str) -> Path:
    path = urlparse(url).path
    if path in {"", "/"}:
        return SITE / "index.html"
    return SITE / f"{path.strip('/')}.html"


def normalize_asset_url(raw: str, base_url: str) -> str | None:
    raw = raw.strip()
    if not raw or raw.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
        return None

    absolute = urljoin(base_url, raw)
    parsed = urlparse(absolute)
    if parsed.scheme != "https" or parsed.netloc not in {"outpost.com.ua", "www.outpost.com.ua"}:
        return None

    path = parsed.path or "/"
    if path.startswith(EXCLUDED_PREFIXES):
        return None

    if Path(path).suffix.lower() not in STATIC_EXTENSIONS:
        return None

    canonical = f"{ORIGIN}{path}"
    if parsed.query:
        canonical += f"?{parsed.query}"
    return canonical


def sitemap_urls() -> list[str]:
    sitemap = SITE / "sitemap.xml"
    root = ET.fromstring(sitemap.read_text(encoding="utf-8"))
    return [
        elem.text.strip()
        for elem in root.iter()
        if elem.tag.endswith("loc") and elem.text and elem.text.strip()
    ]


def collect_public_assets() -> tuple[list[str], int, set[str]]:
    pages = sitemap_urls()
    assets: set[str] = set()
    demo_revalidate_assets: set[str] = set()
    local_css: set[Path] = set()

    for page in pages:
        source = source_path_for_public_url(page)
        if not source.is_file():
            raise SystemExit(f"missing source HTML for sitemap URL: {page} -> {source}")

        parser = AssetCollector()
        parser.feed(source.read_text(encoding="utf-8"))
        for raw in parser.refs:
            asset = normalize_asset_url(raw, page)
            if not asset:
                continue
            assets.add(asset)
            parsed = urlparse(asset)
            if Path(parsed.path).suffix.lower() == ".css":
                local_css.add(SITE / parsed.path.lstrip("/"))

    for css_path in sorted(local_css):
        if not css_path.is_file():
            raise SystemExit(f"referenced stylesheet has no local source file: {css_path}")

        css_text = css_path.read_text(encoding="utf-8")
        css_base = f"{ORIGIN}/{css_path.relative_to(SITE).as_posix()}"
        for _, raw in CSS_URL_RE.findall(css_text):
            asset = normalize_asset_url(raw, css_base)
            if asset:
                assets.add(asset)

    demo_source = SITE / "demo.html"
    if not demo_source.is_file():
        raise SystemExit("missing source HTML for online demo: site/demo.html")

    demo_parser = AssetCollector()
    demo_parser.feed(demo_source.read_text(encoding="utf-8"))
    for raw in demo_parser.refs:
        asset = normalize_asset_url(raw, f"{ORIGIN}/demo")
        if not asset:
            continue
        parsed = urlparse(asset)
        if parsed.path in DEMO_REVALIDATE_PATHS:
            assets.add(asset)
            demo_revalidate_assets.add(asset)

    discovered_demo_paths = {urlparse(url).path for url in demo_revalidate_assets}
    missing_demo_paths = sorted(DEMO_REVALIDATE_PATHS - discovered_demo_paths)
    if missing_demo_paths:
        raise SystemExit(
            "site/demo.html is missing required revalidated runtime asset(s): "
            + ", ".join(missing_demo_paths)
        )

    return sorted(assets), len(pages), demo_revalidate_assets


def probe_once(url: str) -> tuple[int, dict[str, str]]:
    opener = build_opener(NoRedirectHandler)
    request = Request(
        url,
        headers={
            "User-Agent": "OutPOSt-live-static-assets-verifier/1.0",
            "Cache-Control": "no-cache",
            "Accept": "*/*",
        },
    )

    try:
        with opener.open(request, timeout=20) as response:
            return response.status, {key.lower(): value for key, value in response.headers.items()}
    except HTTPError as exc:
        return exc.code, {key.lower(): value for key, value in exc.headers.items()}
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc


def verify_asset(url: str, attempts: int, delay_seconds: int) -> tuple[str | None, str]:
    last_problem = "unknown error"
    for attempt in range(1, attempts + 1):
        try:
            status, headers = probe_once(url)
        except RuntimeError as exc:
            last_problem = f"network error: {exc}"
        else:
            if 300 <= status < 400:
                last_problem = f"HTTP {status} redirect -> {headers.get('location', '-')}"
            elif status != 200:
                last_problem = f"expected HTTP 200, got {status}"
            else:
                suffix = Path(urlparse(url).path).suffix.lower()
                content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
                expected = EXPECTED_CONTENT_TYPES.get(suffix)
                if expected and content_type not in expected:
                    last_problem = (
                        f"content-type {content_type!r}; expected one of {sorted(expected)!r}"
                    )
                else:
                    cache_control = headers.get("cache-control", "(missing)")
                    return None, cache_control

        if attempt < attempts:
            time.sleep(delay_seconds)

    return last_problem, "(unavailable)"


def cache_control_revalidates(value: str) -> bool:
    tokens = {token.strip().lower() for token in value.split(",") if token.strip()}
    if "no-cache" in tokens:
        return True
    return "max-age=0" in tokens and "must-revalidate" in tokens


def main() -> int:
    attempts = env_int("OUTPOST_LIVE_ASSETS_ATTEMPTS", 4)
    delay_seconds = env_int("OUTPOST_LIVE_ASSETS_DELAY_SECONDS", 5, minimum=0)

    assets, page_count, demo_revalidate_assets = collect_public_assets()
    if not assets:
        print("OutPOSt live static assets verifier: FAIL")
        print("  - no public static assets were discovered from sitemap pages")
        return 1

    errors: list[str] = []
    cache_inventory: dict[str, int] = {}

    for url in assets:
        problem, cache_control = verify_asset(url, attempts, delay_seconds)
        if problem:
            errors.append(f"{url}: {problem}")
            continue
        cache_inventory[cache_control] = cache_inventory.get(cache_control, 0) + 1
        if url in demo_revalidate_assets and not cache_control_revalidates(cache_control):
            errors.append(
                f"{url}: online-demo runtime asset must revalidate; observed Cache-Control {cache_control!r}"
            )

    if errors:
        print(f"OutPOSt live static assets verifier: FAIL ({len(errors)} issue(s))")
        for item in errors:
            print(f"  - {item}")
        return 1

    print("OutPOSt live static assets verifier: PASS")
    print(
        f"  checked {len(assets)} unique public static assets derived from "
        f"{page_count} sitemap pages plus the /demo runtime contract"
    )
    print("  every asset returns direct HTTP 200 with the expected MIME type")
    print(f"  online-demo runtime assets with enforced live revalidation: {len(demo_revalidate_assets)}")
    print("  protected/backend and installer/download routes were excluded")
    print("  observed Cache-Control distribution (diagnostic only):")
    for value, count in sorted(cache_inventory.items(), key=lambda item: (-item[1], item[0])):
        print(f"    {count}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
