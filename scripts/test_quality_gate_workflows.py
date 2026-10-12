#!/usr/bin/env python3
"""Synthetic regressions for verify_quality_gate_workflows.py."""

from __future__ import annotations

from verify_quality_gate_workflows import (
    ROOT,
    COMBINED_BROWSER_WORKFLOW,
    validate_combined_browser_workflow,
    validate_manual_browser_workflow,
    validate_live_production_workflow,
    validate_workflow,
)


VALID = """name: Fixture

on:
  workflow_dispatch:
  pull_request:
    branches:
      - main
    paths:
      - "**"
      - "site/**"

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  fixture:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""


VALID_LIVE = """name: Live production fixture

on:
  push:
    branches:
      - main
    paths:
      - "site/**"
      - "wrangler.jsonc"
      - "scripts/verify_release_metadata.py"
      - "scripts/verify_main_push_provenance.py"
      - "scripts/verify_site_identity.py"
      - "scripts/verify_phone_ctas.py"
      - "scripts/verify_security_headers.py"
      - "scripts/verify_public_site.py"
      - "scripts/verify_public_license_terms.py"
      - "scripts/verify_public_product_maturity.py"
      - "scripts/verify_live_host_normalization.py"
      - "scripts/verify_live_cloudflare_privacy.py"
      - "scripts/accounting_release_meta.py"
      - "release/accounting-release.json"
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: live-production
  cancel-in-progress: true

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - run: echo live
      - name: Verify host normalization
        run: python scripts/verify_live_host_normalization.py
      - name: Verify Cloudflare privacy
        run: python scripts/verify_live_cloudflare_privacy.py
      - name: Guard main push provenance
        if: always()
        run: python scripts/verify_main_push_provenance.py
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def errors(text: str) -> list[str]:
    return validate_workflow(".github/workflows/fixture.yml", text)


def live_errors(text: str) -> list[str]:
    return validate_live_production_workflow(".github/workflows/live-production-fixture.yml", text)


def test_valid_fixture_passes() -> None:
    require(not errors(VALID), f"valid fixture failed: {errors(VALID)}")


def test_push_trigger_fails() -> None:
    mutated = VALID.replace(
        "  pull_request:\n",
        "  push:\n    branches:\n      - main\n  pull_request:\n",
        1,
    )
    require(any("push trigger is forbidden" in item for item in errors(mutated)), "push trigger must fail")


def test_missing_dispatch_fails() -> None:
    mutated = VALID.replace("  workflow_dispatch:\n", "", 1)
    require(any("workflow_dispatch trigger is missing" in item for item in errors(mutated)), "missing dispatch must fail")


def test_wrong_pr_base_fails() -> None:
    mutated = VALID.replace("      - main\n", "      - staging\n", 1)
    require(any("pull_request must target main" in item for item in errors(mutated)), "wrong PR base must fail")


def test_unfiltered_required_pr_passes() -> None:
    mutated = VALID.replace('    paths:\n      - "**"\n      - "site/**"\n', "", 1)
    require(not errors(mutated), "unfiltered required PR trigger must cover every changed path")


def test_filtered_required_pr_fails() -> None:
    mutated = VALID.replace('      - "**"\n', "", 1)
    require(any("must include all paths" in item for item in errors(mutated)), "docs/release-only PRs must not be skipped")


def test_required_ignore_activity_filters_fail() -> None:
    for field in ("paths-ignore", "branches-ignore", "types"):
        mutated = VALID.replace('    paths:\n', f'    {field}:\n      - closed\n    paths:\n', 1)
        require(any("ignore/activity filters" in item for item in errors(mutated)), f"{field} could leave a required check pending")


def test_commented_catchall_fails() -> None:
    mutated = VALID.replace('      - "**"\n', '      # - "**"\n', 1)
    require(any("must include all paths" in item for item in errors(mutated)), "a comment is not an all-path trigger")


def test_single_quoted_catchall_passes() -> None:
    mutated = VALID.replace('      - "**"\n', "      - '**'\n", 1)
    require(not errors(mutated), "single-quoted all-path filter should pass")


def test_inline_paths_filter_fails() -> None:
    mutated = VALID.replace('    paths:\n      - "**"\n      - "site/**"\n', '    paths: ["site/**"]\n', 1)
    require(any("auditable all-path list" in item for item in errors(mutated)), "inline filtered paths cannot bypass required coverage")


def test_missing_concurrency_fails() -> None:
    mutated = VALID.replace(
        "concurrency:\n  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}\n  cancel-in-progress: true\n\n",
        "",
        1,
    )
    require(any("concurrency block is missing" in item for item in errors(mutated)), "missing concurrency must fail")


def test_cancel_false_fails() -> None:
    mutated = VALID.replace("  cancel-in-progress: true\n", "  cancel-in-progress: false\n", 1)
    require(any("cancel-in-progress must be true" in item for item in errors(mutated)), "cancel=false must fail")


def test_write_permission_fails() -> None:
    mutated = VALID.replace("  contents: read\n", "  contents: write\n", 1)
    require(any("permissions.contents must be read" in item for item in errors(mutated)), "contents: write must fail")


def test_public_smoke_direct_python_is_covered_by_all_paths() -> None:
    relative = ".github/workflows/public-site-smoke.yml"
    mutated = VALID.replace(
        '      - run: echo ok\n',
        '      - run: echo ok\n      - run: python scripts/smoke_fixture.py\n',
        1,
    )
    result = validate_workflow(relative, mutated)
    require(not result, "all-path required trigger covers new Python scripts without enumerating each")


def test_public_smoke_direct_node_is_covered_by_all_paths() -> None:
    relative = ".github/workflows/public-site-smoke.yml"
    mutated = VALID.replace(
        '      - run: echo ok\n',
        '      - run: echo ok\n      - run: node scripts/smoke_fixture.mjs\n',
        1,
    )
    result = validate_workflow(relative, mutated)
    require(not result, "all-path required trigger covers new Node scripts without enumerating each")


def test_public_smoke_direct_scripts_with_paths_pass() -> None:
    relative = ".github/workflows/public-site-smoke.yml"
    mutated = VALID.replace(
        '      - "site/**"\n',
        '      - "site/**"\n'
        '      - "scripts/smoke_fixture.py"\n'
        '      - "scripts/smoke_fixture.mjs"\n',
        1,
    ).replace(
        '      - run: echo ok\n',
        '      - run: echo ok\n'
        '      - run: python scripts/smoke_fixture.py\n'
        '      - run: node scripts/smoke_fixture.mjs\n',
        1,
    )
    result = validate_workflow(relative, mutated)
    require(
        not any("smoke_fixture" in item for item in result),
        f"public-site smoke scripts with path filters should pass coverage: {result}",
    )


def test_frontend_downloads_exclusion_is_forbidden() -> None:
    relative = COMBINED_BROWSER_WORKFLOW
    require(not validate_workflow(relative, VALID), "catchall required front-end trigger should pass")
    excluded = VALID.replace(
        '      - "site/**"\n',
        '      - "site/**"\n      - "!site/downloads/**"\n',
        1,
    )
    require(
        any("must not exclude changed paths" in item for item in validate_workflow(relative, excluded)),
        "binary-only PRs must not skip required front-end checks",
    )


def test_frontend_negative_paths_fail_in_either_order() -> None:
    relative = COMBINED_BROWSER_WORKFLOW
    wrong_order = VALID.replace(
        '      - "site/**"\n',
        '      - "!site/downloads/**"\n      - "site/**"\n',
        1,
    )
    errors = validate_workflow(relative, wrong_order)
    require(
        any("must not exclude changed paths" in item for item in errors),
        "a negative path must fail even before a later include",
    )


def test_valid_live_fixture_passes() -> None:
    require(not live_errors(VALID_LIVE), f"valid live fixture failed: {live_errors(VALID_LIVE)}")


def test_live_missing_push_fails() -> None:
    mutated = VALID_LIVE.replace(
        '  push:\n    branches:\n      - main\n    paths:\n      - "site/**"\n',
        "",
        1,
    )
    require(
        any("must run on push to main" in item for item in live_errors(mutated)),
        "live workflow without push:main must fail",
    )


def test_live_wrong_push_branch_fails() -> None:
    mutated = VALID_LIVE.replace("      - main\n", "      - staging\n", 1)
    require(
        any("must run on push to main" in item for item in live_errors(mutated)),
        "live workflow wrong push branch must fail",
    )


def test_live_missing_helper_trigger_path_fails() -> None:
    mutated = VALID_LIVE.replace('      - "scripts/verify_public_site.py"\n', "", 1)
    require(
        any("live-production trigger paths must include" in item and "verify_public_site.py" in item for item in live_errors(mutated)),
        "live workflow missing imported helper path must fail",
    )


def test_live_direct_python_run_requires_trigger_path() -> None:
    mutated = VALID_LIVE.replace(
        '      - run: echo live\n',
        '      - run: echo live\n      - run: python scripts/fixture_extra_live_check.py\n',
        1,
    )
    require(
        any(
            "directly executed Python verifier" in item
            and "fixture_extra_live_check.py" in item
            for item in live_errors(mutated)
        ),
        "directly executed live Python verifier without push.paths entry must fail",
    )


def test_live_direct_python_run_with_trigger_path_passes() -> None:
    mutated = VALID_LIVE.replace(
        '      - "release/accounting-release.json"\n',
        '      - "release/accounting-release.json"\n'
        '      - "scripts/fixture_extra_live_check.py"\n',
        1,
    ).replace(
        '      - run: echo live\n',
        '      - run: echo live\n      - run: python scripts/fixture_extra_live_check.py\n',
        1,
    )
    require(
        not any(
            "fixture_extra_live_check.py" in item
            for item in live_errors(mutated)
        ),
        f"directly executed live verifier with trigger path should pass path coverage: {live_errors(mutated)}",
    )


def test_live_missing_host_normalization_trigger_path_fails() -> None:
    mutated = VALID_LIVE.replace(
        '      - "scripts/verify_live_host_normalization.py"\n',
        "",
        1,
    )
    require(
        any(
            "live-production trigger paths must include" in item
            and "verify_live_host_normalization.py" in item
            for item in live_errors(mutated)
        ),
        "live workflow missing host-normalization trigger path must fail",
    )


def test_live_missing_cloudflare_privacy_trigger_path_fails() -> None:
    mutated = VALID_LIVE.replace(
        '      - "scripts/verify_live_cloudflare_privacy.py"\n',
        "",
        1,
    )
    require(
        any(
            "live-production trigger paths must include" in item
            and "verify_live_cloudflare_privacy.py" in item
            for item in live_errors(mutated)
        ),
        "live workflow missing Cloudflare privacy trigger path must fail",
    )


def test_live_missing_host_normalization_run_fails() -> None:
    mutated = VALID_LIVE.replace(
        '        run: python scripts/verify_live_host_normalization.py\n',
        "",
        1,
    )
    require(
        any(
            "must execute" in item and "verify_live_host_normalization.py" in item
            for item in live_errors(mutated)
        ),
        "live workflow missing host-normalization run command must fail",
    )


def test_live_missing_cloudflare_privacy_run_fails() -> None:
    mutated = VALID_LIVE.replace(
        '        run: python scripts/verify_live_cloudflare_privacy.py\n',
        "",
        1,
    )
    require(
        any(
            "must execute" in item and "verify_live_cloudflare_privacy.py" in item
            for item in live_errors(mutated)
        ),
        "live workflow missing Cloudflare privacy run command must fail",
    )


def test_live_missing_provenance_step_fails() -> None:
    mutated = VALID_LIVE.replace(
        '      - name: Guard main push provenance\n        if: always()\n        run: python scripts/verify_main_push_provenance.py\n',
        "",
        1,
    )
    require(
        any("must finish with the always-run main push provenance guard" in item for item in live_errors(mutated)),
        "live workflow missing final provenance sentinel must fail",
    )


def test_live_pull_request_trigger_fails() -> None:
    mutated = VALID_LIVE.replace(
        "  workflow_dispatch:\n",
        "  pull_request:\n    branches:\n      - main\n  workflow_dispatch:\n",
        1,
    )
    require(
        any("pull_request trigger is forbidden" in item for item in live_errors(mutated)),
        "live workflow pull_request trigger must fail",
    )


def manual_browser_fixture() -> str:
    return VALID.replace(
        '  pull_request:\n    branches:\n      - main\n    paths:\n      - "**"\n      - "site/**"\n\n',
        "",
        1,
    )


def test_manual_browser_diagnostic_passes() -> None:
    fixture = manual_browser_fixture()
    require(
        not validate_manual_browser_workflow("legacy.yml", fixture),
        "valid manual-only browser diagnostic must pass",
    )


def test_manual_browser_accidental_pr_trigger_fails() -> None:
    fixture = manual_browser_fixture().replace(
        "  workflow_dispatch:\n",
        "  workflow_dispatch:\n  pull_request:\n    branches:\n      - main\n",
        1,
    )
    result = validate_manual_browser_workflow("legacy.yml", fixture)
    require(
        any("must not have automatic triggers" in item for item in result),
        "manual diagnostics re-enabled on PR must fail closed",
    )


def current_combined_browser_workflow() -> str:
    return (ROOT / COMBINED_BROWSER_WORKFLOW).read_text(encoding="utf-8")


def test_combined_browser_gate_passes() -> None:
    source = current_combined_browser_workflow()
    require(
        not validate_workflow(COMBINED_BROWSER_WORKFLOW, source),
        "combined workflow must preserve canonical PR checks",
    )
    require(
        not validate_combined_browser_workflow(COMBINED_BROWSER_WORKFLOW, source),
        "combined browser gate must retain every suite and fail-closed reporting",
    )


def test_combined_browser_missing_suite_fails() -> None:
    source = current_combined_browser_workflow().replace(
        "npx playwright test scripts/browser_keyboard.spec.mjs",
        "echo skipped scripts/browser_keyboard.spec.mjs",
        1,
    )
    errors = validate_combined_browser_workflow(COMBINED_BROWSER_WORKFLOW, source)
    require(any("missing browser suite keyboard" in e for e in errors), "missing suite must fail")


def test_combined_browser_missing_aggregate_fails() -> None:
    source = current_combined_browser_workflow().replace(
        "      - name: Fail if any browser guard did not pass\n",
        "      - name: Inert step\n",
        1,
    )
    errors = validate_combined_browser_workflow(COMBINED_BROWSER_WORKFLOW, source)
    require(
        any("final always-run aggregate" in e for e in errors),
        "removing final failure aggregator must fail",
    )


def test_combined_browser_missing_screenshot_fails() -> None:
    source = current_combined_browser_workflow().replace(
        "always() && steps.runtime.outcome == 'failure'",
        "always()",
        1,
    )
    errors = validate_combined_browser_workflow(COMBINED_BROWSER_WORKFLOW, source)
    require(
        any("missing conditional runtime screenshot upload" in e for e in errors),
        "lost runtime diagnostic screenshots must fail",
    )


def main() -> int:
    tests = (
        test_valid_fixture_passes,
        test_push_trigger_fails,
        test_missing_dispatch_fails,
        test_wrong_pr_base_fails,
        test_unfiltered_required_pr_passes,
        test_filtered_required_pr_fails,
        test_required_ignore_activity_filters_fail,
        test_commented_catchall_fails,
        test_single_quoted_catchall_passes,
        test_inline_paths_filter_fails,
        test_missing_concurrency_fails,
        test_cancel_false_fails,
        test_write_permission_fails,
        test_public_smoke_direct_python_is_covered_by_all_paths,
        test_public_smoke_direct_node_is_covered_by_all_paths,
        test_public_smoke_direct_scripts_with_paths_pass,
        test_frontend_downloads_exclusion_is_forbidden,
        test_frontend_negative_paths_fail_in_either_order,
        test_valid_live_fixture_passes,
        test_live_missing_push_fails,
        test_live_wrong_push_branch_fails,
        test_live_missing_helper_trigger_path_fails,
        test_live_direct_python_run_requires_trigger_path,
        test_live_direct_python_run_with_trigger_path_passes,
        test_live_missing_host_normalization_trigger_path_fails,
        test_live_missing_cloudflare_privacy_trigger_path_fails,
        test_live_missing_host_normalization_run_fails,
        test_live_missing_cloudflare_privacy_run_fails,
        test_live_missing_provenance_step_fails,
        test_live_pull_request_trigger_fails,
        test_manual_browser_diagnostic_passes,
        test_manual_browser_accidental_pr_trigger_fails,
        test_combined_browser_gate_passes,
        test_combined_browser_missing_suite_fails,
        test_combined_browser_missing_aggregate_fails,
        test_combined_browser_missing_screenshot_fails,
    )
    for test in tests:
        test()

    print("Quality gate workflow guard regression: PASS")
    print(f"  {len(tests)}/{len(tests)} synthetic tests passed")
    print("  pre-merge push/base/dispatch/paths/concurrency/cancel/permission and smoke-script path regressions fail closed")
    print("  all required PR checks reject restrictive path/ignore/activity filters; docs/release/installer-only PRs stay covered")
    print("  live-production missing/wrong push, direct verifier trigger coverage, host/privacy run commands, provenance step and accidental PR triggers fail closed")
    print("  combined browser completeness/failure reporting and manual-only diagnostics are regression guarded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
