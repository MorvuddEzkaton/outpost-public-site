#!/usr/bin/env python3
"""Offline regression tests for the Cloudflare privacy live verifier.

No production network requests are made here. The tests exercise the pure response
checker so pre-merge CI guards the acceptance logic without calling production.
The accepted production contract is enforced separately by the post-merge live
production workflow.
"""

from __future__ import annotations

import verify_live_cloudflare_privacy as privacy

URL = "https://outpost.com.ua/"
HTML_HEADERS = {"content-type": "text/html; charset=utf-8"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_clean_page_passes() -> None:
    errors = privacy.check_page(
        URL,
        200,
        URL,
        HTML_HEADERS,
        "<!doctype html><html><body><h1>OutPOSt</h1></body></html>",
        "",
    )
    require(errors == [], f"clean page failed unexpectedly: {errors!r}")


def test_cloudflare_rum_fails_closed() -> None:
    body = (
        '<!doctype html><html><body><script defer '
        'src="https://static.cloudflareinsights.com/beacon.min.js/v123"></script>'
        "</body></html>"
    )
    errors = privacy.check_page(URL, 200, URL, HTML_HEADERS, body, "")
    combined = "\n".join(errors)
    require(errors, "Cloudflare RUM injection unexpectedly passed")
    require("static.cloudflareinsights.com" in combined, "failure did not name the injected host")
    require("beacon.min.js" in combined, "failure did not name the injected beacon")


def test_cloudflare_beacon_attribute_fails_closed() -> None:
    body = (
        '<!doctype html><html><body><script src="/edge-script.js" '
        'data-cf-beacon="{&quot;token&quot;:&quot;fixture&quot;}"></script>'
        "</body></html>"
    )
    errors = privacy.check_page(URL, 200, URL, HTML_HEADERS, body, "")
    combined = "\n".join(errors)
    require(errors, "Cloudflare data-cf-beacon marker unexpectedly passed")
    require("data-cf-beacon" in combined, "failure did not name the Cloudflare beacon attribute")


def test_redirect_fails_closed() -> None:
    errors = privacy.check_page(
        URL,
        200,
        "https://www.outpost.com.ua/",
        HTML_HEADERS,
        "<!doctype html><html></html>",
        "",
    )
    require(any("direct canonical response" in item for item in errors), "redirect mismatch unexpectedly passed")


def test_non_html_fails_closed() -> None:
    errors = privacy.check_page(URL, 200, URL, {"content-type": "application/json"}, "{}", "")
    require(any("text/html" in item for item in errors), "non-HTML response unexpectedly passed")


def test_request_error_fails_closed() -> None:
    errors = privacy.check_page(URL, None, URL, {}, "", "URLError: fixture failure")
    require(errors == [f"{URL}: request error: URLError: fixture failure"], "request error was not preserved")


def main() -> int:
    tests = (
        test_clean_page_passes,
        test_cloudflare_rum_fails_closed,
        test_cloudflare_beacon_attribute_fails_closed,
        test_redirect_fails_closed,
        test_non_html_fails_closed,
        test_request_error_fails_closed,
    )
    try:
        for test in tests:
            test()
    except AssertionError as exc:
        print("Cloudflare privacy verifier synthetic tests: FAIL")
        print(f"  - {exc}")
        return 1

    print("Cloudflare privacy verifier synthetic tests: PASS")
    print(f"  {len(tests)}/{len(tests)} offline tests passed")
    print("  clean HTML passes; RUM markers, redirect drift, non-HTML and request errors fail closed")
    print("  production network was not called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
