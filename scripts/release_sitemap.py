#!/usr/bin/env python3
"""Shared release-sitemap helpers for OutPOSt public release tooling.

The module only edits the static sitemap text supplied by release tooling. It never
calls production, Cloudflare, D1, Cabinet, Director, Sync, PRRO or RRO services.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import re


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
PUBLIC_ORIGIN = "https://outpost.com.ua"
KYIV = ZoneInfo("Europe/Kyiv")


def _release_date() -> str:
    return datetime.now(KYIV).date().isoformat()


def _url_for_html(path: Path) -> str:
    if path.name == "index.html":
        return f"{PUBLIC_ORIGIN}/"
    return f"{PUBLIC_ORIGIN}/{path.stem}"


def _replace_lastmod(text: str, url: str, release_date: str) -> tuple[str, bool]:
    pattern = re.compile(
        rf"(<loc>{re.escape(url)}</loc>\s*<lastmod>)(\d{{4}}-\d{{2}}-\d{{2}})(</lastmod>)"
    )
    matches = list(pattern.finditer(text))
    if len(matches) > 1:
        raise ValueError(f"site/sitemap.xml contains duplicate release URL: {url}")
    if not matches:
        return text, False
    return pattern.sub(rf"\g<1>{release_date}\g<3>", text, count=1), True


def prepare_release_sitemap(changed_paths) -> tuple[str, str, tuple[str, ...]]:
    """Return updated sitemap text for release-modified public pages.

    `changed_paths` is the set/dict keys produced by prepare_public_release.py before
    the sitemap itself is added. Changelog is always included because release tooling
    requires it to be updated before preparation.
    """

    if not SITEMAP.is_file():
        raise ValueError("site/sitemap.xml is missing")

    original = SITEMAP.read_text(encoding="utf-8")
    release_date = _release_date()

    candidate_urls = {_url_for_html(Path(path)) for path in changed_paths if Path(path).suffix == ".html"}
    candidate_urls.add(f"{PUBLIC_ORIGIN}/changelog")

    # These three pages are release-critical and must always exist in the sitemap.
    required_urls = {
        f"{PUBLIC_ORIGIN}/",
        f"{PUBLIC_ORIGIN}/download",
        f"{PUBLIC_ORIGIN}/changelog",
    }

    text = original
    updated: list[str] = []
    found: set[str] = set()
    for url in sorted(candidate_urls | required_urls):
        text, existed = _replace_lastmod(text, url, release_date)
        if existed:
            found.add(url)
            updated.append(url)

    missing_required = sorted(required_urls - found)
    if missing_required:
        raise ValueError(
            "site/sitemap.xml is missing required release URL(s): " + ", ".join(missing_required)
        )

    return text, release_date, tuple(updated)
