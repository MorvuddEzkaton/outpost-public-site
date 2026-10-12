#!/usr/bin/env python3
"""Verify permanent normalization of canonical public URL variants.

Read-only production check. For every canonical URL in site/sitemap.xml it
verifies HTTP -> HTTPS normalization. For non-root pages it also verifies that
trailing-slash and .html variants permanently redirect to the exact canonical
extensionless URL.

Alternate-host normalization is verified separately by
scripts/verify_live_host_normalization.py, which is a mandatory post-merge
production gate after Cloudflare issue #61 was completed on 2026-09-11.
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
PUBLIC_HOST = "outpost.com.ua"
PERMANENT_REDIRECTS = {301, 308}


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
            or parsed.netloc != PUBLIC_HOST
            or parsed.query
            or parsed.fragment
        ):
            raise SystemExit(f"non-canonical sitemap URL cannot be normalized safely: {url}")
    return urls


def variant_cases(canonical: str) -> list[tuple[str, str, str]]:
    parsed = urlparse(canonical)
    cases = [
        (
            "http",
            urlunparse(("http", parsed.netloc, parsed.path or "/", "", "", "")),
            canonical,
        )
    ]

    if parsed.path not in {"", "/"}:
        path = parsed.path.rstrip("/")
        cases.extend(
            [
                (
                    "trailing-slash",
                    urlunparse(("https", parsed.netloc, f"{path}/", "", "", "")),
                    canonical,
                ),
                (
                    "html",
                    urlunparse(("https", parsed.netloc, f"{path}.html", "", "", "")),
                    canonical,
                ),
            ]
        )
    return cases


def probe_once(source_url: str) -> tuple[int | None, str, str]:
    request = Request(
        source_url,
        method="GET",
        headers={
            "User-Agent": "OutPOSt-live-url-normalization-verifier/1.0",
            "Accept": "text/html,*/*;q=0.1",
            "Range": "bytes=0-0",
            "Cache-Control": "no-cache",
        },
    )

    try:
        with OPENER.open(request, timeout=15) as response:
            return response.status, response.headers.get("Location", ""), ""
    except HTTPError as exc:
        return exc.code, exc.headers.get("Location", ""), ""
    except URLError as exc:
        return None, "", f"network error: {exc}"
    except Exception as exc:  # pragma: no cover - defensive network boundary
        return None, "", f"{type(exc).__name__}: {exc}"


def verify_case(
    kind: str,
    source_url: str,
    canonical: str,
    attempts: int,
    delay_seconds: int,
) -> str | None:
    last_problem = "unknown error"

    for attempt in range(1, attempts + 1):
        status, location, error = probe_once(source_url)
        if error:
            last_problem = error
        elif status not in PERMANENT_REDIRECTS:
            last_problem = (
                f"{kind}: expected permanent HTTP 301/308, got {status}; "
                f"Location={location or '-'}"
            )
        elif not location:
            last_problem = f"{kind}: HTTP {status} is missing Location"
        else:
            resolved = urljoin(source_url, location)
            if resolved != canonical:
                last_problem = (
                    f"{kind}: redirect target mismatch; expected {canonical}, "
                    f"got {resolved} (raw Location={location!r})"
                )
            else:
                return None

        if attempt < attempts and delay_seconds:
            time.sleep(delay_seconds)

    return f"{source_url}: {last_problem}"


def main() -> int:
    attempts = env_int("OUTPOST_LIVE_NORMALIZATION_ATTEMPTS", 4, minimum=1)
    delay_seconds = env_int("OUTPOST_LIVE_NORMALIZATION_DELAY_SECONDS", 5)
    max_workers = env_int("OUTPOST_LIVE_NORMALIZATION_WORKERS", 8, minimum=1)

    canonicals = sitemap_urls()
    cases = [case for canonical in canonicals for case in variant_cases(canonical)]

    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(cases))) as pool:
        future_map = {
            pool.submit(
                verify_case,
                kind,
                source_url,
                canonical,
                attempts,
                delay_seconds,
            ): (kind, source_url, canonical)
            for kind, source_url, canonical in cases
        }
        for future in as_completed(future_map):
            problem = future.result()
            if problem:
                errors.append(problem)

    if errors:
        print(f"OutPOSt live URL normalization verifier: FAIL ({len(errors)} issue(s))")
        for item in sorted(errors):
            print(f"  - {item}")
        print("  alternate hosts are checked separately by verify_live_host_normalization.py")
        return 1

    http_count = len(canonicals)
    path_variant_count = len(cases) - http_count
    print("OutPOSt live URL normalization verifier: PASS")
    print(f"  checked {http_count} HTTP -> HTTPS variants")
    print(f"  checked {path_variant_count} trailing-slash/.html variants")
    print(f"  all {len(cases)} variants use a permanent 301/308 redirect to the exact sitemap canonical")
    print("  alternate hosts are checked separately by the mandatory host-normalization verifier")
    return 0


if __name__ == "__main__":
    sys.exit(main())
