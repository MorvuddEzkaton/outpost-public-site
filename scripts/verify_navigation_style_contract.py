#!/usr/bin/env python3
"""Fail closed when a public page uses the shared nav-more markup without its CSS contract."""

from __future__ import annotations

from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
NAV_MORE_MARKER = "data-nav-more"
NAV_STYLE_RE = re.compile(
    r'<link\b[^>]*href=["\']/assets/outpost-seo-wave2-v02451\.css(?:\?[^"\']*)?["\'][^>]*>',
    re.IGNORECASE,
)


def resolve_source(url: str) -> Path:
    path = urlparse(url).path.strip("/")
    if not path:
        return SITE / "index.html"
    direct = SITE / f"{path}.html"
    if direct.is_file():
        return direct
    return SITE / path / "index.html"


def main() -> int:
    if not SITEMAP.is_file():
        print("Navigation style contract: FAIL (site/sitemap.xml missing)")
        return 1

    try:
        root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    except ET.ParseError as exc:
        print(f"Navigation style contract: FAIL (invalid sitemap XML: {exc})")
        return 1

    urls = [
        elem.text.strip()
        for elem in root.iter()
        if elem.tag.endswith("loc") and elem.text and elem.text.strip()
    ]
    errors: list[str] = []
    checked = 0

    for url in urls:
        source = resolve_source(url)
        if not source.is_file():
            errors.append(f"{url}: static source not found")
            continue
        text = source.read_text(encoding="utf-8")
        if NAV_MORE_MARKER not in text:
            continue
        checked += 1
        matches = NAV_STYLE_RE.findall(text)
        if len(matches) != 1:
            relative = source.relative_to(REPO_ROOT)
            errors.append(
                f"{relative}: uses {NAV_MORE_MARKER} but must include "
                f"/assets/outpost-seo-wave2-v02451.css exactly once; found {len(matches)}"
            )

    if checked == 0:
        errors.append("no sitemap page uses data-nav-more; shared navigation contract unexpectedly absent")

    if errors:
        print(f"Navigation style contract: FAIL ({len(errors)} issue(s))")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("Navigation style contract: PASS")
    print(f"  checked {checked} sitemap page(s) using shared nav-more markup")
    print("  each page includes the required shared navigation stylesheet exactly once")
    return 0


if __name__ == "__main__":
    sys.exit(main())
