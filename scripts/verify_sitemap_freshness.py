#!/usr/bin/env python3
"""Fail closed when sitemap lastmod predates the latest Git change to its HTML source.

The guard is intentionally repo-only. It reads site/sitemap.xml and Git history; it
never calls production, Cloudflare, Cabinet, Director, Sync, D1, Workers, or any API.

CI requirement: checkout must contain full Git history (actions/checkout fetch-depth: 0).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
ORIGIN = "https://outpost.com.ua"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class VerifyError(RuntimeError):
    pass


def parse_iso_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise VerifyError(f"{label}: expected YYYY-MM-DD, got {value!r}") from exc


def source_path_for_url(url: str) -> Path:
    parsed = urlsplit(url)
    if f"{parsed.scheme}://{parsed.netloc}" != ORIGIN:
        raise VerifyError(f"unexpected sitemap origin: {url}")
    if parsed.query or parsed.fragment:
        raise VerifyError(f"sitemap URL must not contain query/fragment: {url}")

    pathname = parsed.path or "/"
    if not pathname.startswith("/") or ".." in Path(pathname).parts:
        raise VerifyError(f"unsafe sitemap path: {pathname}")

    if pathname == "/":
        relative = Path("site/index.html")
    else:
        relative = Path("site") / f"{pathname.lstrip('/').rstrip('/')}.html"

    absolute = ROOT / relative
    if not absolute.is_file():
        raise VerifyError(f"{url}: mapped source file is missing: {relative.as_posix()}")
    return relative


def latest_commit_date(relative_path: Path) -> date:
    command = [
        "git",
        "log",
        "-1",
        "--format=%cs",
        "--",
        relative_path.as_posix(),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise VerifyError(
            f"git log failed for {relative_path.as_posix()}: {result.stderr.strip()}"
        )

    value = result.stdout.strip()
    if not value:
        raise VerifyError(
            f"no Git history for {relative_path.as_posix()}; CI must checkout full history "
            "with actions/checkout fetch-depth: 0"
        )
    return parse_iso_date(value, f"git date for {relative_path.as_posix()}")


def freshness_error(url: str, lastmod: date, committed: date) -> str | None:
    if lastmod < committed:
        return (
            f"{url}: sitemap lastmod {lastmod.isoformat()} is older than latest HTML "
            f"Git change {committed.isoformat()}"
        )
    return None


def future_lastmod_error(url: str, lastmod: date, today_kyiv: date) -> str | None:
    if lastmod > today_kyiv:
        return (
            f"{url}: sitemap lastmod {lastmod.isoformat()} is in the future "
            f"for Europe/Kyiv ({today_kyiv.isoformat()})"
        )
    return None


def read_entries() -> list[tuple[str, date, Path]]:
    try:
        root = ET.parse(SITEMAP).getroot()
    except (OSError, ET.ParseError) as exc:
        raise VerifyError(f"cannot parse {SITEMAP.relative_to(ROOT)}: {exc}") from exc

    entries: list[tuple[str, date, Path]] = []
    seen: set[str] = set()
    for node in root.findall("sm:url", NS):
        loc_node = node.find("sm:loc", NS)
        lastmod_node = node.find("sm:lastmod", NS)
        if loc_node is None or not (loc_node.text or "").strip():
            raise VerifyError("sitemap entry is missing <loc>")
        if lastmod_node is None or not (lastmod_node.text or "").strip():
            raise VerifyError(f"{loc_node.text}: sitemap entry is missing <lastmod>")

        url = (loc_node.text or "").strip()
        if url in seen:
            raise VerifyError(f"duplicate sitemap URL: {url}")
        seen.add(url)

        lastmod = parse_iso_date(lastmod_node.text or "", f"{url} lastmod")
        source = source_path_for_url(url)
        entries.append((url, lastmod, source))

    if not entries:
        raise VerifyError("sitemap contains no URL entries")
    return entries


def verify() -> tuple[int, int]:
    entries = read_entries()
    errors: list[str] = []
    exact_matches = 0
    today_kyiv = datetime.now(ZoneInfo("Europe/Kyiv")).date()

    for url, lastmod, source in entries:
        committed = latest_commit_date(source)
        error = freshness_error(url, lastmod, committed)
        if error:
            errors.append(error)
        future_error = future_lastmod_error(url, lastmod, today_kyiv)
        if future_error:
            errors.append(future_error)
        if lastmod == committed:
            exact_matches += 1

    if errors:
        raise VerifyError("\n  - ".join(errors))
    return len(entries), exact_matches


def main() -> int:
    try:
        count, exact_matches = verify()
    except VerifyError as exc:
        print(f"Sitemap Git freshness guard: FAIL\n  - {exc}", file=sys.stderr)
        return 1

    print("Sitemap Git freshness guard: PASS")
    print(f"  sitemap HTML entries checked: {count}")
    print(f"  entries whose lastmod exactly matches latest HTML Git date: {exact_matches}")
    print("  every lastmod is >= the latest committed change date and <= today in Europe/Kyiv")
    print("  production and protected services were not called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
