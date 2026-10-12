#!/usr/bin/env python3
"""Guard OutPOSt browser/site identity assets in source.

Read-only and standard-library only. The contract deliberately requires modern
icon links while allowing the legacy ``shortcut icon`` relation to be optional.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import struct
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

REQUIRED_ICON_LINKS = {
    ("icon", "192x192", "/favicon.png"),
    ("icon", "48x48", "/favicon-48.png"),
    ("apple-touch-icon", "180x180", "/apple-touch-icon.png"),
}

PNG_DIMENSIONS = {
    "/favicon.png": (192, 192),
    "/favicon-48.png": (48, 48),
    "/apple-touch-icon.png": (180, 180),
}

ROOT_ICON_PATHS = (*PNG_DIMENSIONS.keys(), "/favicon.ico")


class IconCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "link":
            return
        data = {key.lower(): (value or "") for key, value in attrs}
        rel = " ".join(data.get("rel", "").lower().split())
        if "icon" not in rel:
            return
        self.links.append((rel, data.get("sizes", "").lower(), data.get("href", "")))


def sitemap_urls() -> list[str]:
    root = ET.fromstring((SITE / "sitemap.xml").read_text(encoding="utf-8"))
    urls = [
        elem.text.strip()
        for elem in root.iter()
        if elem.tag.endswith("loc") and elem.text and elem.text.strip()
    ]
    if not urls:
        raise RuntimeError("site/sitemap.xml contains no URLs")
    if len(urls) != len(set(urls)):
        raise RuntimeError("site/sitemap.xml contains duplicate URLs")
    return urls


def html_path(url: str) -> Path:
    path = urlparse(url).path
    return SITE / ("index.html" if path in ("", "/") else path.strip("/") + ".html")


def collect_icons(text: str) -> set[tuple[str, str, str]]:
    parser = IconCollector()
    parser.feed(text)
    return set(parser.links)


def validate_required_links(url: str, text: str, errors: list[str]) -> None:
    links = collect_icons(text)
    missing = sorted(REQUIRED_ICON_LINKS - links)
    for rel, sizes, href in missing:
        errors.append(f"{url}: missing required {rel} {sizes} -> {href}")


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return struct.unpack(">II", data[16:24])


def validate_source_assets(errors: list[str]) -> None:
    for href, expected in PNG_DIMENSIONS.items():
        path = SITE / href.lstrip("/")
        if not path.is_file():
            errors.append(f"missing source icon: {path.relative_to(ROOT)}")
            continue
        data = path.read_bytes()
        actual = png_dimensions(data)
        if actual is None:
            errors.append(f"{path.relative_to(ROOT)}: invalid PNG signature/IHDR")
        elif actual != expected:
            errors.append(
                f"{path.relative_to(ROOT)}: expected {expected[0]}x{expected[1]}, got {actual[0]}x{actual[1]}"
            )

    ico = SITE / "favicon.ico"
    if not ico.is_file():
        errors.append("missing source icon: site/favicon.ico")
        return
    data = ico.read_bytes()
    if len(data) < 6 or data[:4] != b"\x00\x00\x01\x00":
        errors.append("site/favicon.ico: invalid ICO header")
        return
    count = int.from_bytes(data[4:6], "little")
    if count < 1 or len(data) < 6 + 16 * count:
        errors.append(f"site/favicon.ico: invalid ICO directory count/length ({count})")


def main() -> int:
    errors: list[str] = []
    try:
        urls = sitemap_urls()
    except Exception as exc:
        print(f"OutPOSt site identity guard: FAIL\n  - {exc}", file=sys.stderr)
        return 1

    for url in urls:
        path = html_path(url)
        if not path.is_file():
            errors.append(f"{url}: source HTML missing: {path.relative_to(ROOT)}")
            continue
        validate_required_links(url, path.read_text(encoding="utf-8"), errors)

    validate_source_assets(errors)

    if errors:
        print(f"OutPOSt site identity guard: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("OutPOSt site identity guard: PASS")
    print(f"  required modern icon links present on {len(urls)}/{len(urls)} sitemap pages")
    print("  PNG dimensions: 192x192, 48x48, 180x180")
    print("  root favicon.ico has a valid ICO directory")
    print("  legacy shortcut-icon relation is optional by design")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
