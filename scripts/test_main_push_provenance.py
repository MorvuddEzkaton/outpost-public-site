#!/usr/bin/env python3
"""Synthetic regressions for verify_main_push_provenance.py."""

from __future__ import annotations

from pathlib import Path
import re

from verify_main_push_provenance import validate_provenance


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_two_parent_suffix_pr_merge_passes() -> None:
    errors = validate_provenance(
        "push",
        ["a" * 40, "b" * 40],
        "Publish validated staging UI/focus fixes (#209)",
    )
    require(not errors, f"two-parent suffix PR merge must pass: {errors}")


def test_two_parent_merge_pull_request_subject_passes() -> None:
    errors = validate_provenance(
        "push",
        ["a" * 40, "b" * 40],
        "Merge pull request #204 from MorvuddEzkaton/hotfix/v0244-download-icon-production",
    )
    require(not errors, f"GitHub merge-commit subject must pass: {errors}")


def test_single_parent_squash_pr_merge_passes() -> None:
    errors = validate_provenance(
        "push",
        ["a" * 40],
        "Release OutPOSt v0.24.4 (#201)",
    )
    require(not errors, f"single-parent squash PR merge must pass: {errors}")


def test_direct_single_parent_push_fails() -> None:
    errors = validate_provenance(
        "push",
        ["a" * 40],
        "Emergency direct edit",
    )
    require(
        any("GitHub PR marker" in error for error in errors),
        "single-parent automatic main push without a PR marker must fail",
    )


def test_three_parent_merge_fails_even_with_pr_marker() -> None:
    errors = validate_provenance(
        "push",
        ["a" * 40, "b" * 40, "c" * 40],
        "Unexpected octopus merge (#999)",
    )
    require(
        any("one parent" in error and "two parents" in error for error in errors),
        "three-parent automatic main update must fail the merge-shape guard",
    )


def test_two_parent_non_pr_merge_fails() -> None:
    errors = validate_provenance(
        "push",
        ["a" * 40, "b" * 40],
        "Merge staging manually",
    )
    require(
        any("GitHub PR marker" in error for error in errors),
        "two-parent merge without PR marker must fail",
    )


def test_manual_dispatch_bypasses_commit_shape() -> None:
    errors = validate_provenance(
        "workflow_dispatch",
        ["a" * 40],
        "Manual verification of current production",
    )
    require(not errors, f"manual live verification must not require PR merge shape: {errors}")


def test_empty_push_metadata_fails_closed() -> None:
    errors = validate_provenance("push", [], "")
    require(len(errors) == 2, f"empty automatic push metadata must fail both checks: {errors}")


def test_live_workflow_fetches_merge_parents() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/live-production-verify.yml").read_text(encoding="utf-8")
    require("- name: Checkout production source" in workflow, "production checkout step missing")
    checkout = workflow.split("- name: Checkout production source", 1)[1].split("- name: Set up Python", 1)[0]
    match = re.search(r"(?m)^\s*fetch-depth:\s*(\d+)\s*$", checkout)
    require(match is not None and int(match.group(1)) >= 2,
            "production checkout must fetch at least two generations to verify GitHub PR merge parents")


def main() -> int:
    tests = (
        test_two_parent_suffix_pr_merge_passes,
        test_two_parent_merge_pull_request_subject_passes,
        test_single_parent_squash_pr_merge_passes,
        test_direct_single_parent_push_fails,
        test_three_parent_merge_fails_even_with_pr_marker,
        test_two_parent_non_pr_merge_fails,
        test_manual_dispatch_bypasses_commit_shape,
        test_empty_push_metadata_fails_closed,
        test_live_workflow_fetches_merge_parents,
    )
    for test in tests:
        test()

    print("Main push provenance regression: PASS")
    print(f"  {len(tests)}/{len(tests)} synthetic tests passed")
    print("  real merge-commit/squash PR styles pass; unmarked or impossible automatic pushes fail closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
