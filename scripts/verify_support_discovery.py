#!/usr/bin/env python3
"""Require every public sitemap page to expose the Support Center directly.

Read-only guard. It parses site/sitemap.xml, maps each public URL to its static
HTML source and requires an href="/support" marker. It does not call production,
Cabinet, Worker APIs, D1, Director, Sync, PRRO or fiscal services.
"""

from __future__ import annotations

from pathlib import Path
import sys
from urllib.parse import urlparse
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
SUPPORT_MARKER = 'href="/support"'


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
            if not slug or "/" in slug:
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
        pages = sitemap_pages()
        missing: list[str] = []

        for loc, html_path in pages:
            html = html_path.read_text(encoding="utf-8")
            if SUPPORT_MARKER not in html:
                missing.append(f"{loc} ({html_path.relative_to(ROOT)})")

        if missing:
            print(f"Support Center discovery guard: FAIL ({len(missing)} page(s))", file=sys.stderr)
            for item in missing:
                print(f"  - missing href=\"/support\": {item}", file=sys.stderr)
            return 1

        print("Support Center discovery guard: PASS")
        print(f"  sitemap pages with direct /support discovery: {len(pages)}/{len(pages)}")
        print("  protected application services were not called")
        return 0

    except GuardError as exc:
        print("Support Center discovery guard: FAIL", file=sys.stderr)
        print(f"  - {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
