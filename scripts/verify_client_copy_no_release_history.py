#!/usr/bin/env python3
"""Prevent release-history language from leaking into ordinary customer-facing copy.

Version-oriented pages are intentionally excluded:
- /download
- /changelog

The guard scans visible body text, marketing metadata and accessibility text.
Technical structured data, asset paths, CSS build ids and download filenames are
not treated as customer copy.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

ALLOWED_VERSION_PAGES = {"download.html", "changelog.html"}
SKIP_FILES = {"google2c445dfee2b7ddee.html"}

HISTORY_PATTERNS = (
    re.compile(r"актуалізован\w*\s+для\s+v?\d", re.IGNORECASE),
    re.compile(r"розвива\w*\s+(?:від|з)\s+v?\d", re.IGNORECASE),
    re.compile(r"(?:у|в|з|від|до)\s+v\d+\.\d+", re.IGNORECASE),
    re.compile(r"перш\w+\s+функціональн\w+\s+етап", re.IGNORECASE),
    re.compile(r"поточн\w+\s+реліз", re.IGNORECASE),
    re.compile(r"\bреліз\w*\b", re.IGNORECASE),
    re.compile(r"історичн\w+\s+fefo[-‑–— ]*етап", re.IGNORECASE),
    re.compile(r"історичні\s+межі\s+показаного", re.IGNORECASE),
    re.compile(r"початков\w+\s+fefo[-‑–— ]*цикл", re.IGNORECASE),
    re.compile(r"\bmilestone(?:-версі\w*)?\b", re.IGNORECASE),
    re.compile(r"релізн\w+\s+цикл", re.IGNORECASE),
    re.compile(r"на\s+якому\s+етапі\b", re.IGNORECASE),
    re.compile(r"\bцей\s+етап\b", re.IGNORECASE),
    re.compile(r"окрем\w+\s+етап", re.IGNORECASE),
    re.compile(r"\bетап\s+\d+\b", re.IGNORECASE),
)

MARKETING_META = {
    "description",
    "og:title",
    "og:description",
    "twitter:title",
    "twitter:description",
}
ACCESSIBILITY_ATTRS = {"alt", "aria-label", "title"}


class CopyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_body = False
        self.skip_depth = 0
        self.in_title = False
        self.items: list[tuple[str, str]] = []

    @staticmethod
    def clean(value: str | None) -> str:
        return " ".join((value or "").split())

    def add(self, kind: str, value: str | None) -> None:
        text = self.clean(value)
        if text:
            self.items.append((kind, text))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if tag == "body":
            self.in_body = True
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = data.get("name") or data.get("property")
            if key in MARKETING_META:
                self.add(f"meta:{key}", data.get("content"))
        if self.in_body and not self.skip_depth:
            for key in ACCESSIBILITY_ATTRS:
                if key in data:
                    self.add(f"attr:{key}", data.get(key))

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self.in_title = False
        if tag == "body":
            self.in_body = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.add("title", data)
        if self.in_body and not self.skip_depth:
            self.add("visible", data)


def violations(text: str) -> list[str]:
    reasons: list[str] = []
    for pattern in HISTORY_PATTERNS:
        if pattern.search(text):
            reasons.append(f"development-history wording /{pattern.pattern}/")
    return reasons


def validate_html(path: Path) -> list[str]:
    if path.name in ALLOWED_VERSION_PAGES or path.name in SKIP_FILES:
        return []
    parser = CopyParser()
    parser.feed(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for kind, text in parser.items:
        key = (kind, text)
        if key in seen:
            continue
        seen.add(key)
        for reason in violations(text):
            errors.append(f"{path.relative_to(ROOT)} [{kind}]: {reason}: {text!r}")
    return errors


def validate_runtime_copy() -> list[str]:
    errors: list[str] = []
    for name in ("_telegram-faq.js", "script.js"):
        path = SITE / name
        text = path.read_text(encoding="utf-8")
        for pattern in HISTORY_PATTERNS:
            for match in pattern.finditer(text):
                start = max(0, match.start() - 90)
                end = min(len(text), match.end() + 160)
                context = " ".join(text[start:end].split())
                errors.append(
                    f"{path.relative_to(ROOT)}: development-history wording /{pattern.pattern}/ in runtime customer copy: {context!r}"
                )
    return errors


def main() -> int:
    errors: list[str] = []
    checked = 0
    for path in sorted(SITE.glob("*.html")):
        if path.name in SKIP_FILES:
            continue
        errors.extend(validate_html(path))
        checked += 1
    errors.extend(validate_runtime_copy())

    if errors:
        print(f"Client copy release-history guard: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Client copy release-history guard: PASS")
    print(f"  public HTML files checked: {checked}")
    print("  /download and /changelog are explicit release-history exceptions")
    print("  visible text, marketing metadata and accessibility text are covered")
    print("  runtime FAQ/injected copy is checked for development-history wording")
    print("  technical structured data, assets and download filenames are intentionally out of scope")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
