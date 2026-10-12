#!/usr/bin/env python3
"""Guard public call CTAs so desktop users see the phone number before tel: opens.

Plain visible phone-number links (for example in footers) remain direct tel: links.
Button-like call CTAs and links explicitly saying "Зателефонувати" are handled by the
shared site/script.js phone dialog first. The actual number inside that dialog is the
explicit tel: action.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SCRIPT = SITE / "script.js"
STYLES = SITE / "assets" / "phone-dialog.css"
SCRIPT_INCLUDE_RE = re.compile(
    r'<script\b[^>]*\bsrc=["\']/?script\.js(?:\?[^"\']*)?["\']',
    re.IGNORECASE,
)


class TelAnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict[str, object]] = []
        self.anchors: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        values = {key.lower(): (value or "") for key, value in attrs}
        href = values.get("href", "")
        if not href.lower().startswith("tel:"):
            return
        item: dict[str, object] = {
            "href": href,
            "class": values.get("class", ""),
            "text": [],
        }
        self.stack.append(item)

    def handle_data(self, data: str) -> None:
        if self.stack:
            text = self.stack[-1]["text"]
            assert isinstance(text, list)
            text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self.stack:
            return
        item = self.stack.pop()
        text_parts = item["text"]
        assert isinstance(text_parts, list)
        self.anchors.append({
            "href": str(item["href"]),
            "class": str(item["class"]),
            "text": " ".join("".join(text_parts).split()),
        })


def is_call_cta(anchor: dict[str, str]) -> bool:
    classes = set(anchor["class"].split())
    return "button" in classes or "зателефонувати" in anchor["text"].lower()


def fail(errors: list[str]) -> int:
    print(f"Phone CTA guard: FAIL ({len(errors)} issue(s))")
    for error in errors:
        print(f"  - {error}")
    return 1


def main() -> int:
    errors: list[str] = []
    call_ctas: list[str] = []
    cta_pages: set[str] = set()

    for path in sorted(SITE.glob("*.html")):
        content = path.read_text(encoding="utf-8")
        parser = TelAnchorParser()
        parser.feed(content)
        page_ctas = [anchor for anchor in parser.anchors if is_call_cta(anchor)]
        if not page_ctas:
            continue

        cta_pages.add(path.name)
        if not SCRIPT_INCLUDE_RE.search(content):
            errors.append(
                f"site/{path.name}: call CTA exists but shared script.js is not included; desktop tel: would bypass the dialog"
            )

        for anchor in page_ctas:
            call_ctas.append(f"site/{path.name}: {anchor['text'] or anchor['href']}")

    if not call_ctas:
        errors.append("no public call CTA was found; guard scope may have drifted")

    if not SCRIPT.is_file():
        errors.append("site/script.js is missing")
    else:
        script = SCRIPT.read_text(encoding="utf-8")
        required_script = {
            "CTA classifier": "isPhoneDialogTrigger",
            "button classifier": 'link.classList.contains("button")',
            "call-text classifier": "/зателефонувати/i",
            "tel selector": "a[href^=\"tel:\" i]",
            "prevent direct tel navigation": "event.preventDefault()",
            "dialog open": "showPhoneDialog()",
            "explicit dial escape hatch": 'link.hasAttribute("data-phone-dial")',
            "actual clickable number": "data-phone-dial",
            "official phone": "+380 99 321 08 72",
            "official tel URI": "tel:+380993210872",
            "lazy dialog stylesheet": "/assets/phone-dialog.css?v=20260908",
        }
        for label, marker in required_script.items():
            if marker not in script:
                errors.append(f"site/script.js: {label} marker missing: {marker}")

        prevent_pos = script.find("event.preventDefault()")
        show_pos = script.find("showPhoneDialog();", prevent_pos)
        if prevent_pos < 0 or show_pos <= prevent_pos:
            errors.append("site/script.js: call CTA must prevent tel navigation before opening the dialog")

    if not STYLES.is_file():
        errors.append("site/assets/phone-dialog.css is missing")
    else:
        css = STYLES.read_text(encoding="utf-8")
        for marker in (".phone-dialog", ".phone-dialog::backdrop", ".phone-dialog-number", ".phone-dialog-close"):
            if marker not in css:
                errors.append(f"phone-dialog.css: required selector missing: {marker}")

    if errors:
        return fail(errors)

    print("Phone CTA guard: PASS")
    print(f"  call CTA pages with shared script.js: {len(cta_pages)}")
    print(f"  call CTAs routed through shared phone dialog: {len(call_ctas)}")
    for item in call_ctas:
        print(f"    - {item}")
    print("  plain visible phone-number links remain direct tel: actions")
    print("  only the number inside the dialog explicitly opens the phone application")
    return 0


if __name__ == "__main__":
    sys.exit(main())
