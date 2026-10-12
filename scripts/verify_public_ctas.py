#!/usr/bin/env python3
"""Read-only source guard for the main public conversion paths.

The guard checks that visitors can move from the public site to download, support and
contact actions without touching Customer Portal, Director, Sync, D1 or fiscal APIs.
"""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

EMAIL = "mailto:roman@outpost.com.ua"
PHONE = "tel:+380993210872"
TELEGRAM = "https://t.me/OutPOStUA_bot"
CABINET = "https://cabinet.outpost.com.ua/"


def text(name: str) -> str:
    return (SITE / name).read_text(encoding="utf-8")


def require(errors: list[str], name: str, content: str, marker: str, label: str) -> None:
    if marker not in content:
        errors.append(f"site/{name}: missing {label}: {marker}")


def main() -> int:
    errors: list[str] = []
    pages = {
        "index.html": text("index.html"),
        "download.html": text("download.html"),
        "license.html": text("license.html"),
        "support.html": text("support.html"),
    }

    for name, content in pages.items():
        require(errors, name, content, "/download", "download path")
        require(errors, name, content, CABINET, "canonical cabinet link")

    # The three acquisition pages must make support discoverable without requiring
    # a visitor to return to the homepage.
    for name in ("index.html", "download.html", "license.html"):
        require(errors, name, pages[name], "/support", "Support Center path")

    # Homepage: direct installer + built-in question action + public phone/email.
    require(errors, "index.html", pages["index.html"], "OutPOSt-Setup-v", "installer CTA")
    require(errors, "index.html", pages["index.html"], "data-outpost-open-question", "question CTA")
    require(errors, "index.html", pages["index.html"], EMAIL, "public email")
    require(errors, "index.html", pages["index.html"], PHONE, "public phone")

    # Download page: a user who encounters installation trouble must have three
    # independent support routes and an explicit license route.
    for marker, label in (
        ("/support", "Support Center CTA"),
        (TELEGRAM, "Telegram support CTA"),
        (PHONE, "phone support CTA"),
        (EMAIL, "license email CTA"),
        ("/license", "license details CTA"),
    ):
        require(errors, "download.html", pages["download.html"], marker, label)

    # License page: try-before-buy, email and phone must all remain explicit.
    for marker, label in (
        ("/download", "demo download CTA"),
        ("/support", "Support Center CTA"),
        (EMAIL, "purchase email CTA"),
        (PHONE, "purchase phone CTA"),
    ):
        require(errors, "license.html", pages["license.html"], marker, label)

    # Support Center: direct Telegram route and official download/contact fallbacks.
    for marker, label in (
        (TELEGRAM, "Telegram support CTA"),
        ("/download", "official download CTA"),
        (EMAIL, "email fallback"),
        (PHONE, "phone fallback"),
    ):
        require(errors, "support.html", pages["support.html"], marker, label)

    unique = list(dict.fromkeys(errors))
    if unique:
        print(f"Public CTA guard: FAIL ({len(unique)} issue(s))")
        for item in unique:
            print(f"  - {item}")
        return 1

    print("Public CTA guard: PASS")
    print("  homepage -> installer/question/contact paths present")
    print("  download -> support/license/contact paths present")
    print("  license -> demo/support/contact paths present")
    print("  support -> Telegram/download/email/phone paths present")
    print("  cabinet is checked as a link marker only; no protected service is called")
    return 0


if __name__ == "__main__":
    sys.exit(main())
