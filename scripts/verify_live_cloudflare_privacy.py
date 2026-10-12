#!/usr/bin/env python3
"""Read-only verification that Cloudflare does not inject analytics/RUM into public HTML.

The public site intentionally uses a strict self-only script CSP and states that it
runs without analytics. Cloudflare Web Analytics / Browser Insights can inject a
third-party beacon at the edge without any repository change, so this verifier
checks the delivered production HTML rather than only source files.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import os
import sys
import time

ORIGIN = "https://outpost.com.ua"
PATHS = (
    "/",
    "/support",
    "/bezkoshtovna-programa-dlya-magazynu",
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
RUM_MARKERS = (
    "static.cloudflareinsights.com",
    "beacon.min.js",
    "cloudflareinsights",
    "data-cf-beacon",
)


class VerifyError(RuntimeError):
    pass


def fetch_page(url: str) -> tuple[int | None, str, dict[str, str], str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            status = int(getattr(response, "status", response.getcode()))
            final_url = response.geturl()
            headers = {key.lower(): value for key, value in response.headers.items()}
            body = response.read(2_000_000).decode("utf-8", "replace")
            return status, final_url, headers, body, ""
    except HTTPError as exc:
        headers = {key.lower(): value for key, value in exc.headers.items()}
        body = exc.read(2_000_000).decode("utf-8", "replace")
        return int(exc.code), exc.geturl(), headers, body, ""
    except (URLError, TimeoutError, OSError) as exc:
        return None, url, {}, "", f"{type(exc).__name__}: {exc}"


def check_page(
    url: str,
    status: int | None,
    final_url: str,
    headers: dict[str, str],
    body: str,
    error: str,
) -> list[str]:
    errors: list[str] = []
    if error:
        return [f"{url}: request error: {error}"]
    if status != 200:
        errors.append(f"{url}: expected HTTP 200, got {status}")
    if final_url != url:
        errors.append(f"{url}: expected direct canonical response, final URL is {final_url}")

    content_type = headers.get("content-type", "").lower()
    if "text/html" not in content_type:
        errors.append(f"{url}: expected text/html response, got {content_type or '-'}")

    lowered = body.lower()
    found = [marker for marker in RUM_MARKERS if marker in lowered]
    if found:
        errors.append(f"{url}: Cloudflare analytics/RUM marker(s) injected: {', '.join(found)}")
    return errors


def verify_once() -> int:
    urls = [f"{ORIGIN}{path}" for path in PATHS]
    results: dict[str, tuple[int | None, str, dict[str, str], str, str]] = {}
    with ThreadPoolExecutor(max_workers=len(urls)) as pool:
        futures = {pool.submit(fetch_page, url): url for url in urls}
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    errors: list[str] = []
    for url in urls:
        errors.extend(check_page(url, *results[url]))

    if errors:
        raise VerifyError("; ".join(errors))

    print(f"  canonical public HTML responses: {len(urls)}/{len(urls)}")
    print("  Cloudflare Web Analytics / Browser Insights markers: 0")
    print("  no cloudflareinsights / beacon.min.js / data-cf-beacon injection detected")
    return len(urls)


def main() -> int:
    attempts = max(1, int(os.environ.get("OUTPOST_LIVE_CLOUDFLARE_PRIVACY_ATTEMPTS", "4")))
    delay = max(0, int(os.environ.get("OUTPOST_LIVE_CLOUDFLARE_PRIVACY_DELAY_SECONDS", "5")))
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            checked = verify_once()
            print("OutPOSt live Cloudflare privacy verification: PASS")
            print(f"  verified {checked}/{checked} representative public HTML pages")
            print("  verifier is read-only; Cabinet, Worker, Telegram, D1 and installer endpoints were not called")
            return 0
        except Exception as exc:
            last_error = exc
            print(f"Attempt {attempt}/{attempts}: {exc}")
            if attempt < attempts:
                time.sleep(delay)

    print(f"OutPOSt live Cloudflare privacy verification: FAIL\n  - {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
