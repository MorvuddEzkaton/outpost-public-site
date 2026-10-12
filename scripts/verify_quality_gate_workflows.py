#!/usr/bin/env python3
"""Guard the canonical pre-merge quality workflows against duplicate Actions triggers.

These six required workflows are PR-only for automatic execution and cannot skip
release-, script-, installer- or docs-only PRs through path filters. They may
also be started manually with workflow_dispatch. Production verification is owned
by the separate live-production workflow, so automatic push triggers here would
only rerun the same pre-merge quality gates and consume extra GitHub-hosted minutes.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

LIVE_PRODUCTION_WORKFLOW = ".github/workflows/live-production-verify.yml"

QUALITY_WORKFLOWS = (
    ".github/workflows/public-repository-security.yml",
    ".github/workflows/browser-guards.yml",
    ".github/workflows/first-party-resource-guard.yml",
    ".github/workflows/public-asset-budget.yml",
    ".github/workflows/public-site-smoke.yml",
    ".github/workflows/sitemap-freshness-guard.yml",
)

MANUAL_BROWSER_WORKFLOWS = (
    ".github/workflows/browser-a11y-guard.yml",
    ".github/workflows/browser-keyboard-guard.yml",
    ".github/workflows/browser-runtime-guard.yml",
    ".github/workflows/browser-ui-guard.yml",
)

COMBINED_BROWSER_WORKFLOW = ".github/workflows/browser-guards.yml"

LIVE_REQUIRED_RUN_COMMANDS = (
    "python scripts/verify_live_host_normalization.py",
    "python scripts/verify_live_cloudflare_privacy.py",
)

LIVE_REQUIRED_TRIGGER_PATHS = (
    "site/**",
    "wrangler.jsonc",
    "scripts/verify_release_metadata.py",
    "scripts/verify_main_push_provenance.py",
    "scripts/verify_site_identity.py",
    "scripts/verify_phone_ctas.py",
    "scripts/verify_security_headers.py",
    "scripts/verify_public_site.py",
    "scripts/verify_public_license_terms.py",
    "scripts/verify_public_product_maturity.py",
    "scripts/verify_live_host_normalization.py",
    "scripts/verify_live_cloudflare_privacy.py",
    "scripts/accounting_release_meta.py",
    "release/accounting-release.json",
)

PULL_REQUEST_MAIN_RE = re.compile(
    r"(?m)^  pull_request:\s*$"
    r"(?:(?:\n    [^\n]*)*)"
    r"\n    branches:\s*$"
    r"(?:(?:\n      [^\n]*)*)"
    r"\n      - main\s*$"
)

DIRECT_PYTHON_RUN_RE = re.compile(
    r"(?m)^\s+(?:-\s+)?run:\s+python\s+(scripts/[^\s]+\.py)(?:\s+.*)?$"
)

PUSH_MAIN_RE = re.compile(
    r"(?m)^  push:\s*$"
    r"(?:(?:\n    [^\n]*)*)"
    r"\n    branches:\s*$"
    r"(?:(?:\n      [^\n]*)*)"
    r"\n      - main\s*$"
)


def validate_workflow(relative: str, text: str) -> list[str]:
    errors: list[str] = []

    if not re.search(r"(?m)^  workflow_dispatch:\s*$", text):
        errors.append(f"{relative}: workflow_dispatch trigger is missing")

    if not PULL_REQUEST_MAIN_RE.search(text):
        errors.append(f"{relative}: pull_request must target main")

    if re.search(r"(?m)^  push:\s*$", text):
        errors.append(
            f"{relative}: automatic push trigger is forbidden for canonical quality gates; "
            "use PR checks or workflow_dispatch"
        )

    if not re.search(r"(?m)^concurrency:\s*$", text):
        errors.append(f"{relative}: concurrency block is missing")

    if not re.search(r"(?m)^  cancel-in-progress:\s*true\s*$", text):
        errors.append(f"{relative}: concurrency.cancel-in-progress must be true")

    if not re.search(
        r"(?ms)^permissions:\s*\n(?:  [^\n]+\n)*?  contents:\s*read\s*$",
        text,
    ):
        errors.append(f"{relative}: permissions.contents must be read")

    pr_event = re.search(
        r"(?m)^  pull_request:[^\S\n]*\n((?:(?:    [^\n]*|[ \t]*)\n)*)", text
    )
    pr_text = pr_event.group(1) if pr_event else ""
    if re.search(r"(?m)^    (?:paths-ignore|branches-ignore|types):", pr_text):
        errors.append(f"{relative}: required PR checks must not have ignore/activity filters")
    path_filter = re.search(
        r"(?m)^    paths:[^\S\n]*\n((?:(?:      [^\n]*|[ \t]*)\n)*)", pr_text
    )
    if re.search(r"(?m)^    paths:", pr_text) and not path_filter:
        errors.append(f"{relative}: required PR path filter must be an auditable all-path list")
    if path_filter:
        entries = re.findall(r"(?m)^      - [\"']([^\"']+)[\"'][ \t]*(?:#.*)?$", path_filter.group(1))
        if "**" not in entries:
            errors.append(f"{relative}: required pull_request.paths must include all paths ('**')")
        if any(entry.startswith("!") for entry in entries):
            errors.append(f"{relative}: required PR checks must not exclude changed paths")

    return errors


def validate_manual_browser_workflow(relative: str, text: str) -> list[str]:
    """Keep original single-suite workflows for manual diagnostics only."""
    errors: list[str] = []
    if not re.search(r"(?m)^  workflow_dispatch:\s*$", text):
        errors.append(f"{relative}: manual browser workflow must retain workflow_dispatch")
    if re.search(r"(?m)^  (?:push|pull_request|schedule|pull_request_target):\s*$", text):
        errors.append(f"{relative}: manual browser workflow must not have automatic triggers")
    if not re.search(r"(?ms)^permissions:\s*\n(?:  [^\n]+\n)*?  contents:\s*read\s*$", text):
        errors.append(f"{relative}: permissions.contents must be read")
    if not re.search(r"(?m)^  cancel-in-progress:\s*true\s*$", text):
        errors.append(f"{relative}: concurrency cancellation is required")
    return errors


def validate_combined_browser_workflow(relative: str, text: str) -> list[str]:
    """Ensure consolidation cannot silently drop browser coverage or mask failures."""
    errors: list[str] = []
    required_suites = {
        "a11y": "scripts/browser_a11y.spec.mjs",
        "keyboard": "scripts/browser_keyboard.spec.mjs",
        "runtime": "scripts/browser_runtime.spec.mjs",
        "ui": "scripts/browser_ui.spec.mjs",
    }
    for suite_id, script in required_suites.items():
        if f'npx playwright test {script} ' not in text:
            errors.append(f"{relative}: missing browser suite {suite_id} ({script})")
        if not re.search(
            rf"(?ms)^      - name: [^\n]+\n        id: {suite_id}\n"
            r"        continue-on-error: true\n"
            rf"        run: npx playwright test {re.escape(script)}\s",
            text,
        ):
            errors.append(f"{relative}: {suite_id} must preserve an independent continued test step")
        if f"steps.{suite_id}.outcome" not in text:
            errors.append(f"{relative}: missing fail-closed outcome check for {suite_id}")
    if text.count("npx playwright install --with-deps chromium") != 1:
        errors.append(f"{relative}: Chromium must be installed exactly once")
    if text.count("npm install --no-save --no-package-lock") != 1:
        errors.append(f"{relative}: browser dependencies must be installed exactly once")
    if 'run: python scripts/verify_navigation_style_contract.py' not in text:
        errors.append(f"{relative}: missing navigation stylesheet contract guard")
    if not re.search(
        r"(?ms)^      - name: Fail if any browser guard did not pass\n        if: always\(\)\n",
        text,
    ):
        errors.append(f"{relative}: final always-run aggregate failure step is required")
    for suite_id in ("keyboard", "runtime", "ui"):
        if f"always() && steps.{suite_id}.outcome == 'failure'" not in text:
            errors.append(f"{relative}: missing conditional {suite_id} screenshot upload")
    return errors


def validate_live_production_workflow(relative: str, text: str) -> list[str]:
    errors: list[str] = []

    if not re.search(r"(?m)^  workflow_dispatch:\s*$", text):
        errors.append(f"{relative}: workflow_dispatch trigger is missing")

    if not PUSH_MAIN_RE.search(text):
        errors.append(f"{relative}: live production verification must run on push to main")

    if re.search(r"(?m)^  pull_request:\s*$", text):
        errors.append(
            f"{relative}: pull_request trigger is forbidden; live production verification is post-merge only"
        )

    if not re.search(r"(?ms)^  push:\s*\n.*?^    paths:\s*$", text):
        errors.append(f"{relative}: push.paths filter is missing")

    if not re.search(r"(?m)^concurrency:\s*$", text):
        errors.append(f"{relative}: concurrency block is missing")

    if not re.search(r"(?m)^  cancel-in-progress:\s*true\s*$", text):
        errors.append(f"{relative}: concurrency.cancel-in-progress must be true")

    if not re.search(
        r"(?ms)^permissions:\s*\n(?:  [^\n]+\n)*?  contents:\s*read\s*$",
        text,
    ):
        errors.append(f"{relative}: permissions.contents must be read")

    for required_path in LIVE_REQUIRED_TRIGGER_PATHS:
        quoted = f'      - "{required_path}"'
        if quoted not in text:
            errors.append(
                f"{relative}: live-production trigger paths must include {required_path!r} "
                "because the workflow executes or imports that source"
            )

    direct_python_scripts = sorted(set(DIRECT_PYTHON_RUN_RE.findall(text)))
    for script_path in direct_python_scripts:
        quoted = f'      - "{script_path}"'
        if quoted not in text:
            errors.append(
                f"{relative}: directly executed Python verifier {script_path!r} "
                "must also be present in push.paths"
            )

    for command in LIVE_REQUIRED_RUN_COMMANDS:
        if f"        run: {command}" not in text:
            errors.append(
                f"{relative}: live-production workflow must execute {command!r}"
            )

    provenance_step = re.compile(
        r"(?ms)^      - name: Guard main push provenance\s*$"
        r"\n        if: always\(\)\s*$"
        r"\n        run: python scripts/verify_main_push_provenance\.py\s*$"
    )
    if not provenance_step.search(text):
        errors.append(
            f"{relative}: live-production workflow must finish with the always-run main push provenance guard"
        )

    return errors


def main() -> int:
    errors: list[str] = []

    for relative in QUALITY_WORKFLOWS:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"{relative}: workflow file is missing")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{relative}: cannot read workflow: {exc}")
            continue
        errors.extend(validate_workflow(relative, text))

    for relative in MANUAL_BROWSER_WORKFLOWS:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"{relative}: manual browser diagnostic workflow is missing")
            continue
        errors.extend(validate_manual_browser_workflow(relative, path.read_text(encoding="utf-8")))

    browser_path = ROOT / COMBINED_BROWSER_WORKFLOW
    if browser_path.is_file():
        errors.extend(validate_combined_browser_workflow(
            COMBINED_BROWSER_WORKFLOW, browser_path.read_text(encoding="utf-8")
        ))

    live_path = ROOT / LIVE_PRODUCTION_WORKFLOW
    if not live_path.is_file():
        errors.append(f"{LIVE_PRODUCTION_WORKFLOW}: workflow file is missing")
    else:
        try:
            live_text = live_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{LIVE_PRODUCTION_WORKFLOW}: cannot read workflow: {exc}")
        else:
            errors.extend(validate_live_production_workflow(LIVE_PRODUCTION_WORKFLOW, live_text))

    if errors:
        print(f"Quality gate workflow guard: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Quality gate workflow guard: PASS")
    print(f"  canonical workflows checked: {len(QUALITY_WORKFLOWS)}")
    print("  four original browser suites share one Chromium installation")
    print("  four legacy browser workflows are manual diagnostic only")
    print("  pre-merge automatic execution: pull_request -> main only")
    print("  pre-merge duplicate automatic push triggers: none")
    print("  all six required checks run on every main PR, including docs/release/installer-only changes")
    print("  required path/activity exclusions forbidden; manual runs are diagnostic, not PR acceptance")
    print("  post-merge automatic execution: live-production push -> main only")
    print("  live-production trigger paths cover verifier/helper/manifest dependencies")
    print("  every directly executed Python verifier is also present in push.paths")
    print("  mandatory host-normalization and Cloudflare privacy run commands are present")
    print("  manual execution: workflow_dispatch")
    print("  concurrency cancellation: enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
