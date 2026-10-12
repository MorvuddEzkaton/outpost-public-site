#!/usr/bin/env python3
"""Guard the public entry point to the customer Cabinet.

Every indexable public sitemap page must expose the exact canonical customer
Cabinet URL. This is a static source check only: it never calls the Cabinet,
Director, Sync API, D1 or any protected service.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
CANONICAL_CABINET = "https://cabinet.outpost.com.ua/"
PUBLIC_ORIGIN = "https://outpost.com.ua"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        data = {key.lower(): (value or "") for key, value in attrs}
        href = data.get("href", "").strip()
        if href:
            self.links.append((href, ""))

    def handle_data(self, data: str) -> None:
        if not self.links:
            return
        href, text = self.links[-1]
        self.links[-1] = (href, text + data)


def route_to_file(url: str) -> Path:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path == "/":
        return SITE / "index.html"
    return SITE / f"{path.strip('/')}.html"


def sitemap_urls() -> list[str]:
    root = ET.parse(SITEMAP).getroot()
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    urls: list[str] = []
    for node in root.findall(f"{namespace}url"):
        loc = node.find(f"{namespace}loc")
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls


def main() -> int:
    errors: list[str] = []
    checked = 0
    for url in sitemap_urls():
        if not url.startswith(PUBLIC_ORIGIN):
            errors.append(f"unexpected sitemap origin: {url}")
            continue
        path = route_to_file(url)
        if not path.is_file():
            errors.append(f"{url}: missing source file {path.relative_to(ROOT)}")
            continue

        parser = LinkParser()
        parser.feed(path.read_text(encoding="utf-8"))
        checked += 1

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

    if errors:
        print(f"Cabinet entry guard: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Cabinet entry guard: PASS")
    print(f"  {checked} sitemap page(s) expose the canonical customer Cabinet link")
    print("  canonical target: https://cabinet.outpost.com.ua/")
    print("  protected Cabinet/Director/Sync services were not called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
