#!/usr/bin/env python3
"""Read-only live verification for OutPOSt public product maturity/status claims."""

from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import os
import sys
import time

from verify_public_product_maturity import PAGE_CONTRACTS, validate_page_text

ORIGIN = "https://outpost.com.ua"
USER_AGENT = "OutPOSt-Product-Maturity-Live-Verify/1.0"
ATTEMPTS = max(1, int(os.getenv("OUTPOST_LIVE_MATURITY_ATTEMPTS", "4")))
DELAY_SECONDS = max(0.0, float(os.getenv("OUTPOST_LIVE_MATURITY_DELAY_SECONDS", "5")))


class VerifyError(RuntimeError):
    pass


def request(pathname: str, timeout: int = 25) -> tuple[int, str]:
    separator = "&" if "?" in pathname else "?"
    url = f"{ORIGIN}{pathname}{separator}{urlencode({'maturity_verify': int(time.time() * 1000)})}"
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Accept": "text/html,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
            text = response.read().decode("utf-8", errors="replace")
            return status, text
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        raise VerifyError(f"{pathname}: HTTP {exc.code}; body={body[:160]!r}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise VerifyError(f"{pathname}: request failed: {exc}") from exc


def verify_once() -> int:
    checked = 0
    errors: list[str] = []
    for pathname in PAGE_CONTRACTS:
        status, text = request(pathname)
        if status != 200:
            errors.append(f"{pathname}: expected HTTP 200, got {status}")
            continue
        errors.extend(validate_page_text(pathname, text))
        checked += 1

    if errors:
        raise VerifyError("; ".join(errors))
    return checked


def main() -> int:
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            checked = verify_once()
            print("Live product maturity verification: PASS")
            print(f"  live public pages checked: {checked}")
            print("  Native ПРРО / CheckBox / Accounting / еАкциз status contracts match source policy")
            print("  no Cabinet, Director, Sync, D1, Worker API, PRRO API or XTrace API was called")
            return 0
        except Exception as exc:
            last_error = exc
            if attempt < ATTEMPTS:
                print(
                    f"Live product maturity verification attempt {attempt}/{ATTEMPTS} failed: "
                    f"{exc}; retrying..."
                )
                time.sleep(DELAY_SECONDS)

    print(f"Live product maturity verification: FAIL\n  - {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
