#!/usr/bin/env python3
"""Offline synthetic tests for verify_live_host_normalization.py."""

from __future__ import annotations

from pathlib import Path
import importlib.util
import sys


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "verify_live_host_normalization.py"

spec = importlib.util.spec_from_file_location("verify_live_host_normalization", MODULE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load verify_live_host_normalization.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_case_generation() -> None:
    canonicals = [
        "https://outpost.com.ua/",
        "https://outpost.com.ua/download",
        "https://outpost.com.ua/support",
    ]
    cases = module.redirect_cases(canonicals)
    require(len(cases) == 15, f"expected 15 redirect cases, got {len(cases)}")

    expected = {
        ("www.outpost.com.ua", "https://www.outpost.com.ua/", "https://outpost.com.ua/"),
        ("outpostua.pages.dev", "https://outpostua.pages.dev/", "https://outpost.com.ua/"),
        ("outpost-web.pages.dev", "https://outpost-web.pages.dev/", "https://outpost.com.ua/"),
        (
            "www.outpost.com.ua query",
            "https://www.outpost.com.ua/download?outpost_verify=host-normalization&x=1",
            "https://outpost.com.ua/download?outpost_verify=host-normalization&x=1",
        ),
        (
            "outpostua.pages.dev query",
            "https://outpostua.pages.dev/support?outpost_verify=host-normalization&x=1",
            "https://outpost.com.ua/support?outpost_verify=host-normalization&x=1",
        ),
        (
            "outpost-web.pages.dev query",
            "https://outpost-web.pages.dev/support?outpost_verify=host-normalization&x=1",
            "https://outpost.com.ua/support?outpost_verify=host-normalization&x=1",
        ),
    }
    require(expected.issubset(set(cases)), "generated cases do not preserve host/path/query expectations")


def test_redirect_evaluation() -> None:
    source = "https://www.outpost.com.ua/download?x=1"
    expected = "https://outpost.com.ua/download?x=1"

    require(module.redirect_problem(source, expected, 301, expected, "") is None, "exact 301 must pass")
    require(
        "redirect target mismatch" in module.redirect_problem(source, expected, 301, "/download?x=1", ""),
        "relative Location on the alternate host must fail because it stays on the duplicate host",
    )
    require(
        "expected HTTP 301" in module.redirect_problem(source, expected, 200, "", ""),
        "direct alternate-host HTTP 200 must fail",
    )
    require(
        "redirect target mismatch" in module.redirect_problem(
            source,
            expected,
            301,
            "https://outpost.com.ua/download",
            "",
        ),
        "dropped query string must fail",
    )
    require(
        "redirect target mismatch" in module.redirect_problem(
            source,
            expected,
            301,
            "https://www.outpost.com.ua/download?x=1",
            "",
        ),
        "redirect loop target must fail",
    )
    require(
        "network error" in module.redirect_problem(source, expected, None, "", "network error: synthetic"),
        "network errors must fail closed",
    )


def test_canonical_evaluation() -> None:
    canonical = "https://outpost.com.ua/download"
    require(module.canonical_problem(canonical, 200, "", "") is None, "canonical direct 200 must pass")
    require(
        "must remain direct HTTP 200" in module.canonical_problem(
            canonical,
            301,
            "https://outpost.com.ua/download",
            "",
        ),
        "canonical redirect/loop must fail",
    )
    require(
        "unexpectedly includes Location" in module.canonical_problem(
            canonical,
            200,
            "https://outpost.com.ua/download",
            "",
        ),
        "canonical HTTP 200 with Location must fail closed",
    )


def test_real_sitemap_shape() -> None:
    canonicals = module.sitemap_urls()
    require(len(canonicals) >= 1, "real sitemap must not be empty")
    require(
        set(module.ALTERNATE_HOSTS)
        == {"www.outpost.com.ua", "outpostua.pages.dev", "outpost-web.pages.dev"},
        "all known duplicate production hosts must stay in the verifier",
    )
    paths = {module.urlparse(url).path or "/" for url in canonicals}
    for required in module.QUERY_PROBE_PATHS:
        require(required in paths, f"required query probe path missing from real sitemap: {required}")

    cases = module.redirect_cases(canonicals)
    expected_count = len(canonicals) * len(module.ALTERNATE_HOSTS) + len(module.QUERY_PROBE_PATHS) * len(module.ALTERNATE_HOSTS)
    require(len(cases) == expected_count, "real sitemap generated unexpected host-normalization case count")


def main() -> int:
    tests = (
        test_case_generation,
        test_redirect_evaluation,
        test_canonical_evaluation,
        test_real_sitemap_shape,
    )
    for test in tests:
        test()
    print("OutPOSt host normalization synthetic tests: PASS")
    print(f"  {len(tests)}/{len(tests)} offline tests passed")
    print("  all three alternate hosts are covered")
    print("  alternate-host direct 200, relative-host loop, dropped query and wrong-target cases fail closed")
    print("  production network was not called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
