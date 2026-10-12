#!/usr/bin/env python3
"""Offline regression tests for OutPOSt IndexNow submission logic."""

from __future__ import annotations

from pathlib import Path
import json

import submit_indexnow as indexnow

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_repository_key_contract() -> None:
    require(8 <= len(indexnow.KEY) <= 128, "IndexNow key length is invalid")
    require(all(ch.isalnum() or ch == "-" for ch in indexnow.KEY), "IndexNow key contains invalid characters")
    key_file = ROOT / indexnow.KEY_RELATIVE_PATH
    require(key_file.is_file(), "IndexNow key file is missing")
    require(key_file.read_text(encoding="utf-8").strip() == indexnow.KEY, "IndexNow key file content mismatch")


def test_current_sitemap_contract() -> None:
    mapping = indexnow.parse_sitemap((ROOT / "site" / "sitemap.xml").read_text(encoding="utf-8"))
    # New public pages (e.g. the v0.24.10 screenshot tour) are expected to grow
    # the sitemap. Guard the accepted baseline without blocking future additions.
    require(len(mapping) >= 24, f"expected at least 24 public sitemap URLs, got {len(mapping)}")
    require(mapping["site/interfeis.html"] == "https://outpost.com.ua/interfeis",
            "real-screenshot gallery is missing from canonical sitemap")
    require(mapping["site/index.html"] == "https://outpost.com.ua/", "homepage mapping mismatch")
    require(mapping["site/support.html"] == "https://outpost.com.ua/support", "support mapping mismatch")
    require(all(url.startswith(indexnow.ORIGIN + "/") for url in mapping.values()), "non-canonical URL in sitemap mapping")


def test_changed_url_selection() -> None:
    current = {
        "site/index.html": "https://outpost.com.ua/",
        "site/support.html": "https://outpost.com.ua/support",
        "site/new-page.html": "https://outpost.com.ua/new-page",
    }
    base = {
        "site/index.html": "https://outpost.com.ua/",
        "site/support.html": "https://outpost.com.ua/support",
        "site/old-page.html": "https://outpost.com.ua/old-page",
    }
    selected = indexnow.select_urls(
        {"site/support.html", "site/old-page.html", "site/styles.css", "site/_worker.js"},
        current,
        base,
    )
    require(
        selected == ["https://outpost.com.ua/old-page", "https://outpost.com.ua/support"],
        f"unexpected changed URL selection: {selected!r}",
    )


def test_key_bootstrap_seeds_current_sitemap() -> None:
    current = {
        "site/index.html": "https://outpost.com.ua/",
        "site/support.html": "https://outpost.com.ua/support",
    }
    selected = indexnow.select_urls({indexnow.KEY_RELATIVE_PATH}, current, {})
    require(selected == ["https://outpost.com.ua/", "https://outpost.com.ua/support"], "key bootstrap did not seed current URLs")


def test_payload_contract() -> None:
    payload = json.loads(indexnow.build_payload(["https://outpost.com.ua/support"]).decode("utf-8"))
    require(payload["host"] == "outpost.com.ua", "payload host mismatch")
    require(payload["key"] == indexnow.KEY, "payload key mismatch")
    require(payload["keyLocation"] == indexnow.KEY_URL, "payload keyLocation mismatch")
    require(payload["urlList"] == ["https://outpost.com.ua/support"], "payload URL list mismatch")


def test_fail_closed_inputs() -> None:
    try:
        indexnow.source_path_for_url("https://example.com/support")
    except indexnow.IndexNowError:
        pass
    else:
        raise AssertionError("foreign sitemap URL unexpectedly passed")

    try:
        indexnow.build_payload([])
    except indexnow.IndexNowError:
        pass
    else:
        raise AssertionError("empty payload unexpectedly passed")


def main() -> int:
    tests = (
        test_repository_key_contract,
        test_current_sitemap_contract,
        test_changed_url_selection,
        test_key_bootstrap_seeds_current_sitemap,
        test_payload_contract,
        test_fail_closed_inputs,
    )
    try:
        for test in tests:
            test()
    except (AssertionError, indexnow.IndexNowError) as exc:
        print("OutPOSt IndexNow synthetic tests: FAIL")
        print(f"  - {exc}")
        return 1

    print("OutPOSt IndexNow synthetic tests: PASS")
    print(f"  {len(tests)}/{len(tests)} offline tests passed")
    print("  canonical sitemap mapping, deletion handling, bootstrap and payload contract are guarded")
    print("  production network was not called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
