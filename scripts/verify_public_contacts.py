#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OLD_EMAIL = "roma.sapozhnikov@gmail.com"
NEW_EMAIL = "roman@outpost.com.ua"
PHONE_HREF = "tel:+380993210872"
PHONE_DISPLAY = "+380 99 321 08 72"

errors: list[str] = []
html_files = sorted(SITE.glob("*.html"))

for path in html_files:
    text = path.read_text(encoding="utf-8")
    if f"mailto:{OLD_EMAIL}" in text:
        errors.append(f"active old email remains in {path.relative_to(ROOT)}")
    if "Email автору" in text:
        if f"mailto:{NEW_EMAIL}" not in text:
            errors.append(f"contact footer lacks current email in {path.relative_to(ROOT)}")
        if PHONE_HREF not in text:
            errors.append(f"contact footer lacks phone in {path.relative_to(ROOT)}")

for rel in ["site/index.html", "site/support.html", "site/license.html", "site/download.html"]:
    text = (ROOT / rel).read_text(encoding="utf-8")
    if f"mailto:{NEW_EMAIL}" not in text:
        errors.append(f"{rel} lacks current contact email")
    if PHONE_HREF not in text or PHONE_DISPLAY not in text:
        errors.append(f"{rel} lacks public phone")

support_gen = (ROOT / "scripts" / "generate_support_center.mjs").read_text(encoding="utf-8")
if f"mailto:{OLD_EMAIL}" in support_gen:
    errors.append("Support Center generator still contains active old email")
if f"mailto:{NEW_EMAIL}" not in support_gen:
    errors.append("Support Center generator lacks current email")
if PHONE_HREF not in support_gen:
    errors.append("Support Center generator lacks phone")

changelog = (SITE / "changelog.html").read_text(encoding="utf-8")
if changelog.count(OLD_EMAIL) > 1:
    errors.append("historical Gmail appears more than once in changelog")
if OLD_EMAIL in changelog and f"mailto:{OLD_EMAIL}" in changelog:
    errors.append("historical Gmail must not remain an active mailto link")

if errors:
    print("Public contact guard: FAIL")
    for error in errors:
        print(f"  - {error}")
    raise SystemExit(1)

print("Public contact guard: PASS")
print(f"  current email: {NEW_EMAIL}")
print(f"  phone: {PHONE_DISPLAY}")
print("  legacy Gmail is not an active public contact")
