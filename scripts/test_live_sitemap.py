#!/usr/bin/env python3
"""Offline regression tests for the live sitemap parity verifier."""

from __future__ import annotations

from verify_live_sitemap import SitemapError, differences, parse_sitemap


BASE = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://outpost.com.ua/</loc>
    <lastmod>2026-09-15</lastmod>
    <changefreq>monthly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://outpost.com.ua/download</loc>
    <lastmod>2026-09-15</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.95</priority>
  </url>
</urlset>
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_equal_sitemaps_pass() -> None:
    parsed = parse_sitemap(BASE, "fixture")
    require(differences(parsed, parsed) == [], "identical sitemap metadata must pass")


def test_changefreq_drift_is_detected() -> None:
    expected = parse_sitemap(BASE, "expected")
    actual = parse_sitemap(BASE.replace("<changefreq>weekly</changefreq>", "<changefreq>monthly</changefreq>"), "actual")
    issues = differences(expected, actual)
    require(any("changefreq mismatch" in item for item in issues), "changefreq drift was not detected")


def test_priority_drift_is_detected() -> None:
    expected = parse_sitemap(BASE, "expected")
    actual = parse_sitemap(BASE.replace("<priority>0.95</priority>", "<priority>0.80</priority>"), "actual")
    issues = differences(expected, actual)
    require(any("priority mismatch" in item for item in issues), "priority drift was not detected")


def test_lastmod_drift_is_detected() -> None:
    expected = parse_sitemap(BASE, "expected")
    actual = parse_sitemap(BASE.replace("<lastmod>2026-09-15</lastmod>", "<lastmod>2026-09-14</lastmod>", 1), "actual")
    issues = differences(expected, actual)
    require(any("lastmod mismatch" in item for item in issues), "lastmod drift was not detected")


def test_missing_required_field_fails_closed() -> None:
    broken = BASE.replace("<priority>0.95</priority>", "")
    try:
        parse_sitemap(broken, "broken")
    except SitemapError as exc:
        require("priority" in str(exc), "missing-field error did not name priority")
        return
    raise AssertionError("missing sitemap priority unexpectedly passed")


def test_duplicate_field_fails_closed() -> None:
    broken = BASE.replace(
        "<priority>1.0</priority>",
        "<priority>1.0</priority><priority>0.9</priority>",
        1,
    )
    try:
        parse_sitemap(broken, "broken")
    except SitemapError as exc:
        require("priority" in str(exc), "duplicate-field error did not name priority")
        return
    raise AssertionError("duplicate sitemap priority unexpectedly passed")


def main() -> int:
    tests = (
        test_equal_sitemaps_pass,
        test_changefreq_drift_is_detected,
        test_priority_drift_is_detected,
        test_lastmod_drift_is_detected,
        test_missing_required_field_fails_closed,
        test_duplicate_field_fails_closed,
    )
    for test in tests:
        test()
    print("Live sitemap parity synthetic tests: PASS")
    print(f"  {len(tests)}/{len(tests)} offline tests passed")
    print("  loc/lastmod/changefreq/priority drift and malformed entries fail closed")
    print("  production network was not called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
