#!/usr/bin/env python3
"""Fail closed on accidental public front-end payload bloat.

This is intentionally a coarse regression guard, not a Lighthouse score. It
checks sitemap HTML plus the first-party CSS/JS/images/fonts those pages load.
Download links (for example installers) are not initial page resources and are
therefore outside this budget.
"""

from __future__ import annotations

import posixpath
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"

KIB = 1024
MAX_HTML = 256 * KIB
MAX_CSS = 128 * KIB
MAX_JS = 128 * KIB
MAX_IMAGE = 512 * KIB
MAX_FONT = 256 * KIB
MAX_PAGE_PAYLOAD = 768 * KIB

CSS_EXTS = {".css"}
JS_EXTS = {".js", ".mjs"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".avif"}
FONT_EXTS = {".woff", ".woff2", ".ttf", ".otf"}
CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)


class ResourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.resources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {k.lower(): (v or "") for k, v in attrs}
        tag = tag.lower()

        if tag == "script" and data.get("src"):
            self.resources.append(data["src"])
        elif tag == "img" and data.get("src"):
            self.resources.append(data["src"])
            self._add_srcset(data.get("srcset", ""))
        elif tag == "source":
            if data.get("src"):
                self.resources.append(data["src"])
            self._add_srcset(data.get("srcset", ""))
        elif tag == "video" and data.get("poster"):
            self.resources.append(data["poster"])
        elif tag == "link" and data.get("href"):
            rel = {part.lower() for part in data.get("rel", "").split()}
            as_value = data.get("as", "").lower()
            if "stylesheet" in rel or "icon" in rel or ("preload" in rel and as_value in {"style", "script", "image", "font"}):
                self.resources.append(data["href"])

    def _add_srcset(self, value: str) -> None:
        for item in value.split(","):
            candidate = item.strip().split()
            if candidate:
                self.resources.append(candidate[0])


def human(size: int) -> str:
    return f"{size / KIB:.1f} KiB"


def sitemap_paths() -> list[str]:
    root = ET.parse(SITEMAP).getroot()
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    paths: list[str] = []
    for loc in root.findall("sm:url/sm:loc", ns):
        text = (loc.text or "").strip()
        parsed = urlsplit(text)
        path = parsed.path or "/"
        paths.append(path)
    if not paths:
        raise RuntimeError("sitemap contains no URLs")
    if len(paths) != len(set(paths)):
        raise RuntimeError("sitemap contains duplicate paths")
    return paths


def html_file_for(path: str) -> Path:
    if path == "/":
        return SITE / "index.html"
    clean = path.strip("/")
    return SITE / f"{clean}.html"


def local_resource_path(raw: str, page_path: str) -> Path | None:
    raw = raw.strip()
    if not raw or raw.startswith(("data:", "mailto:", "tel:", "javascript:", "#")):
        return None
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        return None

    base = "https://outpost.com.ua" + page_path
    resolved = urlsplit(urljoin(base, raw)).path
    normalized = posixpath.normpath(resolved)
    if normalized.startswith("../") or normalized == "..":
        raise RuntimeError(f"resource escapes site root: {raw!r}")
    return SITE / normalized.lstrip("/")


def limit_for(path: Path) -> tuple[int | None, str]:
    suffix = path.suffix.lower()
    if suffix in CSS_EXTS:
        return MAX_CSS, "CSS"
    if suffix in JS_EXTS:
        return MAX_JS, "JS"
    if suffix in IMAGE_EXTS:
        return MAX_IMAGE, "image"
    if suffix in FONT_EXTS:
        return MAX_FONT, "font"
    return None, "resource"


def css_dependencies(css_path: Path, page_path: str) -> list[Path]:
    text = css_path.read_text(encoding="utf-8")
    deps: list[Path] = []
    css_url = "/" + css_path.relative_to(SITE).as_posix()
    css_base = posixpath.dirname(css_url) + "/"
    for _, raw in CSS_URL_RE.findall(text):
        raw = raw.strip()
        if not raw or raw.startswith(("data:", "#")):
            continue
        dep = local_resource_path(raw, css_base)
        if dep is not None:
            deps.append(dep)
    return deps


def main() -> int:
    errors: list[str] = []
    paths = sitemap_paths()
    largest_by_kind: dict[str, tuple[int, Path]] = {}
    worst_page = (0, "")

    for page_path in paths:
        html_path = html_file_for(page_path)
        if not html_path.is_file():
            errors.append(f"{page_path}: missing HTML file {html_path.relative_to(ROOT)}")
            continue

        html_size = html_path.stat().st_size
        if html_size > MAX_HTML:
            errors.append(f"{page_path}: HTML {human(html_size)} exceeds {human(MAX_HTML)}")
        largest_by_kind["HTML"] = max(largest_by_kind.get("HTML", (0, html_path)), (html_size, html_path), key=lambda x: x[0])

        parser = ResourceParser()
        parser.feed(html_path.read_text(encoding="utf-8"))

        resources: set[Path] = set()
        queue: list[Path] = []
        for raw in parser.resources:
            resource = local_resource_path(raw, page_path)
            if resource is not None:
                queue.append(resource)

        while queue:
            resource = queue.pop()
            if resource in resources:
                continue
            resources.add(resource)
            if not resource.is_file():
                errors.append(f"{page_path}: missing local resource {resource.relative_to(ROOT)}")
                continue

            size = resource.stat().st_size
            limit, kind = limit_for(resource)
            if limit is not None and size > limit:
                errors.append(
                    f"{page_path}: {kind} {resource.relative_to(SITE)} is {human(size)}, exceeds {human(limit)}"
                )
            previous = largest_by_kind.get(kind)
            if previous is None or size > previous[0]:
                largest_by_kind[kind] = (size, resource)

            if resource.suffix.lower() == ".css":
                try:
                    queue.extend(css_dependencies(resource, page_path))
                except UnicodeDecodeError:
                    errors.append(f"{page_path}: CSS is not UTF-8: {resource.relative_to(ROOT)}")

        payload = html_size + sum(p.stat().st_size for p in resources if p.is_file())
        if payload > MAX_PAGE_PAYLOAD:
            errors.append(
                f"{page_path}: first-party page payload {human(payload)} exceeds {human(MAX_PAGE_PAYLOAD)}"
            )
        if payload > worst_page[0]:
            worst_page = (payload, page_path)

    if errors:
        print("PUBLIC ASSET BUDGET: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        f"PUBLIC ASSET BUDGET: PASS — {len(paths)} sitemap pages; "
        f"worst first-party payload {human(worst_page[0])} on {worst_page[1]}"
    )
    for kind in ("HTML", "CSS", "JS", "image", "font"):
        item = largest_by_kind.get(kind)
        if item:
            size, path = item
            print(f"- largest {kind}: {human(size)} — {path.relative_to(SITE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
