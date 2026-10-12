#!/usr/bin/env python3
"""Static accessibility/HTML integrity checks for OutPOSt public pages.

This validator is intentionally conservative: it checks structural issues that can be
verified from source without a browser or accessibility tree. It does not claim WCAG
conformance and does not call production services.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
FOOTER_BRAND_RE = re.compile(
    r'<a\b[^>]*class="[^"]*\bfooter-brand\b[^"]*"[^>]*>.*?</a>',
    re.IGNORECASE | re.DOTALL,
)
REDUNDANT_FOOTER_IMG_RE = re.compile(r'<img\b[^>]*\balt="OutPOSt"', re.IGNORECASE)
VISIBLE_BRAND_RE = re.compile(r'<span>\s*OutPOSt\s*</span>', re.IGNORECASE)
VERIFICATION_HTML_RE = re.compile(r"^google[a-z0-9_-]+\.html$", re.IGNORECASE)


@dataclass
class Control:
    tag: str
    control_type: str
    control_id: str
    aria_label: str
    aria_labelledby: str
    inside_label: bool
    line: int


class AccessibilityParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[tuple[str, int]] = []
        self.html_lang: str | None = None
        self.main_count = 0
        self.h1_count = 0
        self.title_count = 0
        self.title_text: list[str] = []
        self._in_title = False
        self._label_depth = 0
        self._form_depth = 0
        self.labels_for: set[str] = set()
        self.controls: list[Control] = []
        self.images_missing_alt: list[int] = []
        self.blank_links_without_noopener: list[int] = []
        self.form_buttons_without_type: list[int] = []
        self.skip_targets: list[tuple[str, int]] = []
        self.breadcrumb_trails: list[tuple[str, str, int, int]] = []
        self._breadcrumb_depth = 0
        self._breadcrumb_tag = ""
        self._breadcrumb_label = ""
        self._breadcrumb_current_count = 0
        self._breadcrumb_line = 0

    @staticmethod
    def attrs_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.lower(): (value or "") for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        data = self.attrs_dict(attrs)
        line, _ = self.getpos()

        element_id = data.get("id", "").strip()
        if element_id:
            self.ids.append((element_id, line))

        if tag == "html" and self.html_lang is None:
            self.html_lang = data.get("lang", "").strip().lower()
        elif tag == "main":
            self.main_count += 1
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "title":
            self.title_count += 1
            self._in_title = True
        elif tag == "label":
            self._label_depth += 1
            target = data.get("for", "").strip()
            if target:
                self.labels_for.add(target)
        elif tag == "form":
            self._form_depth += 1

        if tag == "img" and "alt" not in data:
            self.images_missing_alt.append(line)

        if tag == "a" and data.get("target", "").lower() == "_blank":
            rel_tokens = {token.lower() for token in data.get("rel", "").split()}
            if "noopener" not in rel_tokens:
                self.blank_links_without_noopener.append(line)

        classes = {token for token in data.get("class", "").split() if token}

        if self._breadcrumb_depth:
            self._breadcrumb_depth += 1
            if data.get("aria-current", "").strip().lower() == "page":
                self._breadcrumb_current_count += 1
        elif classes.intersection({"crumbs", "breadcrumbs"}):
            self._breadcrumb_depth = 1
            self._breadcrumb_tag = tag
            self._breadcrumb_label = data.get("aria-label", "").strip()
            self._breadcrumb_current_count = (
                1 if data.get("aria-current", "").strip().lower() == "page" else 0
            )
            self._breadcrumb_line = line

        if tag == "a" and "skip-link" in classes:
            href = data.get("href", "").strip()
            if href.startswith("#") and len(href) > 1:
                self.skip_targets.append((href[1:], line))

        if tag in {"input", "select", "textarea"}:
            control_type = data.get("type", "").strip().lower() if tag == "input" else tag
            if control_type not in {"hidden", "submit", "button", "reset", "image"}:
                self.controls.append(
                    Control(
                        tag=tag,
                        control_type=control_type,
                        control_id=element_id,
                        aria_label=data.get("aria-label", "").strip(),
                        aria_labelledby=data.get("aria-labelledby", "").strip(),
                        inside_label=self._label_depth > 0,
                        line=line,
                    )
                )

        if tag == "button" and self._form_depth > 0 and not data.get("type", "").strip():
            self.form_buttons_without_type.append(line)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if self._breadcrumb_depth:
            if self._breadcrumb_depth == 1 and tag == self._breadcrumb_tag:
                self.breadcrumb_trails.append(
                    (
                        self._breadcrumb_tag,
                        self._breadcrumb_label,
                        self._breadcrumb_current_count,
                        self._breadcrumb_line,
                    )
                )
                self._breadcrumb_depth = 0
                self._breadcrumb_tag = ""
                self._breadcrumb_label = ""
                self._breadcrumb_current_count = 0
                self._breadcrumb_line = 0
            elif self._breadcrumb_depth > 1:
                self._breadcrumb_depth -= 1

        if tag == "title":
            self._in_title = False
        elif tag == "label" and self._label_depth > 0:
            self._label_depth -= 1
        elif tag == "form" and self._form_depth > 0:
            self._form_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title and data.strip():
            self.title_text.append(data.strip())


def validate_page(path: Path) -> list[str]:
    errors: list[str] = []
    parser = AccessibilityParser()
    try:
        source = path.read_text(encoding="utf-8")
        parser.feed(source)
        parser.close()
    except Exception as exc:
        return [f"site/{path.name}: HTML parser error: {exc}"]

    if parser.html_lang != "uk":
        errors.append(f"site/{path.name}: <html lang> must be 'uk', got {parser.html_lang!r}")

    if parser.main_count != 1:
        errors.append(f"site/{path.name}: expected exactly one <main>, got {parser.main_count}")

    if parser.h1_count < 1:
        errors.append(f"site/{path.name}: missing <h1>")

    if parser.title_count != 1 or not " ".join(parser.title_text).strip():
        errors.append(f"site/{path.name}: expected one non-empty <title>, got count={parser.title_count}")

    counts = Counter(value for value, _ in parser.ids)
    for duplicate in sorted(value for value, count in counts.items() if count > 1):
        lines = [str(line) for value, line in parser.ids if value == duplicate]
        errors.append(f"site/{path.name}: duplicate id={duplicate!r} at lines {', '.join(lines)}")

    all_ids = {value for value, _ in parser.ids}
    for target, line in parser.skip_targets:
        if target not in all_ids:
            errors.append(f"site/{path.name}:{line}: skip-link target #{target} does not exist")

    for line in parser.images_missing_alt:
        errors.append(f"site/{path.name}:{line}: <img> is missing an alt attribute")

    for match in FOOTER_BRAND_RE.finditer(source):
        block = match.group(0)
        if REDUNDANT_FOOTER_IMG_RE.search(block) and VISIBLE_BRAND_RE.search(block):
            line = source.count("\n", 0, match.start()) + 1
            errors.append(
                f"site/{path.name}:{line}: footer brand logo alt duplicates visible OutPOSt text; use alt=''"
            )

    for line in parser.blank_links_without_noopener:
        errors.append(f"site/{path.name}:{line}: target='_blank' link is missing rel='noopener'")

    for line in parser.form_buttons_without_type:
        errors.append(f"site/{path.name}:{line}: <button> inside a form must declare type explicitly")

    for tag, aria_label, current_count, line in parser.breadcrumb_trails:
        if tag != "nav":
            errors.append(
                f"site/{path.name}:{line}: breadcrumb trail must use <nav>, got <{tag}>"
            )
        if aria_label != "Навігаційний ланцюжок":
            errors.append(
                f"site/{path.name}:{line}: breadcrumb nav must use "
                "aria-label='Навігаційний ланцюжок'"
            )
        if current_count != 1:
            errors.append(
                f"site/{path.name}:{line}: breadcrumb nav must contain exactly one "
                f"aria-current='page', got {current_count}"
            )

    for control in parser.controls:
        labeled = (
            control.inside_label
            or bool(control.aria_label)
            or bool(control.aria_labelledby)
            or (bool(control.control_id) and control.control_id in parser.labels_for)
        )
        if not labeled:
            descriptor = f"{control.tag} type={control.control_type!r}" if control.tag == "input" else control.tag
            errors.append(
                f"site/{path.name}:{control.line}: {descriptor} has no label/aria-label/aria-labelledby"
            )

    return errors


def main() -> int:
    all_html = sorted(SITE.glob("*.html"))
    pages = [path for path in all_html if not VERIFICATION_HTML_RE.fullmatch(path.name)]
    errors: list[str] = []
    for path in pages:
        errors.extend(validate_page(path))

    unique = list(dict.fromkeys(errors))
    if unique:
        print(f"OutPOSt accessibility/static HTML guard: FAIL ({len(unique)} issue(s))")
        for item in unique:
            print(f"  - {item}")
        return 1

    print("OutPOSt accessibility/static HTML guard: PASS")
    print(f"  checked {len(pages)} public HTML page(s)")
    print(f"  skipped {len(all_html) - len(pages)} Google verification file(s) that must remain exact non-page payloads")
    print("  lang/main/h1/title, duplicate IDs, image alt, redundant footer alt, skip targets, form labels and _blank rel contracts are valid")
    print("  breadcrumb trails use semantic nav labels with exactly one aria-current=page marker")
    return 0


if __name__ == "__main__":
    sys.exit(main())
