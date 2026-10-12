#!/usr/bin/env python3
"""Guard the static OutPOSt 404 page contract.

Read-only and standard-library only. This verifies the source 404 page stays a
non-indexable error document and is never promoted into the public sitemap.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ERROR_PAGE = SITE / "404.html"
SITEMAP = SITE / "sitemap.xml"
PUBLIC_404_URL = "https://outpost.com.ua/404"


class MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.robots: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        data = {key.lower(): (value or "") for key, value in attrs}
        if data.get("name", "").lower() == "robots":
            self.robots.append(data.get("content", ""))


def fail(errors: list[str]) -> int:
    print(f"404 source guard: FAIL ({len(errors)} issue(s))", file=sys.stderr)
    for item in errors:
        print(f"  - {item}", file=sys.stderr)
    return 1


def sitemap_urls() -> list[str]:
    root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    return [
        node.text.strip()
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] == "loc" and node.text and node.text.strip()
    ]


def main() -> int:
    errors: list[str] = []

    if not ERROR_PAGE.is_file():
        return fail(["site/404.html is missing"])
    if not SITEMAP.is_file():
        return fail(["site/sitemap.xml is missing"])

    text = ERROR_PAGE.read_text(encoding="utf-8")
    parser = MetaParser()
    parser.feed(text)

    if len(parser.robots) != 1:
        errors.append(f"site/404.html must contain exactly one meta robots tag; found {len(parser.robots)}")
    elif "noindex" not in parser.robots[0].lower():
        errors.append(f"site/404.html meta robots must contain noindex; got {parser.robots[0]!r}")

    if "Сторінку не знайдено" not in text:
        errors.append("site/404.html is missing the OutPOSt 'Сторінку не знайдено' marker")
    if 'href="/"' not in text and "href='/'" not in text:
        errors.append("site/404.html must retain a link back to the homepage")

    try:
        urls = sitemap_urls()
    except (OSError, ET.ParseError) as exc:
        errors.append(f"cannot parse site/sitemap.xml: {exc}")
        urls = []

    if PUBLIC_404_URL in urls or "https://outpost.com.ua/404.html" in urls:
        errors.append("404 error document must never appear in the public sitemap")

    if errors:
        return fail(errors)

    print("404 source guard: PASS")
    print("  site/404.html exists and contains exactly one noindex robots directive")
    print("  OutPOSt error marker and homepage recovery link are present")
    print("  404 error document is absent from the public sitemap")
    print("  protected services were not called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
