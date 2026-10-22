#!/usr/bin/env python3
"""Offline regression tests for verify_sitemap_freshness.py."""

from __future__ import annotations

from datetime import date

from verify_sitemap_freshness import VerifyError, freshness_error, future_lastmod_error, parse_iso_date
from verify_release_sitemap import PUBLIC_ORIGIN, validate_release_dates


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_equal_date_passes() -> None:
    current = date(2026, 9, 8)
    require(freshness_error("https://outpost.com.ua/features", current, current) is None, "equal date must pass")


def test_newer_lastmod_passes() -> None:
    require(
        freshness_error(
            "https://outpost.com.ua/features",
            date(2026, 9, 9),
            date(2026, 9, 8),
        )
        is None,
        "newer lastmod must pass",
    )


def test_stale_lastmod_fails_closed() -> None:
    error = freshness_error(
        "https://outpost.com.ua/features",
        date(2026, 9, 7),
        date(2026, 9, 8),
    )
    require(error is not None and "older than latest HTML Git change" in error, "stale lastmod must fail")


def test_invalid_date_fails_closed() -> None:
    try:
        parse_iso_date("08.09.2026", "synthetic")
    except VerifyError:
        return
    raise AssertionError("non-ISO lastmod must fail")


def test_future_lastmod_fails_closed() -> None:
    error = future_lastmod_error(
        "https://outpost.com.ua/features",
        date(2026, 9, 16),
        date(2026, 9, 15),
    )
    require(error is not None and "in the future" in error, "future lastmod must fail")


def test_today_lastmod_passes() -> None:
    current = date(2026, 9, 15)
    require(
        future_lastmod_error("https://outpost.com.ua/features", current, current) is None,
        "today's lastmod must pass",
    )



def test_independent_changelog_lastmod_is_valid() -> None:
    dates = {
        f"{PUBLIC_ORIGIN}/": date(2026, 10, 20),
        f"{PUBLIC_ORIGIN}/download": date(2026, 10, 20),
        f"{PUBLIC_ORIGIN}/changelog": date(2026, 10, 22),
    }
    require(
        validate_release_dates(dates, date(2026, 10, 22)) == [],
        "metadata-only changelog changes must not fake edits to homepage/download",
    )


def test_release_sitemap_still_rejects_future_dates() -> None:
    dates = {
        f"{PUBLIC_ORIGIN}/": date(2026, 10, 20),
        f"{PUBLIC_ORIGIN}/download": date(2026, 10, 20),
        f"{PUBLIC_ORIGIN}/changelog": date(2026, 10, 23),
    }
    errors = validate_release_dates(dates, date(2026, 10, 22))
    require(
        len(errors) == 1 and "in the future" in errors[0] and "/changelog" in errors[0],
        "release sitemap must still fail closed for future dates",
    )


def main() -> int:
    tests = (
        test_equal_date_passes,
        test_newer_lastmod_passes,
        test_stale_lastmod_fails_closed,
        test_invalid_date_fails_closed,
        test_future_lastmod_fails_closed,
        test_today_lastmod_passes,
        test_independent_changelog_lastmod_is_valid,
        test_release_sitemap_still_rejects_future_dates,
    )
    for test in tests:
        test()
    print("Sitemap Git freshness synthetic tests: PASS")
    print(f"  {len(tests)}/{len(tests)} offline tests passed")
    print("  stale, future and invalid lastmod dates fail closed")
    print("  non-release changelog copy may have its own truthful lastmod date")
    print("  production network was not called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
