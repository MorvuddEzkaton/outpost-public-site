#!/usr/bin/env python3
"""Offline regressions for live demo static-asset cache verification."""

from __future__ import annotations

from urllib.parse import urlparse

from verify_live_static_assets import (
    DEMO_REVALIDATE_PATHS,
    cache_control_revalidates,
    collect_public_assets,
)
from verify_public_site import DEMO_REVALIDATE_ASSETS as SOURCE_DEMO_REVALIDATE_ASSETS


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_cache_control_contract() -> None:
    require(cache_control_revalidates("no-cache, max-age=0, must-revalidate"), "explicit no-cache must pass")
    require(cache_control_revalidates("public, max-age=0, must-revalidate"), "Cloudflare default revalidation must pass")
    require(cache_control_revalidates("NO-CACHE"), "Cache-Control parsing must be case-insensitive")
    require(not cache_control_revalidates("public, max-age=3600"), "long-lived cache must fail")
    require(not cache_control_revalidates("public, max-age=0"), "max-age=0 without revalidation directive must fail")
    require(not cache_control_revalidates("(missing)"), "missing cache header must fail")


def test_source_and_live_demo_asset_contracts_match() -> None:
    source_paths = set(SOURCE_DEMO_REVALIDATE_ASSETS)
    require(
        source_paths == DEMO_REVALIDATE_PATHS,
        f"source/live demo revalidation contracts drifted: source={sorted(source_paths)}, live={sorted(DEMO_REVALIDATE_PATHS)}",
    )


def test_real_demo_assets_are_discovered() -> None:
    assets, page_count, demo_assets = collect_public_assets()
    require(page_count > 0, "sitemap pages must be discovered")
    require(bool(assets), "public assets must be discovered")

    paths = {urlparse(url).path for url in demo_assets}
    require(
        paths == DEMO_REVALIDATE_PATHS,
        f"demo revalidation asset set drifted: expected {sorted(DEMO_REVALIDATE_PATHS)}, got {sorted(paths)}",
    )
    require(len(demo_assets) == len(DEMO_REVALIDATE_PATHS), "each demo runtime asset must have one current cache-key URL")


def main() -> int:
    tests = (
        test_cache_control_contract,
        test_source_and_live_demo_asset_contracts_match,
        test_real_demo_assets_are_discovered,
    )
    for test in tests:
        test()

    print("Live demo static-asset cache regression: PASS")
    print(f"  {len(tests)}/{len(tests)} offline tests passed")
    print("  source _headers contract and live verifier asset sets are identical")
    print(f"  demo runtime assets discovered: {len(DEMO_REVALIDATE_PATHS)}")
    print("  stale long-lived/missing Cache-Control values fail closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
