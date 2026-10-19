#!/usr/bin/env python3
"""Reject third-party browser subresources in public source.

External navigation links are intentionally allowed. This guard only covers
resources that a browser would load as part of rendering/executing a page
(scripts, styles, images, media, frames, preload targets and CSS url/import).
The public site's CSP is already strict; this guard prevents bad source from
relying on CSP blocking at runtime.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PUBLIC_HOST = "outpost.com.ua"

CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
CSS_IMPORT_RE = re.compile(
    r"@import\s+(?:url\(\s*)?(['\"]?)([^'\"\)\s;]+)\1\s*\)?",
    re.IGNORECASE,
)


# The legacy smoke check already validates normal a/img/script/link paths.
# This closes its remaining static-asset blind spots: srcset, video posters,
# media/source tags, font files, and CSS url()/@import resources.
STATIC_ASSET_SUFFIXES = {
    ".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico",
    ".avif", ".gif", ".woff", ".woff2", ".ttf", ".otf", ".mp4",
    ".webm", ".ogg", ".mp3", ".wav", ".pdf",
}


def local_static_target(source: Path, raw: str, site_root: Path = SITE) -> Path | None:
    """Resolve an expected *static* first-party resource, without fetching it."""
    value = raw.strip()
    if not value or value.startswith(("#", "data:", "blob:")):
        return None

    parsed = urlsplit("https:" + value if value.startswith("//") else value)
    if parsed.scheme and parsed.scheme != "https":
        return None
    if parsed.netloc and parsed.netloc.lower() != PUBLIC_HOST:
        return None

    url_path = unquote(parsed.path)
    if not url_path or Path(url_path).suffix.lower() not in STATIC_ASSET_SUFFIXES:
        return None

    root = site_root.resolve()
    target = (root / url_path.lstrip("/")) if url_path.startswith("/") else (source.parent / url_path)
    return target.resolve()


def check_local_static_resource(
    source: Path, context: str, raw: str, errors: list[str], site_root: Path = SITE
) -> None:
    """Fail closed on broken or escaping same-origin static asset references."""
    target = local_static_target(source, raw, site_root)
    if target is None:
        return
    root = site_root.resolve()
    if not target.is_relative_to(root):
        errors.append(f"{source}: {context} escapes public site root: {raw}")
    elif not target.is_file():
        errors.append(f"{source}: missing local asset in {context}: {raw}")


def split_srcset(value: str) -> list[str]:
    out: list[str] = []
    for item in value.split(","):
        candidate = item.strip().split()
        if candidate:
            out.append(candidate[0])
    return out


def is_forbidden_external(raw: str) -> bool:
    value = raw.strip()
    if not value or value.startswith(("#", "data:", "blob:")):
        return False

    if value.startswith("//"):
        parsed = urlsplit("https:" + value)
        return parsed.netloc.lower() != PUBLIC_HOST

    parsed = urlsplit(value)
    if not parsed.scheme and not parsed.netloc:
        return False

    if parsed.scheme not in {"http", "https"}:
        return True

    return parsed.scheme != "https" or parsed.netloc.lower() != PUBLIC_HOST


class ResourceCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.resources: list[tuple[str, str]] = []

    def add(self, context: str, value: str) -> None:
        if value:
            self.resources.append((context, value))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        data = {key.lower(): (value or "") for key, value in attrs}

        if tag == "script":
            self.add("script[src]", data.get("src", ""))
            return

        if tag == "img":
            self.add("img[src]", data.get("src", ""))
            for value in split_srcset(data.get("srcset", "")):
                self.add("img[srcset]", value)
            return

        if tag == "source":
            self.add("source[src]", data.get("src", ""))
            for value in split_srcset(data.get("srcset", "")):
                self.add("source[srcset]", value)
            return

        if tag in {"audio", "video"}:
            self.add(f"{tag}[src]", data.get("src", ""))
            if tag == "video":
                self.add("video[poster]", data.get("poster", ""))
            return

        if tag == "iframe":
            self.add("iframe[src]", data.get("src", ""))
            return

        if tag == "embed":
            self.add("embed[src]", data.get("src", ""))
            return

        if tag == "object":
            self.add("object[data]", data.get("data", ""))
            return

        if tag == "link" and data.get("href"):
            rel = {part.lower() for part in data.get("rel", "").split()}
            resource_rels = {
                "stylesheet",
                "icon",
                "apple-touch-icon",
                "preload",
                "modulepreload",
                "prefetch",
                "preconnect",
                "dns-prefetch",
            }
            if rel & resource_rels:
                self.add(f"link[rel={' '.join(sorted(rel))}]", data["href"])


def check_html(errors: list[str]) -> int:
    count = 0
    for path in sorted(SITE.glob("*.html")):
        count += 1
        parser = ResourceCollector()
        parser.feed(path.read_text(encoding="utf-8"))
        for context, value in parser.resources:
            if is_forbidden_external(value):
                errors.append(
                    f"site/{path.name}: third-party browser resource in {context}: {value}"
                )
            else:
                check_local_static_resource(path, context, value, errors)
    return count


def check_css(errors: list[str]) -> int:
    count = 0
    css_files = sorted(SITE.rglob("*.css"))
    for path in css_files:
        count += 1
        text = path.read_text(encoding="utf-8")
        values: list[tuple[str, str]] = []
        values.extend(("url()", match[1].strip()) for match in CSS_URL_RE.findall(text))
        values.extend(("@import", match[1].strip()) for match in CSS_IMPORT_RE.findall(text))

        for context, value in values:
            if is_forbidden_external(value):
                errors.append(
                    f"{path.relative_to(ROOT).as_posix()}: third-party browser resource in {context}: {value}"
                )
            else:
                check_local_static_resource(path, context, value, errors)
    return count


def main() -> int:
    errors: list[str] = []
    html_count = check_html(errors)
    css_count = check_css(errors)

    unique = list(dict.fromkeys(errors))
    if unique:
        print(f"FIRST-PARTY RESOURCE GUARD: FAIL ({len(unique)} issue(s))")
        for error in unique:
            print(f"- {error}")
        return 1

    print(
        "FIRST-PARTY RESOURCE GUARD: PASS — "
        f"{html_count} HTML files and {css_count} CSS files contain no third-party browser subresources or missing local static assets"
    )
    print("  external navigation links are outside this guard")
    print("  source does not depend on CSP to block third-party scripts/styles/images/media/frames")
    print("  srcset, poster, CSS url()/@import and other first-party static assets resolve inside site/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
