#!/usr/bin/env python3
"""Fail-closed validation for public HTML hash/fragment links.

Checks that every internal link containing ``#fragment`` points to an existing
``id`` (or legacy anchor ``name``) on the resolved public HTML target. Two
intentional dynamic contracts are recognized only when their runtime scripts
are present: the shared ``#top`` fallback and the public-question dialog trigger.
Standard-library only; does not call production services.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse
import posixpath
import sys


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PUBLIC_HOSTS = {"outpost.com.ua", "www.outpost.com.ua"}
TOP_FALLBACK_MARKER = 'if (!document.getElementById("top")) document.documentElement.id = "top";'


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: set[str] = set()
        self.hrefs: list[tuple[str, bool]] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        element_id = data.get("id", "").strip()
        if element_id:
            self.targets.add(element_id)

        tag = tag.lower()
        if tag == "a":
            name = data.get("name", "").strip()
            if name:
                self.targets.add(name)
            href = data.get("href", "").strip()
            if href:
                self.hrefs.append((href, "data-outpost-open-question" in data))
        elif tag == "script":
            src = data.get("src", "").strip()
            if src:
                self.scripts.append(src)


def route_to_html(path: str) -> str | None:
    if not path or path == "/":
        return "index.html"

    clean = path.lstrip("/")
    if not clean:
        return "index.html"

    suffix = PurePosixPath(clean).suffix.lower()
    if suffix and suffix != ".html":
        return None
    if suffix == ".html":
        return clean
    return f"{clean}.html"


def resolve_target(source_name: str, href: str) -> tuple[str, str] | None:
    parsed = urlparse(href)
    fragment = unquote(parsed.fragment).strip()
    if not fragment:
        return None

    if parsed.scheme or parsed.netloc:
        if parsed.scheme != "https" or parsed.netloc not in PUBLIC_HOSTS:
            return None
        target_name = route_to_html(parsed.path)
        if target_name is None:
            return None
        return target_name, fragment

    raw_path = parsed.path
    if not raw_path:
        return source_name, fragment

    if raw_path.startswith("/"):
        target_name = route_to_html(raw_path)
    else:
        source_dir = PurePosixPath(source_name).parent.as_posix()
        joined = posixpath.normpath(posixpath.join(source_dir, raw_path))
        target_name = route_to_html("/" + joined)

    if target_name is None:
        return None
    return target_name, fragment


def loads_shared_script(page: PageParser) -> bool:
    return any(urlparse(src).path.endswith("/script.js") or urlparse(src).path == "script.js" for src in page.scripts)


def loads_public_question_runtime(page: PageParser) -> bool:
    return any("outpost-public-question" in urlparse(src).path for src in page.scripts)


def main() -> int:
    pages: dict[str, PageParser] = {}
    for path in sorted(SITE.glob("*.html")):
        parser = PageParser()
        parser.feed(path.read_text(encoding="utf-8"))
        pages[path.name] = parser

    shared_script = SITE / "script.js"
    top_fallback_ready = shared_script.is_file() and TOP_FALLBACK_MARKER in shared_script.read_text(encoding="utf-8")

    errors: list[str] = []
    checked = 0
    dynamic_checked = 0
    for source_name, parser in pages.items():
        for href, public_question_trigger in parser.hrefs:
            resolved = resolve_target(source_name, href)
            if resolved is None:
                continue
            target_name, fragment = resolved
            checked += 1
            target = pages.get(target_name)
            if target is None:
                errors.append(
                    f"site/{source_name}: fragment link {href!r} resolves to missing site/{target_name}"
                )
                continue
            if fragment in target.targets:
                continue

            if fragment == "top" and top_fallback_ready and loads_shared_script(target):
                dynamic_checked += 1
                continue

            if (
                public_question_trigger
                and fragment == "outpost-question"
                and loads_public_question_runtime(parser)
            ):
                dynamic_checked += 1
                continue

            errors.append(
                f"site/{source_name}: fragment link {href!r} targets missing #{fragment} in site/{target_name}"
            )

    if errors:
        print(f"Internal anchor guard: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Internal anchor guard: PASS")
    print(f"  checked {checked} internal fragment link(s) across {len(pages)} HTML page(s)")
    print(f"  verified {dynamic_checked} intentional dynamic fragment target(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
