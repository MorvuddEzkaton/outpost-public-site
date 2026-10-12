#!/usr/bin/env python3
"""Read-only production verifier for sitemap canonical/indexability contracts.

Only public outpost.com.ua URLs from the repository sitemap are fetched. The verifier
checks HTTP 200, exact canonical parity, and absence of noindex in HTML/headers. It
never calls Cabinet, Director, Sync, D1 or fiscal services.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen
import os
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
ORIGIN = "https://outpost.com.ua"
ALLOWED_HOST = "outpost.com.ua"


class HeadAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonicals: list[str] = []
        self.robots: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "link" and "canonical" in data.get("rel", "").lower().split():
            href = data.get("href", "").strip()
            if href:
                self.canonicals.append(href)
        if tag.lower() == "meta" and data.get("name", "").lower() == "robots":
            self.robots.append(data.get("content", "").lower())


def sitemap_urls() -> list[str]:
    root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    urls = [
        element.text.strip()
        for element in root.iter()
        if element.tag.endswith("loc") and element.text and element.text.strip()
    ]
    if not urls:
        raise RuntimeError("local sitemap has no URLs")
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST or parsed.query or parsed.fragment:
            raise RuntimeError(f"unexpected local sitemap URL outside canonical public origin: {url}")
    return urls


def cache_bust(url: str, nonce: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["verify_indexability"] = nonce
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query),
            parsed.fragment,
        )
    )


def fetch_public(url: str, nonce: str) -> tuple[int, str, str, str]:
    request = Request(
        cache_bust(url, nonce),
        headers={
            "User-Agent": "OutPOSt-live-indexability-verifier/1.0",
            "Accept": "text/html,*/*;q=0.1",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(request, timeout=15) as response:
        final_url = response.geturl()
        final_host = (urlparse(final_url).hostname or "").lower()
        if final_host != ALLOWED_HOST:
            raise RuntimeError(f"unexpected redirect outside public site: {final_url}")
        body = response.read().decode("utf-8", errors="replace")
        x_robots = response.headers.get("X-Robots-Tag", "").lower()
        return response.status, final_url, x_robots, body


def verify_once(nonce: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    verified: list[str] = []

    try:
        urls = sitemap_urls()
    except Exception as exc:
        return [f"local sitemap: {exc}"], verified

    for url in urls:
        try:
            status, _, x_robots, html = fetch_public(url, nonce)
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            continue

        parser = HeadAudit()
        parser.feed(html)

        if status != 200:
            errors.append(f"{url}: HTTP {status}")
        if parser.canonicals != [url]:
            errors.append(f"{url}: expected exactly canonical {url!r}, got {parser.canonicals!r}")
        if any("noindex" in value for value in parser.robots):
            errors.append(f"{url}: live meta robots contains noindex: {parser.robots!r}")
        if "noindex" in x_robots:
            errors.append(f"{url}: X-Robots-Tag contains noindex: {x_robots!r}")

        if not errors or not any(item.startswith(f"{url}:") for item in errors):
            verified.append(url)

    return errors, verified


def main() -> int:
    attempts = max(1, int(os.getenv("OUTPOST_LIVE_INDEXABILITY_ATTEMPTS", "4")))
    delay = max(0, int(os.getenv("OUTPOST_LIVE_INDEXABILITY_DELAY_SECONDS", "5")))

    last_errors: list[str] = []
    last_verified: list[str] = []
    for attempt in range(1, attempts + 1):
        nonce = f"{int(time.time())}-{attempt}"
        last_errors, last_verified = verify_once(nonce)
        if not last_errors:
            print("Live sitemap indexability: PASS")
            print(f"  canonical/indexable public pages verified: {len(last_verified)}")
            print("  HTTP 200 + exact canonical + no noindex in meta/X-Robots-Tag")
            print("  cache busting used; protected services were not called")
            return 0
        if attempt < attempts:
            time.sleep(delay)

    print(f"Live sitemap indexability: FAIL ({len(last_errors)} issue(s))", file=sys.stderr)
    for error in last_errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
