#!/usr/bin/env python3
"""Offline regressions for live demo static-asset cache verification."""

from __future__ import annotations

import hashlib
from http.client import IncompleteRead, RemoteDisconnected
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
import verify_live_production as production
import verify_live_static_assets as static_assets

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


def response_for(url, payload, status=206, headers=None):
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = status
    response.geturl.return_value = url
    response.getcode.return_value = status
    response.headers = headers if headers is not None else {
        "Content-Range": f"bytes 0-{len(payload) - 1}/{len(payload)}",
        "Content-Type": "application/octet-stream",
    }
    response.read.return_value = payload
    return response


def expect_failure(call, expected):
    try:
        call()
    except production.VerifyError as exc:
        require(expected in str(exc), f"unexpected failure: {exc}")
    else:
        raise AssertionError("invalid response accepted")


def test_installer_retry_restarts_full_range_and_verifies_exact_bytes():
    payload = b"synthetic installer bytes"
    name = "synthetic.exe"
    url = production.ORIGIN + "/downloads/" + name
    sha = hashlib.sha256(payload).hexdigest().upper()
    partial = response_for(url, payload)
    partial.read.side_effect = IncompleteRead(payload[:4], len(payload) - 4)
    full = response_for(url, payload)
    with patch.object(production, "urlopen", side_effect=[partial, full]) as read, \
            patch.object(production.time, "sleep") as pause:
        production.verify_installer(name, len(payload), sha)
        require(read.call_count == 2, "only the interrupted GET should repeat")
        require(pause.call_count == 1, "one bounded backoff expected")
        for call in read.call_args_list:
            request = call.args[0]
            require(request.get_method() == "GET", "verification must remain read-only")
            require(request.full_url == url, "retries must keep the exact URL")
            require(request.get_header("Range") == "bytes=0-", "range must never be dropped")
            require(request.get_header("Accept-encoding") == "identity", "representation must stay identical")


def test_persistent_transport_failure_exhausts_budget():
    url = production.ORIGIN + "/downloads/synthetic.exe"
    with patch.object(production, "urlopen", side_effect=[
        IncompleteRead(b"partial", 20), RemoteDisconnected(), URLError(TimeoutError())
    ]) as read, patch.object(production.time, "sleep") as pause:
        expect_failure(lambda: production.request_bytes(url, range_request=True), "after 3 attempts")
        require(read.call_count == 3, "transport retry budget must be finite")
        require(pause.call_count == 2, "no further sleep after final failure")


def test_invalid_installer_contract_never_retries_or_passes():
    payload = b"synthetic installer bytes"
    name = "synthetic.exe"
    url = production.ORIGIN + "/downloads/" + name
    sha = hashlib.sha256(payload).hexdigest().upper()
    good_range = f"bytes 0-{len(payload) - 1}/{len(payload)}"
    cases = (
        (payload, 200, good_range, sha, "HTTP 206"),
        (payload, 206, "", sha, "Content-Range mismatch"),
        (payload, 206, f"bytes 1-{len(payload) - 1}/{len(payload)}", sha, "Content-Range mismatch"),
        (payload[:-1], 206, good_range, sha, "size mismatch"),
        (payload, 206, good_range, "0" * 64, "SHA-256 mismatch"),
    )
    for body, status, header, expected_sha, error in cases:
        response = response_for(url, body, status, {"Content-Range": header})
        with patch.object(production, "urlopen", return_value=response) as read, \
                patch.object(production.time, "sleep") as pause:
            expect_failure(lambda: production.verify_installer(name, len(payload), expected_sha), error)
            require(read.call_count == 1, "semantic mismatches must fail immediately")
            pause.assert_not_called()


def test_http_error_is_not_a_transport_retry():
    url = production.ORIGIN + "/downloads/synthetic.exe"
    error = HTTPError(url, 403, "Forbidden", {}, None)
    with patch.object(production, "urlopen", side_effect=error) as read, \
            patch.object(production.time, "sleep") as pause:
        expect_failure(lambda: production.request_bytes(url, range_request=True), "HTTP 403")
        read.assert_called_once()
        pause.assert_not_called()


def test_static_asset_remote_disconnect_recovers_within_existing_budget():
    url = static_assets.ORIGIN + "/assets/synthetic.css"
    full = response_for(url, b"body{}", 200, {
        "Content-Type": "text/css", "Cache-Control": "no-cache"
    })
    with patch.object(static_assets, "build_opener") as opener, \
            patch.object(static_assets.time, "sleep") as pause:
        opener.return_value.open.side_effect = [RemoteDisconnected(), full]
        problem, cache = static_assets.verify_asset(url, 3, 0)
        require(problem is None and cache == "no-cache", "valid response after disconnect must pass")
        require(opener.return_value.open.call_count == 2, "one asset GET retry expected")
        require(pause.call_count == 1, "existing backoff must be applied")


def test_static_asset_exhaustion_and_mime_mismatch_remain_fail_closed():
    url = static_assets.ORIGIN + "/assets/synthetic.css"
    with patch.object(static_assets, "build_opener") as opener, \
            patch.object(static_assets.time, "sleep") as pause:
        opener.return_value.open.side_effect = RemoteDisconnected()
        problem, _ = static_assets.verify_asset(url, 2, 0)
        require(problem is not None and "RemoteDisconnected" in problem, "exhausted transport must fail")
        require(opener.return_value.open.call_count == 2, "existing per-asset limit must be preserved")
        require(pause.call_count == 1, "no retry after exhaustion")
    wrong = response_for(url, b"<html>", 200, {"Content-Type": "text/html"})
    with patch.object(static_assets, "build_opener") as opener, \
            patch.object(static_assets.time, "sleep"):
        opener.return_value.open.return_value = wrong
        problem, _ = static_assets.verify_asset(url, 2, 0)
        require(problem is not None and "content-type" in problem, "wrong MIME must fail")


def main() -> int:
    tests = (
        test_cache_control_contract,
        test_source_and_live_demo_asset_contracts_match,
        test_real_demo_assets_are_discovered,
        test_installer_retry_restarts_full_range_and_verifies_exact_bytes,
        test_persistent_transport_failure_exhausts_budget,
        test_invalid_installer_contract_never_retries_or_passes,
        test_http_error_is_not_a_transport_retry,
        test_static_asset_remote_disconnect_recovers_within_existing_budget,
        test_static_asset_exhaustion_and_mime_mismatch_remain_fail_closed,
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
