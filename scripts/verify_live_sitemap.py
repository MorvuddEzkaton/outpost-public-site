#!/usr/bin/env python3
"""Verify that production sitemap loc/lastmod data matches repository source.

Read-only safety model:
- reads local site/sitemap.xml;
- performs GET requests only to https://outpost.com.ua/sitemap.xml;
- compares URL membership plus lastmod/changefreq/priority values exactly;
- retries briefly to tolerate Cloudflare deployment/cache propagation;
- does not call Cabinet, Worker APIs, D1, Director, Sync, PRRO or fiscal services.
"""

from __future__ import annotations

from pathlib import Path
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
LOCAL_SITEMAP = ROOT / "site" / "sitemap.xml"
LIVE_SITEMAP_URL = "https://outpost.com.ua/sitemap.xml"
USER_AGENT = "OutPOSt-Live-Sitemap-Verifier/1.0"


class SitemapError(RuntimeError):
    pass


def parse_sitemap(xml_text: str, label: str) -> dict[str, dict[str, str]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise SitemapError(f"{label}: invalid XML: {exc}") from exc

    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0] + "}"
    else:
        namespace = ""

    if root.tag != f"{namespace}urlset":
        raise SitemapError(f"{label}: root element must be urlset")

    entries: dict[str, dict[str, str]] = {}
    required_fields = ("loc", "lastmod", "changefreq", "priority")

    for index, url_element in enumerate(root.findall(f"{namespace}url"), 1):
        values: dict[str, list[str]] = {field: [] for field in required_fields}
        for child in list(url_element):
            field = child.tag.rsplit("}", 1)[-1]
            if field in values:
                values[field].append((child.text or "").strip())

        for field in required_fields:
            current = values[field]
            if len(current) != 1 or not current[0]:
                raise SitemapError(
                    f"{label}: url entry #{index} must contain exactly one non-empty "
                    f"{field}; got {current!r}"
                )

        loc = values["loc"][0]
        if loc in entries:
            raise SitemapError(f"{label}: duplicate loc {loc}")

        entries[loc] = {
            "lastmod": values["lastmod"][0],
            "changefreq": values["changefreq"][0],
            "priority": values["priority"][0],
        }

    if not entries:
        raise SitemapError(f"{label}: sitemap contains no URL entries")
    return entries


def fetch_live_sitemap() -> str:
    request = urllib.request.Request(
        LIVE_SITEMAP_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.1",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise SitemapError(f"production sitemap returned HTTP {status}")
            data = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SitemapError(f"production sitemap request failed: {exc}") from exc

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SitemapError("production sitemap is not valid UTF-8") from exc


def differences(
    expected: dict[str, dict[str, str]],
    actual: dict[str, dict[str, str]],
) -> list[str]:
    issues: list[str] = []

    for loc in sorted(expected.keys() - actual.keys()):
        issues.append(f"missing on production: {loc}")
    for loc in sorted(actual.keys() - expected.keys()):
        issues.append(f"unexpected on production: {loc}")
    for loc in sorted(expected.keys() & actual.keys()):
        for field in ("lastmod", "changefreq", "priority"):
            if expected[loc][field] != actual[loc][field]:
                issues.append(
                    f"{field} mismatch for {loc}: "
                    f"repository={expected[loc][field]} production={actual[loc][field]}"
                )

    return issues


def positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise SitemapError(f"{name} must be an integer") from exc
    if value < 1:
        raise SitemapError(f"{name} must be >= 1")
    return value


def nonnegative_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise SitemapError(f"{name} must be an integer") from exc
    if value < 0:
        raise SitemapError(f"{name} must be >= 0")
    return value


def main() -> int:
    try:
        if not LOCAL_SITEMAP.is_file():
            raise SitemapError("local site/sitemap.xml is missing")

        expected = parse_sitemap(LOCAL_SITEMAP.read_text(encoding="utf-8"), "repository sitemap")
        attempts = positive_int_env("OUTPOST_LIVE_SITEMAP_ATTEMPTS", 6)
        delay_seconds = nonnegative_int_env("OUTPOST_LIVE_SITEMAP_DELAY_SECONDS", 5)

        last_error: str | None = None
        last_issues: list[str] = []

        for attempt in range(1, attempts + 1):
            try:
                actual = parse_sitemap(fetch_live_sitemap(), "production sitemap")
                issues = differences(expected, actual)
                if not issues:
                    print("OutPOSt live sitemap verifier: PASS")
                    print(f"  production URL: {LIVE_SITEMAP_URL}")
                    print(f"  matched loc + lastmod + changefreq + priority entries: {len(expected)}")
                    print("  protected application services were not called")
                    return 0
                last_issues = issues
                last_error = None
                print(
                    f"OutPOSt live sitemap verifier: propagation mismatch on attempt {attempt}/{attempts} "
                    f"({len(issues)} issue(s))"
                )
            except SitemapError as exc:
                last_error = str(exc)
                last_issues = []
                print(
                    f"OutPOSt live sitemap verifier: request/parse issue on attempt {attempt}/{attempts}: {exc}"
                )

            if attempt < attempts and delay_seconds:
                time.sleep(delay_seconds)

        print("OutPOSt live sitemap verifier: FAIL", file=sys.stderr)
        if last_error:
            print(f"  - {last_error}", file=sys.stderr)
        for issue in last_issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    except SitemapError as exc:
        print("OutPOSt live sitemap verifier: FAIL", file=sys.stderr)
        print(f"  - {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
