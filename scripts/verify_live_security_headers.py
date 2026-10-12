#!/usr/bin/env python3
"""Read-only post-deploy verification of OutPOSt browser security headers.

Expected CSP, Permissions-Policy and scalar header contracts are imported from the
existing source guard so source and live verification cannot silently drift apart.
Only public sitemap pages and one fresh unknown route are requested.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import os
import sys
import time
import xml.etree.ElementTree as ET

import verify_security_headers as security

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SITEMAP = SITE / "sitemap.xml"
HEADERS_FILE = SITE / "_headers"
ORIGIN = "https://outpost.com.ua"
USER_AGENT = "OutPOSt-Live-Security-Headers-Verify/1.0"


class VerifyError(RuntimeError):
    pass


def source_contract_ready() -> None:
    if not HEADERS_FILE.is_file():
        raise VerifyError("site/_headers is missing")
    routes, _ = security.parse_headers(HEADERS_FILE.read_text(encoding="utf-8"))
    route_errors = security.header_route_errors(routes)
    if route_errors:
        raise VerifyError("; ".join(route_errors))


def sitemap_urls() -> list[str]:
    try:
        root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        raise VerifyError(f"cannot parse site/sitemap.xml: {exc}") from exc

    urls = [
        node.text.strip()
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] == "loc" and node.text and node.text.strip()
    ]
    if not urls:
        raise VerifyError("site/sitemap.xml contains no public URLs")
    if any(not url.startswith(f"{ORIGIN}/") for url in urls):
        raise VerifyError("sitemap contains a URL outside the canonical public origin")
    return urls


def fetch_headers(url: str) -> tuple[int | None, dict[str, str], str]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Accept": "text/html,*/*;q=0.1",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            status = int(getattr(response, "status", response.getcode()))
            headers = {key.lower(): value for key, value in response.headers.items()}
            return status, headers, ""
    except HTTPError as exc:
        headers = {key.lower(): value for key, value in exc.headers.items()}
        return int(exc.code), headers, ""
    except (URLError, TimeoutError, OSError) as exc:
        return None, {}, f"{type(exc).__name__}: {exc}"


def check_response(url: str, status: int | None, headers: dict[str, str], error: str, expected_status: int) -> list[str]:
    errors: list[str] = []
    if error:
        return [f"{url}: request error: {error}"]
    if status != expected_status:
        errors.append(f"{url}: expected HTTP {expected_status}, got {status}")

    for name, expected in security.EXPECTED_SCALAR_HEADERS.items():
        actual = headers.get(name.lower())
        if actual != expected:
            errors.append(f"{url}: {name} expected {expected!r}, got {actual!r}")

    csp_value = headers.get("content-security-policy", "")
    if not csp_value:
        errors.append(f"{url}: Content-Security-Policy is missing")
    else:
        actual_csp = security.parse_csp(csp_value)
        if actual_csp != security.EXPECTED_CSP:
            errors.append(f"{url}: live CSP differs from protected source contract: {actual_csp!r}")

    permissions_value = headers.get("permissions-policy", "")
    if not permissions_value:
        errors.append(f"{url}: Permissions-Policy is missing")
    else:
        actual_permissions = security.parse_permissions(permissions_value)
        if actual_permissions != security.EXPECTED_PERMISSIONS:
            errors.append(f"{url}: live Permissions-Policy differs from protected source contract: {actual_permissions!r}")

    return errors


def verify_once() -> int:
    source_contract_ready()
    public_urls = sitemap_urls()
    missing_url = f"{ORIGIN}/definitely-missing-security-{int(time.time())}-{os.getpid()}"
    targets = [(url, 200) for url in public_urls] + [(missing_url, 404)]

    results: dict[str, tuple[int | None, dict[str, str], str]] = {}
    with ThreadPoolExecutor(max_workers=min(10, len(targets))) as pool:
        futures = {pool.submit(fetch_headers, url): url for url, _ in targets}
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    errors: list[str] = []
    for url, expected_status in targets:
        status, headers, error = results[url]
        errors.extend(check_response(url, status, headers, error, expected_status))

    if errors:
        raise VerifyError("; ".join(errors))

    print(f"  sitemap responses: {len(public_urls)}/{len(public_urls)}")
    print("  fresh 404 response: 1/1")
    print("  CSP, Permissions-Policy, X-Frame-Options, nosniff and Referrer-Policy match source contract")
    return len(targets)


def main() -> int:
    attempts = max(1, int(os.environ.get("OUTPOST_LIVE_SECURITY_ATTEMPTS", "4")))
    delay = max(0, int(os.environ.get("OUTPOST_LIVE_SECURITY_DELAY_SECONDS", "5")))
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            checked = verify_once()
            print("OutPOSt live security headers verification: PASS")
            print(f"  protected browser security headers verified on {checked}/{checked} public responses")
            print("  protected services, Cabinet APIs and installer/download files were not called")
            return 0
        except Exception as exc:
            last_error = exc
            print(f"Attempt {attempt}/{attempts}: {exc}")
            if attempt < attempts:
                time.sleep(delay)

    print(f"OutPOSt live security headers verification: FAIL\n  - {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
