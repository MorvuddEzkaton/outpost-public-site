#!/usr/bin/env python3
"""Verify that every production sitemap page exposes the Support Center.

Read-only safety model:
- reads local site/sitemap.xml;
- performs GET requests only to public https://outpost.com.ua sitemap pages;
- requires HTTP 200 and a direct href="/support" marker on every page;
- retries briefly for Cloudflare deployment/cache propagation;
- does not call Cabinet, Worker APIs, D1, Director, Sync, PRRO or fiscal services.
"""

from __future__ import annotations

from pathlib import Path
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITEMAP = ROOT / "site" / "sitemap.xml"
SUPPORT_MARKER = 'href="/support"'
USER_AGENT = "OutPOSt-Live-Support-Discovery-Verifier/1.0"


class VerifyError(RuntimeError):
    pass


def sitemap_urls() -> list[str]:
    try:
        root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        raise VerifyError(f"cannot parse site/sitemap.xml: {exc}") from exc

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls: list[str] = []
    seen: set[str] = set()
    for node in root.findall("sm:url", ns):
        loc_node = node.find("sm:loc", ns)
        loc = (loc_node.text or "").strip() if loc_node is not None else ""
        if not loc:
            raise VerifyError("sitemap contains an entry without loc")
        parsed = urlparse(loc)
        if parsed.scheme != "https" or parsed.netloc != "outpost.com.ua":
            raise VerifyError(f"unexpected sitemap URL: {loc}")
        if parsed.query or parsed.fragment:
            raise VerifyError(f"sitemap URL contains query/fragment: {loc}")
        if loc in seen:
            raise VerifyError(f"duplicate sitemap URL: {loc}")
        seen.add(loc)
        urls.append(loc)

    if not urls:
        raise VerifyError("sitemap contains no URLs")
    return urls


def int_env(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise VerifyError(f"{name} must be an integer") from exc
    if value < minimum:
        raise VerifyError(f"{name} must be >= {minimum}")
    return value


def fetch_page(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise VerifyError(f"{url}: HTTP {status}")
            data = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise VerifyError(f"{url}: request failed: {exc}") from exc

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VerifyError(f"{url}: response is not valid UTF-8") from exc


def verify_once(urls: list[str]) -> list[str]:
    issues: list[str] = []
    for url in urls:
        try:
            html = fetch_page(url)
            if SUPPORT_MARKER not in html:
                issues.append(f"missing direct /support link: {url}")
        except VerifyError as exc:
            issues.append(str(exc))
    return issues


def main() -> int:
    try:
        urls = sitemap_urls()
        attempts = int_env("OUTPOST_LIVE_SUPPORT_ATTEMPTS", 4, 1)
        delay_seconds = int_env("OUTPOST_LIVE_SUPPORT_DELAY_SECONDS", 5, 0)
        last_issues: list[str] = []

        for attempt in range(1, attempts + 1):
            last_issues = verify_once(urls)
            if not last_issues:
                print("OutPOSt live Support Center discovery verifier: PASS")
                print(f"  public sitemap pages checked: {len(urls)}")
                print(f"  direct /support links present: {len(urls)}/{len(urls)}")
                print("  protected application services were not called")
                return 0

            print(
                f"OutPOSt live Support Center discovery verifier: propagation mismatch "
                f"on attempt {attempt}/{attempts} ({len(last_issues)} issue(s))"
            )
            if attempt < attempts and delay_seconds:
                time.sleep(delay_seconds)

        print("OutPOSt live Support Center discovery verifier: FAIL", file=sys.stderr)
        for issue in last_issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    except VerifyError as exc:
        print("OutPOSt live Support Center discovery verifier: FAIL", file=sys.stderr)
        print(f"  - {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
