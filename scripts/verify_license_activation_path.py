#!/usr/bin/env python3
"""Guard the public demo -> Computer ID -> license contact path.

Read-only, standard-library only. It never calls Cabinet, Workers or D1.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
LICENSE = ROOT / "site" / "license.html"
INDEX = ROOT / "site" / "index.html"

EMAIL_PREFIX = "mailto:roman@outpost.com.ua"
TELEGRAM = "https://t.me/OutPOStUA_bot?start=license"


def fail(messages: list[str]) -> int:
    print(f"License activation path guard: FAIL ({len(messages)} issue(s))", file=sys.stderr)
    for message in messages:
        print(f"  - {message}", file=sys.stderr)
    return 1


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in (LICENSE, INDEX) if not path.is_file()]
    if missing:
        return fail([f"{path} is missing" for path in missing])

    text = LICENSE.read_text(encoding="utf-8")
    homepage = INDEX.read_text(encoding="utf-8")
    errors: list[str] = []

    required_page = {
        "public price": "2 000 грн",
        "demo route": 'href="/download"',
        "Computer ID activation": "Computer ID",
        "personal license file": ".outpost-license",
        "two-year support": "2 роки",
        "official email": EMAIL_PREFIX,
        "official Telegram purchase route": TELEGRAM,
    }
    for label, marker in required_page.items():
        if marker not in text:
            errors.append(f"{label}: missing marker {marker!r}")

    match = re.search(
        r'<section class="capability-group" id="activation">(?P<body>.*?)</section>',
        text,
        flags=re.DOTALL,
    )
    if not match:
        errors.append("activation section id=activation is missing")
    else:
        activation = match.group("body")
        required_activation = {
            "Computer ID step": "Computer ID",
            "email contact inside activation instructions": EMAIL_PREFIX,
            "Telegram contact inside activation instructions": TELEGRAM,
            "license import step": ".outpost-license",
        }
        for label, marker in required_activation.items():
            if marker not in activation:
                errors.append(f"{label}: missing marker {marker!r}")

    faq_match = re.search(
        r'<summary>Як придбати OutPOSt\?(?:.*?)</summary>\s*<p>(?P<body>.*?)</p>',
        homepage,
        flags=re.DOTALL,
    )
    if not faq_match:
        errors.append("homepage purchase FAQ 'Як придбати OutPOSt?' is missing")
    else:
        faq = faq_match.group("body")
        required_faq = {
            "homepage FAQ price": "2 000 грн",
            "homepage FAQ two-year support": "2 років",
            "homepage FAQ official email": EMAIL_PREFIX,
            "homepage FAQ official Telegram route": TELEGRAM,
            "homepage FAQ no-site-payment context": "платежів через сайт немає",
        }
        for label, marker in required_faq.items():
            if marker not in faq:
                errors.append(f"{label}: missing marker {marker!r}")

    if "щомісячної підписки" not in text:
        errors.append("no-monthly-subscription wording is missing")

    if errors:
        return fail(errors)

    print("License activation path guard: PASS")
    print("  demo -> Computer ID -> email/Telegram -> .outpost-license path is explicit")
    print("  homepage purchase FAQ matches the official email/Telegram contact path")
    print("  price, perpetual-license context and 2-year support markers remain present")
    print("  protected services were not called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
