#!/usr/bin/env python3
"""Guard intentionally removed public OutPOSt routes from accidental reintroduction.

This check is static and read-only. It does not call production services, Cloudflare,
D1, Customer Portal, Director, Sync API, or fiscal integrations.
"""

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PUBLIC_ORIGIN = "https://outpost.com.ua"

REMOVED_ROUTES = {
    "/about": "about.html",
}


def main() -> int:
    errors: list[str] = []
    html_files = sorted(SITE.glob("*.html"))
    sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8") if (SITE / "sitemap.xml").is_file() else ""

    for route, filename in REMOVED_ROUTES.items():
        removed_file = SITE / filename
        if removed_file.exists():
            errors.append(f"removed public page returned: site/{filename}")

        canonical = f"{PUBLIC_ORIGIN}{route}"
        if f"<loc>{canonical}</loc>" in sitemap:
            errors.append(f"removed public route returned to sitemap: {canonical}")

        relative_link = re.compile(rf"href\s*=\s*(['\"])\s*{re.escape(route)}(?:[#?][^'\"]*)?\1", re.IGNORECASE)
        absolute_link = re.compile(rf"href\s*=\s*(['\"])\s*{re.escape(canonical)}(?:[#?][^'\"]*)?\1", re.IGNORECASE)

        for path in html_files:
            text = path.read_text(encoding="utf-8")
            if relative_link.search(text) or absolute_link.search(text):
                errors.append(f"site/{path.name}: link to removed public route {route} found")

    unique_errors = list(dict.fromkeys(errors))
    if unique_errors:
        print(f"Removed public page guard: FAIL ({len(unique_errors)} issue(s))")
        for error in unique_errors:
            print(f"  - {error}")
        return 1

    print("Removed public page guard: PASS")
    print("  /about remains absent from static files, public links and sitemap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
