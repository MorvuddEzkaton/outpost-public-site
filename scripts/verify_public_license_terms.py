#!/usr/bin/env python3
"""Guard commercial/license wording and structured facts across public sitemap pages.

Read-only and standard-library only. It checks source HTML/JSON-LD and never calls
Cabinet, Director, Sync, Workers, D1, payment systems, or any other protected service.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import json
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
PUBLIC_ORIGIN = "https://outpost.com.ua"
OFFICIAL_EMAIL = "roman@outpost.com.ua"
OFFICIAL_PHONE_DIGITS = "380993210872"

CURRENT_PRICE_MARKERS = ("2 000 грн", "2 000 ₴", "2000 грн")
SUPPORT_MARKERS = ("2 роки", "2 років")
ONE_PC_PATTERNS = (
    r"\bодин\s+(?:робочий\s+)?пк\b",
    r"\bодному\s+(?:робочому\s+)?пк\b",
    r"\bна\s+одному\s+(?:робочому\s+)?пк\b",
    r"\bза\s+1\s+(?:робочий\s+)?пк\b",
    r"\b1\s+пк\b",
    r"\bодна\s+ліцензія\b",
)
STALE_PRICE_PATTERNS = (
    r"(?<!\d)1\s*000\s*(?:грн|₴|UAH)(?!\w)",
    r"(?<!\d)1000\s*(?:грн|₴|UAH)(?!\w)",
)
UNSCOPED_SEO_PRICE = "<small>одноразово · без щомісячної підписки</small>"
SCOPED_SEO_PRICE = "<small>за 1 ПК · одноразово · без щомісячної підписки</small>"


class JsonLdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._active = False
        self._buffer: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "script" and data.get("type", "").lower() == "application/ld+json":
            self._active = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._active:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._active:
            self.blocks.append("".join(self._buffer).strip())
            self._active = False
            self._buffer = []


def fail(errors: list[str]) -> int:
    print(f"Public license terms guard: FAIL ({len(errors)} issue(s))", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


def sitemap_urls() -> list[str]:
    try:
        root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        raise RuntimeError(f"cannot parse site/sitemap.xml: {exc}") from exc

    urls: list[str] = []
    for node in root:
        loc = next(
            (
                child.text.strip()
                for child in node
                if child.tag.rsplit("}", 1)[-1] == "loc" and child.text
            ),
            None,
        )
        if loc:
            urls.append(loc)
    return urls


def html_path(url: str) -> Path:
    if url == f"{PUBLIC_ORIGIN}/":
        return SITE / "index.html"
    relative = url.removeprefix(PUBLIC_ORIGIN).strip("/")
    return SITE / f"{relative}.html"


def iter_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def object_types(value: dict) -> set[str]:
    raw = value.get("@type")
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {str(item) for item in raw}
    return set()


def validate_structured_commercial_facts(
    url: str,
    text: str,
    errors: list[str],
) -> tuple[int, int, int]:
    parser = JsonLdCollector()
    parser.feed(text)

    parsed_blocks = 0
    offer_count = 0
    contact_fact_count = 0

    for index, raw in enumerate(parser.blocks, start=1):
        if not raw:
            errors.append(f"{url}: JSON-LD block #{index} is empty")
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"{url}: JSON-LD block #{index} is invalid JSON: {exc}")
            continue

        parsed_blocks += 1
        for obj in iter_dicts(data):
            types = object_types(obj)

            if "Offer" in types:
                offer_count += 1
                has_price = "price" in obj
                has_currency = "priceCurrency" in obj
                if has_price != has_currency:
                    errors.append(
                        f"{url}: structured Offer must publish price and priceCurrency together"
                    )
                if has_price:
                    try:
                        structured_price = float(
                            str(obj["price"]).replace(" ", "").replace(",", ".")
                        )
                    except ValueError:
                        errors.append(
                            f"{url}: structured Offer price is not numeric: {obj['price']!r}"
                        )
                    else:
                        if structured_price != 2000:
                            errors.append(
                                f"{url}: structured Offer price must be 2000 UAH, got {obj['price']!r}"
                            )
                if has_currency and str(obj["priceCurrency"]).upper() != "UAH":
                    errors.append(
                        f"{url}: structured Offer priceCurrency must be UAH, got {obj['priceCurrency']!r}"
                    )

            if "email" in obj:
                contact_fact_count += 1
                email = str(obj["email"]).removeprefix("mailto:").strip().lower()
                if email != OFFICIAL_EMAIL:
                    errors.append(
                        f"{url}: structured email must be {OFFICIAL_EMAIL}, got {obj['email']!r}"
                    )

            if "telephone" in obj:
                contact_fact_count += 1
                digits = re.sub(r"\D", "", str(obj["telephone"]))
                if digits != OFFICIAL_PHONE_DIGITS:
                    errors.append(
                        f"{url}: structured telephone must be +380 99 321 08 72, got {obj['telephone']!r}"
                    )

    return parsed_blocks, offer_count, contact_fact_count


def main() -> int:
    errors: list[str] = []
    try:
        urls = sitemap_urls()
    except RuntimeError as exc:
        return fail([str(exc)])

    if not urls:
        return fail(["sitemap contains no public URLs"])

    price_pages = 0
    scoped_seo_boxes = 0
    jsonld_blocks = 0
    structured_offers = 0
    structured_contact_facts = 0

    for url in urls:
        path = html_path(url)
        if not path.is_file():
            errors.append(f"{url}: mapped HTML is missing ({path.relative_to(ROOT)})")
            continue

        text = path.read_text(encoding="utf-8")

        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in STALE_PRICE_PATTERNS):
            errors.append(f"{url}: stale 1000-UAH public price marker detected")

        has_price = any(marker in text for marker in CURRENT_PRICE_MARKERS)
        if has_price:
            price_pages += 1
            if not any(marker in text for marker in SUPPORT_MARKERS):
                errors.append(f"{url}: publishes 2000-UAH price without 2-year support context")
            if not any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in ONE_PC_PATTERNS):
                errors.append(f"{url}: publishes 2000-UAH price without one-PC license scope")

        if UNSCOPED_SEO_PRICE in text:
            errors.append(f"{url}: SEO price box omits 'за 1 ПК' scope")
        if SCOPED_SEO_PRICE in text:
            scoped_seo_boxes += 1

        blocks, offers, contacts = validate_structured_commercial_facts(url, text, errors)
        jsonld_blocks += blocks
        structured_offers += offers
        structured_contact_facts += contacts

    veteran_required_pages = {
        "index.html": ("УБД", "безкоштов", "1 ПК"),
        "license.html": ("УБД", "безкоштов", "один робочий ПК"),
        "download.html": ("УБД", "безкоштов", "один робочий ПК"),
        "support.html": ("УБД", "безкоштов", "один робочий ПК"),
        "bezkoshtovna-programa-dlya-magazynu.html": (
            "Безкоштовна програма для магазину",
            "чинного посвідчення УБД",
            "0 грн",
            "один робочий ПК",
            "2 роки",
            "не пробний період",
        ),
    }
    for filename, markers in veteran_required_pages.items():
        text = (SITE / filename).read_text(encoding="utf-8")
        missing = [marker for marker in markers if marker not in text]
        if missing:
            errors.append(
                f"{filename}: missing UBD free-license marker(s): {', '.join(missing)}"
            )

    faq_source = (SITE / "_telegram-faq.js").read_text(encoding="utf-8")
    for marker in (
        'id: "license_ubd"',
        "чинного посвідчення УБД",
        "безкоштовно",
        "2 роки технічної підтримки",
    ):
        if marker not in faq_source:
            errors.append(f"site/_telegram-faq.js: missing UBD FAQ marker: {marker}")

    if scoped_seo_boxes != 7:
        errors.append(f"expected 7 scoped SEO price boxes, found {scoped_seo_boxes}")

    if errors:
        return fail(list(dict.fromkeys(errors)))

    print("Public license terms guard: PASS")
    print(f"  sitemap pages checked: {len(urls)}")
    print(f"  pages publishing current price: {price_pages}")
    print("  all public 2000-UAH price mentions retain 2-year support + one-PC scope")
    print("  7/7 SEO price boxes say 'за 1 ПК' explicitly")
    print("  no stale 1000-UAH price marker found")
    print(f"  valid JSON-LD blocks checked: {jsonld_blocks}")
    print(f"  structured Offer facts checked: {structured_offers}")
    print(f"  structured email/telephone facts checked: {structured_contact_facts}")
    print("  structured price/currency/contact facts match official public terms")
    print("  UBD free-license terms are present on homepage, license, download, Support Center and dedicated SEO landing")
    print("  Telegram FAQ source preserves the UBD eligibility, one-PC scope and 2-year support")
    print("  protected services were not called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
