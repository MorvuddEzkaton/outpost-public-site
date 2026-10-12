#!/usr/bin/env python3
"""Read-only guard for release-critical sitemap lastmod metadata."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITEMAP = ROOT / "site" / "sitemap.xml"
PUBLIC_ORIGIN = "https://outpost.com.ua"
RELEASE_URLS = (
    f"{PUBLIC_ORIGIN}/",
    f"{PUBLIC_ORIGIN}/download",
    f"{PUBLIC_ORIGIN}/changelog",
)


def main() -> int:
    errors: list[str] = []
    if not SITEMAP.is_file():
        print("Release sitemap guard: FAIL\n  - missing site/sitemap.xml", file=sys.stderr)
        return 1

    try:
        root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    except ET.ParseError as exc:
        print(f"Release sitemap guard: FAIL\n  - invalid sitemap XML: {exc}", file=sys.stderr)
        return 1

    rows: dict[str, list[str]] = {}
    for url_node in root:
        loc = None
        lastmod = None
        for child in url_node:
            local = child.tag.rsplit("}", 1)[-1]
            if local == "loc" and child.text:
                loc = child.text.strip()
            elif local == "lastmod" and child.text:
                lastmod = child.text.strip()
        if loc:
            rows.setdefault(loc, []).append(lastmod or "")

    parsed: dict[str, date] = {}
    for url in RELEASE_URLS:
        values = rows.get(url, [])
        if len(values) != 1:
            errors.append(f"{url}: expected exactly one sitemap entry, got {len(values)}")
            continue
        raw = values[0]
        try:
            parsed[url] = date.fromisoformat(raw)
        except ValueError:
            errors.append(f"{url}: invalid ISO lastmod date {raw!r}")

    if len(parsed) == len(RELEASE_URLS):
        today_kyiv = datetime.now(ZoneInfo("Europe/Kyiv")).date()
        for url, value in parsed.items():
            if value > today_kyiv:
                errors.append(f"{url}: lastmod {value.isoformat()} is in the future for Europe/Kyiv")

        homepage = parsed[f"{PUBLIC_ORIGIN}/"]
        download = parsed[f"{PUBLIC_ORIGIN}/download"]
        changelog = parsed[f"{PUBLIC_ORIGIN}/changelog"]

        # A product release updates all three pages together, but ordinary public-site
        # work may legitimately update the homepage and/or download page without
        # changing the changelog. The fail-closed condition we need is therefore that
        # release-facing pages must never look older than the current changelog.
        if homepage < changelog:
            errors.append(
                f"homepage lastmod {homepage.isoformat()} is older than changelog {changelog.isoformat()}"
            )
        if download < changelog:
            errors.append(
                f"download lastmod {download.isoformat()} is older than changelog {changelog.isoformat()}"
            )

    if errors:
        print(f"Release sitemap guard: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    homepage = parsed[f"{PUBLIC_ORIGIN}/"]
    download = parsed[f"{PUBLIC_ORIGIN}/download"]
    changelog = parsed[f"{PUBLIC_ORIGIN}/changelog"]
    aligned = homepage == download == changelog

    print("Release sitemap guard: PASS")
    if aligned:
        print(f"  /, /download and /changelog share release lastmod {changelog.isoformat()}")
    else:
        print(
            "  non-release content updates are newer than the current changelog: "
            f"/={homepage.isoformat()}, /download={download.isoformat()}, /changelog={changelog.isoformat()}"
        )
    print("  release-facing lastmod dates are valid ISO dates and not older than /changelog")
    print("  no release-critical lastmod is in the future for Europe/Kyiv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
