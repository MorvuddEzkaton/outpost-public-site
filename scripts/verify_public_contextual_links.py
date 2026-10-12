#!/usr/bin/env python3
"""Guard contextual internal-link coverage across public sitemap pages."""

from __future__ import annotations

from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
PUBLIC_ORIGIN = "https://outpost.com.ua"
MIN_CONTEXTUAL_INLINKS = 3


class MainLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.main_depth = 0
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "main":
            self.main_depth += 1
            return
        if tag != "a" or self.main_depth <= 0:
            return
        data = {key.lower(): (value or "") for key, value in attrs}
        href = data.get("href", "").strip()
        if href:
            self.links.add(href)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "main" and self.main_depth > 0:
            self.main_depth -= 1


def clean_route(raw: str) -> str | None:
    if not raw:
        return None

    if raw.startswith(("mailto:", "tel:", "javascript:", "#")):
        return None

    if raw.startswith("/"):
        route = raw.split("#", 1)[0].split("?", 1)[0]
    else:
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            return None
        if parsed.netloc not in {"outpost.com.ua", "www.outpost.com.ua"}:
            return None
        route = parsed.path or "/"

    if route.endswith(".html"):
        route = route[:-5]
    if route != "/" and route.endswith("/"):
        route = route.rstrip("/")
    return route or "/"


def sitemap_pages(errors: list[str]) -> dict[str, Path]:
    try:
        root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        errors.append(f"site/sitemap.xml: cannot parse sitemap: {exc}")
        return {}

    pages: dict[str, Path] = {}
    for elem in root.iter():
        if not elem.tag.endswith("loc") or not elem.text:
            continue
        url = elem.text.strip()
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "outpost.com.ua":
            errors.append(f"site/sitemap.xml: unexpected URL outside public origin: {url}")
            continue
        route = parsed.path or "/"
        if route != "/" and route.endswith("/"):
            route = route.rstrip("/")
        target = SITE / ("index.html" if route == "/" else route.lstrip("/") + ".html")
        pages[route] = target

    if not pages:
        errors.append("site/sitemap.xml: no public pages found")
    return pages


def main() -> int:
    errors: list[str] = []
    pages = sitemap_pages(errors)
    routes = set(pages)
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = {}

    for source, path in sorted(pages.items()):
        if not path.is_file():
            errors.append(f"{source}: missing static target {path.relative_to(ROOT)}")
            continue

        parser = MainLinkParser()
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()

        targets: set[str] = set()
        for href in parser.links:
            target = clean_route(href)
            if target is None or target == source or target not in routes:
                continue
            targets.add(target)
            incoming[target].add(source)
        outgoing[source] = targets

    for route in sorted(routes):
        if route == "/":
            continue
        count = len(incoming.get(route, set()))
        if count < MIN_CONTEXTUAL_INLINKS:
            sources = ", ".join(sorted(incoming.get(route, set()))) or "none"
            errors.append(
                f"{route}: only {count} contextual sitemap inlink(s) inside <main>; "
                f"minimum is {MIN_CONTEXTUAL_INLINKS}; sources: {sources}"
            )

    unique_errors = list(dict.fromkeys(errors))
    if unique_errors:
        print(f"Public contextual-link guard: FAIL ({len(unique_errors)} issue(s))")
        for error in unique_errors:
            print(f"  - {error}")
        return 1

    weakest = sorted(
        (
            (len(incoming.get(route, set())), route)
            for route in routes
            if route != "/"
        )
    )

    print("Public contextual-link guard: PASS")
    print(f"  sitemap pages checked: {len(routes)}")
    print(f"  minimum contextual inlinks per non-home page: {MIN_CONTEXTUAL_INLINKS}")
    print("  weakest pages:")
    for count, route in weakest[:8]:
        print(f"    {count}: {route}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
