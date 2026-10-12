#!/usr/bin/env python3
"""Verify alternate OutPOSt production hosts permanently redirect to the canonical apex host.

Read-only production check for the completed GitHub issue #61 contract. For every canonical URL in
site/sitemap.xml it verifies that https://www.outpost.com.ua and both known
Cloudflare Pages hosts (https://outpostua.pages.dev and
https://outpost-web.pages.dev) return an exact HTTP 301 to the matching
https://outpost.com.ua URL. Representative query-string cases are also checked.

The canonical apex URLs themselves must remain direct HTTP 200 responses. This
makes redirect loops and accidental redirects on the production host fail closed.

The Cloudflare account-level Redirect Rules passed acceptance on 2026-09-11.
This verifier is therefore a mandatory post-merge production gate.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import os
import sys
import time
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
CANONICAL_HOST = "outpost.com.ua"
ALTERNATE_HOSTS = (
    "www.outpost.com.ua",
    "outpostua.pages.dev",
    "outpost-web.pages.dev",
)
EXPECTED_REDIRECT_STATUS = 301
QUERY_PROBE_PATHS = ("/download", "/support")
QUERY_PROBE = "outpost_verify=host-normalization&x=1"
USER_AGENT = "OutPOSt-live-host-normalization-verifier/1.0"


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


OPENER = build_opener(NoRedirectHandler)


def env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise SystemExit(f"{name} must be an integer, got {raw!r}")
    if value < minimum:
        raise SystemExit(f"{name} must be >= {minimum}, got {value}")
    return value


def sitemap_urls() -> list[str]:
    root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    urls = [
        elem.text.strip()
        for elem in root.iter()
        if elem.tag.endswith("loc") and elem.text and elem.text.strip()
    ]
    if not urls:
        raise SystemExit("site/sitemap.xml contains no public URLs")

    for url in urls:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != CANONICAL_HOST
            or parsed.query
            or parsed.fragment
        ):
            raise SystemExit(f"non-canonical sitemap URL cannot be host-normalized safely: {url}")
    return urls


def alternate_url(canonical: str, host: str, query: str = "") -> str:
    parsed = urlparse(canonical)
    return urlunparse(("https", host, parsed.path or "/", "", query, ""))


def canonical_with_query(canonical: str, query: str) -> str:
    parsed = urlparse(canonical)
    return urlunparse(("https", CANONICAL_HOST, parsed.path or "/", "", query, ""))


def redirect_cases(canonicals: list[str]) -> list[tuple[str, str, str]]:
    cases: list[tuple[str, str, str]] = []
    by_path = {urlparse(url).path or "/": url for url in canonicals}

    for canonical in canonicals:
        for host in ALTERNATE_HOSTS:
            cases.append((host, alternate_url(canonical, host), canonical))

    for path in QUERY_PROBE_PATHS:
        canonical = by_path.get(path)
        if canonical is None:
            raise SystemExit(f"query-string probe path is missing from sitemap: {path}")
        expected = canonical_with_query(canonical, QUERY_PROBE)
        for host in ALTERNATE_HOSTS:
            cases.append((f"{host} query", alternate_url(canonical, host, QUERY_PROBE), expected))

    return cases


def probe_once(url: str) -> tuple[int | None, str, str]:
    request = Request(
        url,
        method="GET",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,*/*;q=0.1",
            "Range": "bytes=0-0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    try:
        with OPENER.open(request, timeout=15) as response:
            return int(response.status), response.headers.get("Location", ""), ""
    except HTTPError as exc:
        return exc.code, exc.headers.get("Location", ""), ""
    except URLError as exc:
        return None, "", f"network error: {exc}"
    except Exception as exc:  # pragma: no cover - defensive network boundary
        return None, "", f"{type(exc).__name__}: {exc}"


def redirect_problem(source_url: str, expected: str, status: int | None, location: str, error: str) -> str | None:
    if error:
        return error
    if status != EXPECTED_REDIRECT_STATUS:
        return f"expected HTTP 301, got {status}; Location={location or '-'}"
    if not location:
        return "HTTP 301 is missing Location"
    resolved = urljoin(source_url, location)
    if resolved != expected:
        return f"redirect target mismatch; expected {expected}, got {resolved} (raw Location={location!r})"
    return None


def canonical_problem(url: str, status: int | None, location: str, error: str) -> str | None:
    if error:
        return error
    if status != 200:
        return f"canonical host must remain direct HTTP 200, got {status}; Location={location or '-'}"
    if location:
        return f"canonical HTTP 200 unexpectedly includes Location={location!r}"
    return None


def verify_redirect_case(
    label: str,
    source_url: str,
    expected: str,
    attempts: int,
    delay_seconds: int,
) -> str | None:
    last_problem = "unknown error"
    for attempt in range(1, attempts + 1):
        status, location, error = probe_once(source_url)
        problem = redirect_problem(source_url, expected, status, location, error)
        if problem is None:
            return None
        last_problem = problem
        if attempt < attempts and delay_seconds:
            time.sleep(delay_seconds)
    return f"{label}: {source_url}: {last_problem}"


def verify_canonical_case(url: str, attempts: int, delay_seconds: int) -> str | None:
    last_problem = "unknown error"
    for attempt in range(1, attempts + 1):
        status, location, error = probe_once(url)
        problem = canonical_problem(url, status, location, error)
        if problem is None:
            return None
        last_problem = problem
        if attempt < attempts and delay_seconds:
            time.sleep(delay_seconds)
    return f"canonical: {url}: {last_problem}"


def main() -> int:
    attempts = env_int("OUTPOST_LIVE_HOST_NORMALIZATION_ATTEMPTS", 4, minimum=1)
    delay_seconds = env_int("OUTPOST_LIVE_HOST_NORMALIZATION_DELAY_SECONDS", 5)
    max_workers = env_int("OUTPOST_LIVE_HOST_NORMALIZATION_WORKERS", 8, minimum=1)

    canonicals = sitemap_urls()
    redirects = redirect_cases(canonicals)
    errors: list[str] = []

    work_items = len(redirects) + len(canonicals)
    with ThreadPoolExecutor(max_workers=min(max_workers, work_items)) as pool:
        future_map = {}
        for label, source_url, expected in redirects:
            future_map[
                pool.submit(
                    verify_redirect_case,
                    label,
                    source_url,
                    expected,
                    attempts,
                    delay_seconds,
                )
            ] = source_url
        for canonical in canonicals:
            future_map[
                pool.submit(
                    verify_canonical_case,
                    canonical,
                    attempts,
                    delay_seconds,
                )
            ] = canonical

        for future in as_completed(future_map):
            problem = future.result()
            if problem:
                errors.append(problem)

    if errors:
        print(f"OutPOSt live host normalization verifier: FAIL ({len(errors)} issue(s))")
        for item in sorted(errors):
            print(f"  - {item}")
        print("  expected Cloudflare account-level 301 rules: www + both known pages.dev hosts -> https://outpost.com.ua")
        print("  host-normalization contract is mandatory after the accepted 2026-09-11 Cloudflare apply")
        return 1

    base_redirects = len(canonicals) * len(ALTERNATE_HOSTS)
    query_redirects = len(redirects) - base_redirects
    print("OutPOSt live host normalization verifier: PASS")
    print(f"  canonical apex direct HTTP 200: {len(canonicals)}/{len(canonicals)} sitemap URLs")
    print(f"  alternate-host exact HTTP 301 redirects: {base_redirects}/{base_redirects}")
    print(f"  query-preserving HTTP 301 probes: {query_redirects}/{query_redirects}")
    print("  exact redirect targets prevent alternate-host chains and canonical redirect loops")
    return 0


if __name__ == "__main__":
    sys.exit(main())
