#!/usr/bin/env python3
"""Require every public sitemap page to expose the Support Center directly.

Read-only guard. It parses site/sitemap.xml, maps each public URL to its static
HTML source and requires a native link to the matching language Support Center. It does not call production,
Cabinet, Worker APIs, D1, Director, Sync, PRRO or fiscal services.
"""

from __future__ import annotations

from pathlib import Path
from html.parser import HTMLParser
import sys
import re
from urllib.parse import urlparse
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
def support_target(url: str) -> str:
    path = urlparse(url).path
    return "/en/support" if path == "/en" or path.startswith("/en/") else "/support"


class SupportLinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: set[str] = set()

    def handle_starttag(self, tag, attrs) -> None:
        values = dict(attrs)
        if tag == "a" and "data-site-language" not in values and values.get("href"):
            self.links.add(values["href"])


def has_support_link(url: str, html: str) -> bool:
    collector = SupportLinkCollector()
    collector.feed(html)
    return support_target(url) in collector.links


def check_contract() -> None:
    root = "https://outpost.com.ua"
    cases = (
        ("/", '<a href="/support">Підтримка</a>', True),
        ("/download", '<a href="/en/support">Support</a>', False),
        ("/en", '<a href="/en/support">Support</a>', True),
        ("/en/features", '<a href="/support">Support (Ukrainian)</a>', False),
        ("/en/support", '<a href="/en/support" aria-current="page">Support</a>', True),
        ("/en/support", '<a href="/en/support" data-site-language="en">English</a>', False),
        ("/en/lite", '<!-- <a href="/en/support">Support</a> -->', False),
        ("/en/lite", '<script>const x = \'href="/en/support"\';</script>', False),
        ("/en/lite", '<a href="/en/support-extra">Support</a>', False),
    )
    for path, html, expected in cases:
        if has_support_link(root + path, html) != expected:
            raise GuardError(f"Support Center locale contract failed: {path} {html!r}")



class GuardError(RuntimeError):
    pass


def sitemap_pages() -> list[tuple[str, Path]]:
    try:
        root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        raise GuardError(f"cannot parse site/sitemap.xml: {exc}") from exc

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    pages: list[tuple[str, Path]] = []
    seen: set[str] = set()

    for url_node in root.findall("sm:url", ns):
        loc_node = url_node.find("sm:loc", ns)
        loc = (loc_node.text or "").strip() if loc_node is not None else ""
        if not loc:
            raise GuardError("sitemap contains an entry without loc")
        if loc in seen:
            raise GuardError(f"duplicate sitemap URL: {loc}")
        seen.add(loc)

        parsed = urlparse(loc)
        if parsed.scheme != "https" or parsed.netloc != "outpost.com.ua":
            raise GuardError(f"unexpected sitemap URL host: {loc}")
        if parsed.query or parsed.fragment:
            raise GuardError(f"sitemap URL must not contain query/fragment: {loc}")

        path = parsed.path or "/"
        if path == "/":
            html_path = SITE / "index.html"
        else:
            slug = path.strip("/")
            if not re.fullmatch(r"(?:[a-z0-9-]+|en/[a-z0-9-]+)", slug) or path != "/" + slug:
                raise GuardError(f"unsupported sitemap path shape: {loc}")
            html_path = SITE / f"{slug}.html"

        if not html_path.is_file():
            raise GuardError(f"missing static source for {loc}: {html_path.relative_to(ROOT)}")
        pages.append((loc, html_path))

    if not pages:
        raise GuardError("sitemap contains no public pages")
    return pages


def main() -> int:
    try:
        check_contract()
        pages = sitemap_pages()
        missing: list[str] = []

        for loc, html_path in pages:
            html = html_path.read_text(encoding="utf-8")
            if not has_support_link(loc, html):
                missing.append(f"{loc} ({html_path.relative_to(ROOT)}): expected {support_target(loc)}")

        if missing:
            print(f"Support Center discovery guard: FAIL ({len(missing)} page(s))", file=sys.stderr)
            for item in missing:
                print(f"  - missing direct localized support link: {item}", file=sys.stderr)
            return 1

        print("Support Center discovery guard: PASS")
        print(f"  sitemap pages with direct locale-matched support discovery: {len(pages)}/{len(pages)}")
        print("  protected application services were not called")
        return 0

    except GuardError as exc:
        print("Support Center discovery guard: FAIL", file=sys.stderr)
        print(f"  - {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
