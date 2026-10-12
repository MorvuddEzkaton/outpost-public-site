#!/usr/bin/env python3
"""Synthetic regressions for changelog release-note count validation."""

from __future__ import annotations

from pathlib import Path

from verify_release_metadata import CHANGELOG_PAGE, validate_changelog_change_counts


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_real_changelog_passes() -> None:
    html = CHANGELOG_PAGE.read_text(encoding="utf-8")
    errors = validate_changelog_change_counts(html)
    require(not errors, f"real changelog count contract failed: {errors}")


def test_mismatched_count_fails() -> None:
    html = """
    <h2>v1.2.3 — fixture</h2>
    <div class="changelog-facts"><span>2 основних змін</span></div>
    <ul class="release-notes-list"><li>One</li><li>Two</li><li>Three</li></ul>
    """
    errors = validate_changelog_change_counts(html)
    require(
        any("declares 2" in error and "has 3 release-note items" in error for error in errors),
        "mismatched declared/actual changelog count must fail",
    )


def test_duplicate_count_fails() -> None:
    html = """
    <h2>v1.2.3 — fixture</h2>
    <span>1 основних змін</span><span>1 основних змін</span>
    <ul class="release-notes-list"><li>One</li></ul>
    """
    errors = validate_changelog_change_counts(html)
    require(any("exactly one" in error for error in errors), "duplicate declared count must fail")


def test_missing_list_fails() -> None:
    html = """
    <h2>v1.2.3 — fixture</h2>
    <span>1 основних змін</span>
    <p>No release list.</p>
    """
    errors = validate_changelog_change_counts(html)
    require(any("release-notes-list" in error for error in errors), "declared count without list must fail")


def test_two_component_historical_version_starts_new_segment() -> None:
    html = """
    <h2>v0.24.1 — fixture</h2>
    <span>1 основних змін</span>
    <ul class="release-notes-list"><li>One</li></ul>
    <h2>v0.24 — historical fixture</h2>
    <span>2 основних змін</span>
    <ul class="release-notes-list"><li>One</li><li>Two</li></ul>
    """
    require(
        not validate_changelog_change_counts(html),
        "two-component historical versions must start a new changelog segment",
    )


def test_historical_release_without_count_is_allowed() -> None:
    html = """
    <h2>v1.2.3 — historical fixture</h2>
    <ul class="release-notes-list"><li>Historical note</li></ul>
    """
    require(
        not validate_changelog_change_counts(html),
        "historical release without a declared 'основних змін' count must remain allowed",
    )


def main() -> int:
    tests = (
        test_real_changelog_passes,
        test_mismatched_count_fails,
        test_duplicate_count_fails,
        test_missing_list_fails,
        test_two_component_historical_version_starts_new_segment,
        test_historical_release_without_count_is_allowed,
    )
    for test in tests:
        test()

    print("Release changelog count regression: PASS")
    print(f"  {len(tests)}/{len(tests)} synthetic/current-source tests passed")
    print("  declared change counts must match release-note item counts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
