#!/usr/bin/env python3
"""Synthetic regressions for changelog release-note count validation."""

from __future__ import annotations

from pathlib import Path
import json

from verify_release_metadata import (
    CHANGELOG_PAGE,
    DOWNLOAD_PAGE,
    INSTALLER_NAME_RE,
    validate_changelog_change_counts,
    validate_changelog_seo_current_release,
)


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



def seo_fixture(search_version="0.24.43", social_version="0.24.43",
                structured_version="0.24.43", social=True, structured=True):
    def description(version):
        return f"Повна історія версій OutPOSt: реліз v{version}; Бухгалтерія v1.0.2."

    social_tag = (
        f'<meta content="{description(social_version)}" property="og:description"/>'
        if social else ""
    )
    graph = json.dumps({
        "@graph": [{
            "@id": "https://outpost.com.ua/changelog#webpage",
            "@type": "WebPage",
            "description": description(structured_version),
        }]
    }, ensure_ascii=False)
    jsonld = f'<script type="application/ld+json">{graph}</script>' if structured else ""
    return (
        '<html><head>'
        f'<meta content="{description(search_version)}" name="description"/>'
        f'{social_tag}{jsonld}'
        '</head><body><div class="changelog-version">'
        '<span>Поточний реліз</span><strong>0.24.43</strong></div></body></html>'
    )


def test_real_changelog_seo_matches_current_release() -> None:
    versions = set(INSTALLER_NAME_RE.findall(DOWNLOAD_PAGE.read_text(encoding="utf-8")))
    require(len(versions) == 1, f"download installer version ambiguous: {versions}")
    errors = validate_changelog_seo_current_release(
        CHANGELOG_PAGE.read_text(encoding="utf-8"), next(iter(versions))
    )
    require(not errors, f"current changelog SEO descriptions are stale: {errors}")


def test_stale_changelog_search_description_fails() -> None:
    errors = validate_changelog_seo_current_release(seo_fixture(search_version="0.24.42"), "0.24.43")
    require(any("description" in e and "0.24.42" in e for e in errors),
            "stale search description should fail")


def test_stale_changelog_social_description_fails() -> None:
    errors = validate_changelog_seo_current_release(seo_fixture(social_version="0.24.42"), "0.24.43")
    require(any("og:description" in e for e in errors), "stale social description should fail")


def test_stale_changelog_jsonld_description_fails() -> None:
    errors = validate_changelog_seo_current_release(seo_fixture(structured_version="0.24.42"), "0.24.43")
    require(any("WebPage JSON-LD description" in e for e in errors),
            "stale structured description should fail")


def test_missing_changelog_social_description_fails() -> None:
    errors = validate_changelog_seo_current_release(seo_fixture(social=False), "0.24.43")
    require(any("expected exactly one og:description" in e for e in errors),
            "missing social description should fail")


def test_aligned_changelog_metadata_passes() -> None:
    errors = validate_changelog_seo_current_release(seo_fixture(), "0.24.43")
    require(not errors, f"aligned metadata should pass: {errors}")


def main() -> int:
    tests = (
        test_real_changelog_passes,
        test_mismatched_count_fails,
        test_duplicate_count_fails,
        test_missing_list_fails,
        test_two_component_historical_version_starts_new_segment,
        test_historical_release_without_count_is_allowed,
        test_real_changelog_seo_matches_current_release,
        test_stale_changelog_search_description_fails,
        test_stale_changelog_social_description_fails,
        test_stale_changelog_jsonld_description_fails,
        test_missing_changelog_social_description_fails,
        test_aligned_changelog_metadata_passes,
    )
    for test in tests:
        test()

    print("Release changelog count regression: PASS")
    print(f"  {len(tests)}/{len(tests)} synthetic/current-source tests passed")
    print("  declared change counts must match release-note item counts")
    print("  changelog search/social/JSON-LD metadata stays aligned with the current release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
