#!/usr/bin/env python3
"""Offline regression tests for verify_public_product_maturity.py."""

from __future__ import annotations

from pathlib import Path
from accounting_release_meta import load_accounting_release

from verify_public_product_maturity import (
    PAGE_CONTRACTS,
    source_text,
    validate_global_html_text,
    validate_page_text,
    validate_runtime_script_text,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_real_sources_pass() -> None:
    for pathname in PAGE_CONTRACTS:
        errors = validate_page_text(pathname, source_text(pathname))
        require(not errors, f"{pathname} current source must pass: {errors}")
    runtime_text = (Path(__file__).resolve().parents[1] / "site" / "script.js").read_text(encoding="utf-8")
    runtime_errors = validate_runtime_script_text(runtime_text)
    require(not runtime_errors, f"/script.js current source must pass: {runtime_errors}")


def test_required_disclaimer_fails_closed() -> None:
    pathname = "/eakcyz"
    text = source_text(pathname)
    marker = "Production і будь-які віддалені записи залишаються заблокованими"
    mutated = text.replace(marker, "", 1)
    errors = validate_page_text(pathname, mutated)
    require(any("missing maturity/status marker" in error for error in errors), "missing eАкциз disclaimer must fail")


def test_features_version_regression_fails() -> None:
    pathname = "/features"
    text = source_text(pathname)
    version = load_accounting_release().version
    anchor = f"OutPOSt Бухгалтерія v{version} доступна для Windows; Windows RC 406/406 пройдено. Інсталятор поки без цифрового підпису."
    require(anchor in text, "features Accounting anchor missing")
    mutated = text.replace(anchor, anchor.replace(f"v{version}", "v0.999.1"), 1)
    errors = validate_page_text(pathname, mutated)
    require(any("must match canonical manifest" in error for error in errors), "stale Accounting version must fail")


def test_package_regression_fails() -> None:
    pathname = "/features"
    text = source_text(pathname)
    marker = "Бухгалтерія входить до основного пакета OutPOSt без окремої ліцензії та встановлюється окремим Windows-інсталятором."
    require(marker in text, "features current Accounting package marker missing")
    mutated = text.replace(marker, "Після завершення Бухгалтерія увійде до основного пакета OutPOSt без окремої ліцензії.", 1)
    errors = validate_page_text(pathname, mutated)
    require(any("missing maturity/status marker" in error or "forbidden" in error for error in errors), "old package wording must fail")


def test_features_stale_eakcyz_wording_fails() -> None:
    pathname = "/features"
    text = source_text(pathname)
    marker = '<a href="/eakcyz">еАкциз/XTrace</a> має необов’язковий read-only Sandbox-контур'
    require(marker in text, "features eАкциз current-status marker missing")
    mutated = text.replace(
        marker,
        "еАкциз/XTrace лишається інтеграційним напрямком: сценарії Data Matrix і електронних марок готуються",
        1,
    )
    errors = validate_page_text(pathname, mutated)
    require(any("missing maturity/status marker" in error or "forbidden" in error for error in errors), "stale eАкциз features wording must fail")


def test_automation_stale_eakcyz_wording_fails() -> None:
    pathname = "/avtomatyzatsiya-magazynu"
    text = source_text(pathname)
    marker = "еАкциз/XTrace — необов’язковий read-only Sandbox-контур"
    require(marker in text, "automation eАкциз current-status marker missing")
    mutated = text.replace(
        marker,
        "еАкциз/XTrace — напрямок інтеграції, який ще не заявлений production-ready",
        1,
    )
    errors = validate_page_text(pathname, mutated)
    require(
        any("missing maturity/status marker" in error or "forbidden" in error for error in errors),
        "stale eАкциз automation wording must fail",
    )


def test_offline_stale_eakcyz_wording_fails() -> None:
    pathname = "/offline-programa-dlya-magazynu"
    text = source_text(pathname)
    marker = "еАкциз/XTrace — read-only Sandbox-запити"
    require(marker in text, "offline eАкциз current-status marker missing")
    mutated = text.replace(
        marker,
        "Майбутні державні API, зокрема еАкциз/XTrace.",
        1,
    )
    errors = validate_page_text(pathname, mutated)
    require(
        any("missing maturity/status marker" in error or "forbidden" in error for error in errors),
        "stale eАкциз offline wording must fail",
    )


def test_global_stale_eakcyz_wording_fails() -> None:
    errors = validate_global_html_text(
        "uncontracted-seo-page.html",
        "еАкциз/XTrace — напрямок інтеграції, який ще не заявлений production-ready",
    )
    require(
        any("forbidden global maturity/status claim" in error for error in errors),
        "global stale eАкциз wording must fail even on an uncontracted page",
    )
    changelog_errors = validate_global_html_text(
        "changelog.html",
        "еАкциз/XTrace — напрямок інтеграції, який ще не заявлений production-ready",
    )
    require(not changelog_errors, "historical changelog must remain excluded from global maturity sweep")


def test_prro_stale_acceptance_wording_fails() -> None:
    pathname = "/prro"
    text = source_text(pathname) + "\nфінальне TEST-приймання\n"
    errors = validate_page_text(pathname, text)
    require(
        any("forbidden maturity/status pattern" in error for error in errors),
        "stale Native PRRO TEST acceptance wording must fail",
    )


def test_features_blank_accounting_fact_fails() -> None:
    pathname = "/features"
    text = source_text(pathname)
    version = load_accounting_release().version
    marker = f'<span>Для завантаження</span><strong>Бухгалтерія v{version}</strong><small>Windows · x86 · .NET 4.8</small>'
    require(marker in text, "features Accounting build marker missing")
    mutated = text.replace(marker, '<span>Для завантаження</span><strong></strong><small>Windows · x86 · .NET 4.8</small>', 1)
    errors = validate_page_text(pathname, mutated)
    require(
        any("missing maturity/status marker" in error for error in errors),
        "blank Accounting build fact must fail",
    )


def test_prro_overclaim_fails() -> None:
    pathname = "/prro"
    text = source_text(pathname) + "\nNative ПРРО — production-ready\n"
    errors = validate_page_text(pathname, text)
    require(any("forbidden" in error for error in errors), "Native ПРРО production overclaim must fail")


def test_small_store_future_prro_wording_fails() -> None:
    pathname = "/programa-dlya-nevelykogo-magazynu"
    text = source_text(pathname) + "\nпісля завершення фінального приймання, Native ПРРО\n"
    errors = validate_page_text(pathname, text)
    require(any("forbidden" in error for error in errors), "future-gated Native PRRO wording must fail")


def test_accounting_future_package_wording_fails() -> None:
    pathname = "/buhgalteriya"
    text = source_text(pathname) + "\nПісля завершення клієнтського релізу Бухгалтерія планується\n"
    errors = validate_page_text(pathname, text)
    require(any("forbidden" in error for error in errors), "future-tense Accounting package wording must fail")


def test_homepage_future_accounting_package_wording_fails() -> None:
    pathname = "/"
    text = source_text(pathname) + "\nпісля клієнтського релізу — без окремої ліцензії\n"
    errors = validate_page_text(pathname, text)
    require(any("forbidden" in error for error in errors), "homepage future-tense Accounting package wording must fail")


def test_license_future_accounting_package_wording_fails() -> None:
    pathname = "/license"
    text = source_text(pathname) + "\nПісля публічного клієнтського релізу OutPOSt Бухгалтерія входить\n"
    errors = validate_page_text(pathname, text)
    require(any("forbidden" in error for error in errors), "license future-tense Accounting package wording must fail")


def test_runtime_future_accounting_package_wording_fails() -> None:
    text = "\n".join((
        "OutPOSt Бухгалтерія входить до пакета OutPOSt без окремої ліцензії на модуль",
        "OutPOSt Бухгалтерія</a> входить до основного пакета без окремої ліцензії",
        "після клієнтського релізу модуль входить до основного пакета OutPOSt",
    ))
    errors = validate_runtime_script_text(text)
    require(any("forbidden runtime" in error for error in errors), "runtime future-tense Accounting package wording must fail")


def main() -> int:
    tests = (
        test_real_sources_pass,
        test_required_disclaimer_fails_closed,
        test_features_version_regression_fails,
        test_package_regression_fails,
        test_features_stale_eakcyz_wording_fails,
        test_automation_stale_eakcyz_wording_fails,
        test_offline_stale_eakcyz_wording_fails,
        test_global_stale_eakcyz_wording_fails,
        test_prro_stale_acceptance_wording_fails,
        test_features_blank_accounting_fact_fails,
        test_prro_overclaim_fails,
        test_small_store_future_prro_wording_fails,
        test_accounting_future_package_wording_fails,
        test_homepage_future_accounting_package_wording_fails,
        test_license_future_accounting_package_wording_fails,
        test_runtime_future_accounting_package_wording_fails,
    )
    for test in tests:
        test()
    print("Product maturity guard synthetic tests: PASS")
    print(f"  {len(tests)}/{len(tests)} offline tests passed")
    print("  stale PRRO/eАкциз copy (including automation/offline/uncontracted public HTML), future-gated Native PRRO copy, future-tense Accounting package copy (including homepage/license/runtime), blank Accounting fact, disclaimer removal, incorrect Accounting version, package regression and PRRO overclaim fail closed")
    print("  production network was not called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
