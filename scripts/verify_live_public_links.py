#!/usr/bin/env python3
"""Read-only post-deploy crawl of public OutPOSt internal HTML links.

Targets are derived only from href values in source HTML mapped by site/sitemap.xml.
Protected/backend routes and file downloads are never probed.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import os
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
ORIGIN = "https://outpost.com.ua"
HOST = "outpost.com.ua"
USER_AGENT = "OutPOSt-Live-Public-Links-Verify/1.0"

PROTECTED_PREFIXES = ("/admin", "/api", "/downloads/", "/cdn-cgi/", "/functions/")
FILE_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".css", ".js",
    ".txt", ".xml", ".pdf", ".exe", ".zip",
)
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        href = data.get("href", "").strip()
        if href:
            self.hrefs.append(href)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


class VerifyError(RuntimeError):
    pass


def sitemap_urls() -> list[str]:
    try:
        root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        raise VerifyError(f"cannot parse site/sitemap.xml: {exc}") from exc
    urls = [
        node.text.strip()
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] == "loc" and node.text and node.text.strip()
    ]
    if not urls:
        raise VerifyError("site/sitemap.xml contains no public URLs")
    return urls


def source_file(url: str) -> Path:
    path = urlparse(url).path
    return SITE / ("index.html" if path in ("", "/") else path.strip("/") + ".html")


def collect_targets() -> tuple[dict[str, set[str]], set[str]]:
    targets: dict[str, set[str]] = {}
    skipped_protected: set[str] = set()

    for page_url in sitemap_urls():
        path = source_file(page_url)
        if not path.is_file():
            raise VerifyError(f"mapped source HTML is missing for {page_url}: {path.relative_to(ROOT)}")

        parser = LinkParser()
        parser.feed(path.read_text(encoding="utf-8"))
        for href in parser.hrefs:
            lower = href.lower()
            if lower.startswith(("mailto:", "tel:", "javascript:", "data:")) or href.startswith("#"):
                continue

            absolute = urljoin(page_url, href)
            parsed = urlparse(absolute)
            if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != HOST:
                continue

            public_path = parsed.path or "/"
            if public_path.startswith(PROTECTED_PREFIXES):
                skipped_protected.add(public_path)
                continue
            if public_path.lower().endswith(FILE_SUFFIXES):
                continue

            if parsed.scheme != "https":
                raise VerifyError(f"{page_url}: public internal HTML href uses non-HTTPS URL: {href}")

            clean = urlunparse(("https", HOST, public_path, "", parsed.query, ""))
            targets.setdefault(clean, set()).add(page_url)

    if not targets:
        raise VerifyError("no public internal HTML link targets were discovered")
    return targets, skipped_protected


def probe(url: str) -> tuple[int | None, str, str]:
    opener = build_opener(NoRedirect)
    request = Request(
        url,
        method="GET",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,*/*;q=0.1",
            "Range": "bytes=0-0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    try:
        with opener.open(request, timeout=20) as response:
            return int(response.status), response.headers.get("Location", ""), ""
    except HTTPError as exc:
        return int(exc.code), exc.headers.get("Location", ""), ""
    except (URLError, TimeoutError, OSError) as exc:
        return None, "", f"{type(exc).__name__}: {exc}"


def verify_once() -> tuple[int, int]:
    targets, skipped_protected = collect_targets()
    results: dict[str, tuple[int | None, str, str]] = {}

    with ThreadPoolExecutor(max_workers=min(10, len(targets))) as pool:
        futures = {pool.submit(probe, url): url for url in targets}
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    errors: list[str] = []
    for url in sorted(targets):
        status, location, error = results[url]
        refs = ", ".join(sorted(targets[url]))
        if error:
            errors.append(f"{url}: request error {error}; linked from {refs}")
        elif status in REDIRECT_STATUSES:
            errors.append(f"{url}: internal source link redirects with HTTP {status} to {location or '<missing Location>'}; linked from {refs}")
        elif status not in (200, 206):
            errors.append(f"{url}: expected direct HTTP 200/206, got {status}; linked from {refs}")

    if errors:
        raise VerifyError("; ".join(errors))

    print(f"  public sitemap pages parsed: {len(sitemap_urls())}")
    print(f"  unique public internal HTML targets: {len(targets)}")
    print("  redirects observed: 0")
    print(f"  protected/file paths skipped without requests: {len(skipped_protected)}")
    return len(targets), len(skipped_protected)


def main() -> int:
    attempts = max(1, int(os.environ.get("OUTPOST_LIVE_LINKS_ATTEMPTS", "4")))
    delay = max(0, int(os.environ.get("OUTPOST_LIVE_LINKS_DELAY_SECONDS", "5")))
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            verify_once()
            print("OutPOSt live public links verification: PASS")
            print("  all source-linked public HTML routes resolve directly without dead links or redirect hops")
            print("  protected services and installer/download files were not called")
            return 0
        except Exception as exc:
            last_error = exc
            print(f"Attempt {attempt}/{attempts}: {exc}")
            if attempt < attempts:
                time.sleep(delay)

    print(f"OutPOSt live public links verification: FAIL\n  - {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
