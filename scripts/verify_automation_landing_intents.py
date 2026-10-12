#!/usr/bin/env python3
"""Guard distinct search intent across OutPOSt automation landing pages."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

PAGES = {
    "/avtomatyzatsiya-magazynu": {
        "file": "avtomatyzatsiya-magazynu.html",
        "role": "hub",
        "must_link": {
            "/avtomatyzatsiya-rozdribnoi-torgivli",
            "/avtomatyzatsiya-zakupivel-i-skladu",
        },
        "term_groups": (
            ("каса", "каси"),
            ("продаж",),
            ("товар",),
            ("борг",),
            ("звіт",),
        ),
    },
    "/avtomatyzatsiya-rozdribnoi-torgivli": {
        "file": "avtomatyzatsiya-rozdribnoi-torgivli.html",
        "role": "retail",
        "must_link": {"/avtomatyzatsiya-magazynu"},
        "term_groups": (
            ("каса", "касир"),
            ("продаж",),
            ("повернен",),
            ("ппрро", "mini", "checkbox", "фіскал"),
        ),
    },
    "/avtomatyzatsiya-zakupivel-i-skladu": {
        "file": "avtomatyzatsiya-zakupivel-i-skladu.html",
        "role": "procurement",
        "must_link": {"/avtomatyzatsiya-magazynu"},
        "term_groups": (
            ("закупів", "прихід"),
            ("постачаль",),
            ("склад", "залишк"),
            ("собіварт", "інвентаризац"),
        ),
    },
}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_chunks: list[str] = []
        self.h1_chunks: list[str] = []
        self.text_chunks: list[str] = []
        self.links: set[str] = set()
        self.description: str | None = None
        self.canonical: str | None = None
        self.robots: str | None = None
        self._in_title = False
        self._in_h1 = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr = {key.lower(): value for key, value in attrs}
        if tag in {"script", "style", "template"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
        elif tag == "a":
            href = attr.get("href")
            if href and href.startswith("/"):
                self.links.add(href.split("#", 1)[0].split("?", 1)[0])
        elif tag == "meta":
            name = (attr.get("name") or "").lower()
            if name == "description":
                self.description = attr.get("content")
            elif name == "robots":
                self.robots = attr.get("content")
        elif tag == "link":
            rel = (attr.get("rel") or "").lower()
            if "canonical" in rel.split():
                self.canonical = attr.get("href")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "template"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        clean = data.strip()
        if not clean:
            return
        self.text_chunks.append(clean)
        if self._in_title:
            self.title_chunks.append(clean)
        if self._in_h1:
            self.h1_chunks.append(clean)

    @property
    def title(self) -> str:
        return " ".join(self.title_chunks).strip()

    @property
    def h1(self) -> str:
        return " ".join(self.h1_chunks).strip()

    @property
    def visible_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.text_chunks)).strip().lower()


def parse(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


def main() -> int:
    errors: list[str] = []
    snapshots: dict[str, PageParser] = {}

    for route, contract in PAGES.items():
        path = SITE / contract["file"]
        if not path.is_file():
            errors.append(f"{route}: missing {path.relative_to(ROOT)}")
            continue

        parser = parse(path)
        snapshots[route] = parser

        expected_canonical = f"https://outpost.com.ua{route}"
        if parser.canonical != expected_canonical:
            errors.append(
                f"{route}: canonical must be {expected_canonical!r}, got {parser.canonical!r}"
            )

        if not parser.title:
            errors.append(f"{route}: missing <title>")
        if not parser.description:
            errors.append(f"{route}: missing meta description")
        if not parser.h1:
            errors.append(f"{route}: missing H1")

        robots = (parser.robots or "").lower()
        if "noindex" in robots:
            errors.append(f"{route}: automation landing page must remain indexable")

        for target in sorted(contract["must_link"]):
            if target not in parser.links:
                errors.append(f"{route}: missing intent/navigation link to {target}")

        for group in contract["term_groups"]:
            if not any(term in parser.visible_text for term in group):
                errors.append(
                    f"{route}: missing role-specific topic group {group!r} for {contract['role']} intent"
                )

    for field in ("title", "description", "h1", "canonical"):
        values: dict[str, str] = {}
        for route, parser in snapshots.items():
            value = getattr(parser, field) or ""
            if not value:
                continue
            key = value.casefold().strip()
            if key in values:
                errors.append(
                    f"{route}: duplicate {field} with {values[key]}: {value!r}"
                )
            else:
                values[key] = route

    hub = snapshots.get("/avtomatyzatsiya-magazynu")
    if hub:
        title = hub.title.casefold()
        if "автоматизація магазину" not in title:
            errors.append("/avtomatyzatsiya-magazynu: hub title must target 'автоматизація магазину'")

    retail = snapshots.get("/avtomatyzatsiya-rozdribnoi-torgivli")
    if retail:
        title = retail.title.casefold()
        if "роздрібної торгівлі" not in title:
            errors.append(
                "/avtomatyzatsiya-rozdribnoi-torgivli: title must preserve retail-specific intent"
            )

    procurement = snapshots.get("/avtomatyzatsiya-zakupivel-i-skladu")
    if procurement:
        title = procurement.title.casefold()
        if "закупів" not in title or "склад" not in title:
            errors.append(
                "/avtomatyzatsiya-zakupivel-i-skladu: title must preserve procurement/warehouse intent"
            )

    unique_errors = list(dict.fromkeys(errors))
    if unique_errors:
        print(f"Automation landing intent guard: FAIL ({len(unique_errors)} issue(s))")
        for error in unique_errors:
            print(f"  - {error}")
        return 1

    print("Automation landing intent guard: PASS")
    print("  broad automation page remains the hub")
    print("  retail automation keeps sales/cashier/fiscal intent")
    print("  procurement automation keeps supplier/stock intent")
    print("  canonical/title/description/H1 values remain distinct")
    print("  hub <-> specialist internal-link contract is intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
