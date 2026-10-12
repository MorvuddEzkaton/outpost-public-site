#!/usr/bin/env python3
"""Synthetic regressions for the online-demo dialog isolation contract."""

from __future__ import annotations

from verify_public_site import validate_demo_dialog_contract


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_valid_dialogs_pass() -> None:
    html = """
    <dialog id="cash-payment-dialog" class="demo-dialog payment-dialog"></dialog>
    <dialog class="extra demo-dialog" id="debt-dialog"></dialog>
    """
    require(not validate_demo_dialog_contract(html), "valid demo dialogs must pass")


def test_missing_demo_dialog_class_fails() -> None:
    html = '<dialog id="unsafe-dialog" class="other"></dialog>'
    errors = validate_demo_dialog_contract(html)
    require(
        any("must include class 'demo-dialog'" in error for error in errors),
        "dialog without demo-dialog class must fail",
    )


def test_missing_id_fails() -> None:
    html = '<dialog class="demo-dialog"></dialog>'
    errors = validate_demo_dialog_contract(html)
    require(any("must have a stable id" in error for error in errors), "dialog without id must fail")


def test_duplicate_id_fails() -> None:
    html = """
    <dialog id="duplicate-dialog" class="demo-dialog"></dialog>
    <dialog class="demo-dialog" id="duplicate-dialog"></dialog>
    """
    errors = validate_demo_dialog_contract(html)
    require(any("duplicate dialog id" in error for error in errors), "duplicate dialog ids must fail")


def test_data_attributes_cannot_spoof_id_or_class() -> None:
    html = '<dialog data-id="fake-id" data-class="demo-dialog"></dialog>'
    errors = validate_demo_dialog_contract(html)
    require(any("must have a stable id" in error for error in errors), "data-id must not satisfy the dialog id contract")
    require(
        any("must include class 'demo-dialog'" in error for error in errors),
        "data-class must not satisfy the dialog class contract",
    )


def test_no_dialogs_fails() -> None:
    errors = validate_demo_dialog_contract("<main>No dialogs here</main>")
    require(any("no dialog elements found" in error for error in errors), "missing dialog contract must fail")


def main() -> int:
    tests = (
        test_valid_dialogs_pass,
        test_missing_demo_dialog_class_fails,
        test_missing_id_fails,
        test_duplicate_id_fails,
        test_data_attributes_cannot_spoof_id_or_class,
        test_no_dialogs_fails,
    )
    for test in tests:
        test()

    print("Demo dialog contract regression: PASS")
    print(f"  {len(tests)}/{len(tests)} synthetic tests passed")
    print("  missing/spoofed class/id, duplicate ids and disappearing modal contract fail closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
