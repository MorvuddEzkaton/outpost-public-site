#!/usr/bin/env python3
"""Verify that every live public sitemap page exposes the canonical Cabinet link.

The verifier fetches only public `https://outpost.com.ua/...` pages. It inspects
HTML for the link but deliberately never requests `cabinet.outpost.com.ua` or
any protected API/Worker/D1 service.
"""

from __future__ import annotations

from html.parser import HTMLParser
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITEMAP = ROOT / "site" / "sitemap.xml"
PUBLIC_ORIGIN = "https://outpost.com.ua"
CANONICAL_CABINET = "https://cabinet.outpost.com.ua/"
ATTEMPTS = max(1, int(os.environ.get("OUTPOST_LIVE_CABINET_ATTEMPTS", "4")))
DELAY_SECONDS = max(0.0, float(os.environ.get("OUTPOST_LIVE_CABINET_DELAY_SECONDS", "5")))
USER_AGENT = "OutPOSt-Live-Cabinet-Entry-Guard/1.0"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[list[str]] = []
        self._active: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        data = {key.lower(): (value or "") for key, value in attrs}
        href = data.get("href", "").strip()
        if not href:
            return
        entry = [href, ""]
        self.links.append(entry)
        self._active = entry

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a":
            self._active = None

    def handle_data(self, data: str) -> None:
        if self._active is not None:
            self._active[1] += data


def sitemap_urls() -> list[str]:
    root = ET.parse(SITEMAP).getroot()
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    urls: list[str] = []
    for node in root.findall(f"{ns}url"):
        loc = node.find(f"{ns}loc")
        if loc is not None and loc.text:
            url = loc.text.strip()
            if not url.startswith(PUBLIC_ORIGIN):
                raise RuntimeError(f"unexpected sitemap origin: {url}")
            urls.append(url)
    return urls


def fetch_html(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(request, timeout=20) as response:
        status = getattr(response, "status", response.getcode())
        if status != 200:
            raise RuntimeError(f"HTTP {status}")
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            raise RuntimeError(f"unexpected Content-Type: {content_type or 'missing'}")
        return response.read().decode("utf-8", errors="strict")


def verify_once(urls: list[str]) -> list[str]:
    errors: list[str] = []
    for url in urls:
        try:
            html = fetch_html(url)
        except (HTTPError, URLError, TimeoutError, UnicodeError, RuntimeError) as exc:
            errors.append(f"{url}: fetch failed: {exc}")
            continue

        parser = LinkParser()
        parser.feed(html)
        cabinet_links = [(href, text.strip()) for href, text in parser.links if "cabinet.outpost.com.ua" in href]
        exact = [(href, text) for href, text in cabinet_links if href == CANONICAL_CABINET]
        wrong = [(href, text) for href, text in cabinet_links if href != CANONICAL_CABINET]

        if not exact:
            errors.append(f"{url}: canonical Cabinet link is missing")
        if wrong:
            rendered = ", ".join(repr(href) for href, _ in wrong)
            errors.append(f"{url}: non-canonical Cabinet link(s): {rendered}")
        if exact and not any("кабінет" in text.lower() for _, text in exact):
            errors.append(f"{url}: canonical Cabinet link has no visible 'Кабінет' label")
    return errors


def main() -> int:
    try:
        urls = sitemap_urls()
    except Exception as exc:
        print(f"Live Cabinet entry verifier: FAIL: {exc}", file=sys.stderr)
        return 1

    last_errors: list[str] = []
    for attempt in range(1, ATTEMPTS + 1):
        last_errors = verify_once(urls)
        if not last_errors:
            print("Live Cabinet entry verifier: PASS")
            print(f"  {len(urls)} public sitemap page(s) expose {CANONICAL_CABINET}")
            print("  only outpost.com.ua public pages were fetched")
            print("  Cabinet/Director/Sync APIs and D1 were not called")
            return 0

        print(
            f"Live Cabinet entry verifier: propagation mismatch on attempt {attempt}/{ATTEMPTS} "
            f"({len(last_errors)} issue(s))"
        )
        if attempt < ATTEMPTS and DELAY_SECONDS:
            time.sleep(DELAY_SECONDS)

    print(f"Live Cabinet entry verifier: FAIL ({len(last_errors)} issue(s))", file=sys.stderr)
    for error in last_errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
