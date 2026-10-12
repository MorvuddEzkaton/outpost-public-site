#!/usr/bin/env python3
"""Fail-closed static guard for the manual Accounting pre-release PR workflow."""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "prepare-accounting-release.yml"


def fail(message: str) -> None:
    print("Prepare Accounting release workflow guard: FAIL", file=sys.stderr)
    print(f"  - {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if not WORKFLOW.is_file():
        fail("prepare-accounting-release.yml is missing")
    text = WORKFLOW.read_text(encoding="utf-8")

    allowed_top_level = {"name", "on", "permissions", "concurrency", "jobs"}
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):(?:\s|$)", line)
        if not match or match.group(1) not in allowed_top_level:
            fail(f"unexpected column-zero content at line {lineno}: {line}")

    live_compile = "python -m py_compile scripts/verify_live_production.py scripts/verify_live_public_ctas.py scripts/verify_live_phone_ctas.py scripts/verify_live_indexability.py scripts/verify_live_404.py scripts/verify_live_public_links.py scripts/verify_live_sitemap.py scripts/test_live_sitemap.py scripts/verify_live_robots.py scripts/verify_live_support_discovery.py scripts/verify_live_cabinet_entry.py scripts/verify_live_security_headers.py scripts/verify_live_static_assets.py scripts/test_live_static_assets.py scripts/test_social_image_dimensions.py scripts/verify_live_url_normalization.py scripts/verify_live_host_normalization.py scripts/test_live_host_normalization.py scripts/verify_live_cloudflare_privacy.py scripts/test_live_cloudflare_privacy.py scripts/verify_live_social_metadata.py scripts/verify_live_structured_metadata.py scripts/verify_live_product_maturity.py scripts/verify_live_accounting_release.py"

    required = {
        "main-only manual activation": "vars.OUTPOST_RELEASE_PREPARATION_ENABLED == '1'",
        "trusted main job": "github.ref == 'refs/heads/main'",
        "owner-only preparation": "github.actor == 'MorvuddEzkaton'",
        "read-only default token": "permissions:\n  contents: read",
        "main revision check": 'test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"',
        "validated input switch": 'git switch --detach "${STAGING_SHA}"',
        "hash-bound Windows receipt": 'TARGET_EVIDENCE="release/evidence/accounting-v${VERSION}.json"',
        "immutable artifact inventory": "python scripts/release_integrity.py --base-ref origin/main",
        "negative integrity tests": "python scripts/test_release_integrity.py",
        "generated checksum diff visibility": 'git add --intent-to-add -- "${TARGET_SHA}"',
        "manual-only trigger": "workflow_dispatch:",
        "version input": "version:",
        "RC input": "rc_acceptance:",
        "Authenticode input": "authenticode:",
        "branch write permission": "contents: write",
        "pull request write permission": "pull-requests: write",
        "prepared staging checkout": "ref: main",
        "full history": "fetch-depth: 0",
        "main/staging refresh": "git fetch origin main staging --prune",
        "staging ancestry": 'git merge-base --is-ancestor "${MAIN_SHA}" "${STAGING_SHA}"',
        "Accounting target EXE": 'TARGET_EXE="site/downloads/OutPOSt-Accounting-Setup-v${VERSION}.exe"',
        "exact-one staging input": 'if [ "${changed}" -ne 3 ]',
        "dry-run updater": 'python scripts/prepare_accounting_release.py "${VERSION}"',
        "immutable rollback SHA": 'BACKUP_SHA="${MAIN_SHA}"',
        "isolated branch": 'RELEASE_BRANCH="codex/accounting-release/v${VERSION}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"',
        "apply updater": "--apply",
        "manifest allowlist": "release/accounting-release.json",
        "Accounting page allowlist": "site/buhgalteriya.html",
        "download page allowlist": "site/download.html",
        "sitemap allowlist": "site/sitemap.xml",
        "stable OutPOSt EXE protection": "Stable OutPOSt installer changed during Accounting preparation.",
        "stable OutPOSt checksum protection": "Stable OutPOSt checksum changed during Accounting preparation.",
        "stable changelog protection": "site/changelog.html",
        "Worker protection": "site/_worker.js",
        "Cloudflare config protection": "wrangler.jsonc",
        "automation landing intent guard": "python scripts/verify_automation_landing_intents.py",
        "public SEO uniqueness guard": "python scripts/verify_public_seo_uniqueness.py",
        "public contextual link guard": "python scripts/verify_public_contextual_links.py",
        "demo contract regression": "python scripts/test_demo_dialog_contract.py",
        "FAQ schema regression": "python scripts/test_public_faq_schema.py",
        "quality workflow guard": "python scripts/verify_quality_gate_workflows.py",
        "quality workflow regression": "python scripts/test_quality_gate_workflows.py",
        "main provenance regression": "python scripts/test_main_push_provenance.py",
        "Accounting workflow self guard": "python scripts/verify_prepare_accounting_release_workflow.py",
        "release gate parity guard": "python scripts/verify_release_gate_parity.py",
        "release gate parity regression": "python scripts/test_release_gate_parity.py",
        "release changelog count regression": "python scripts/test_release_changelog_counts.py",
        "Accounting source guard": "python scripts/verify_accounting_release.py",
        "Accounting current tool check": "python scripts/prepare_accounting_release.py --check-current",
        "Accounting synthetic regression": "python scripts/test_prepare_accounting_release.py",
        "stable release metadata guard": "python scripts/verify_release_metadata.py",
        "stable release tool check": "python scripts/prepare_public_release.py --check-current",
        "product maturity source guard": "python scripts/verify_public_product_maturity.py",
        "product maturity regression": "python scripts/test_product_maturity_guard.py",
        "sitemap freshness regression": "python scripts/test_sitemap_freshness.py",
        "sitemap freshness guard": "python scripts/verify_sitemap_freshness.py",
        "host normalization offline regression": "python scripts/test_live_host_normalization.py",
        "Cloudflare privacy offline regression": "python scripts/test_live_cloudflare_privacy.py",
        "live sitemap parity offline regression": "python scripts/test_live_sitemap.py",
        "live static asset offline regression": "python scripts/test_live_static_assets.py",
        "CMS preview privacy regression": "node scripts/test_cms_preview_privacy.mjs",
        "static preview privacy regression": "node scripts/test_static_preview_privacy.mjs",
        "live verifier compilation": live_compile,
        "diff whitespace gate": "git diff --check",
        "release branch push": 'git push origin "HEAD:refs/heads/${RELEASE_BRANCH}"',
        "PR creation": "gh pr create",
        "PR target main": "--base main",
        "no auto merge statement": "does **not** merge the PR",
    }
    for label, marker in required.items():
        if marker not in text:
            fail(f"{label}: protected marker is missing: {marker}")

    if re.search(r"(?m)^\s{2}(push|pull_request|schedule):\s*$", text):
        fail("Accounting release workflow must remain workflow_dispatch-only")

    forbidden = {
        "automatic merge": "gh pr merge",
        "Cloudflare deployment": "wrangler deploy",
        "hard reset": "git reset --hard",
        "force push": "--force",
        "direct stable installer target": 'TARGET_EXE="site/downloads/OutPOSt-Setup-',
    }
    for label, marker in forbidden.items():
        if marker in text:
            fail(f"{label} is forbidden in Accounting release workflow")

    if 'git push origin "${MAIN_SHA}:refs/heads/${BACKUP_BRANCH}"' in text:
        fail("per-release backup branch creation is forbidden; retain the immutable main SHA")
    if '"${status}" = "D"' in text:
        fail("deletion of historical artifact URLs is forbidden")
    trusted_checkout = text.find("ref: main")
    scope = text.find('git diff --name-status "${MAIN_SHA}" "${STAGING_SHA}"')
    switch = text.find('git switch --detach "${STAGING_SHA}"')
    if not (0 <= trusted_checkout < scope < switch):
        fail("trusted main checkout and scope validation must precede any staging execution")

    dangerous_pushes = [
        r"git\s+push[^\n]*refs/heads/main",
        r"git\s+push[^\n]*\bHEAD:main\b",
        r"git\s+push[^\n]*refs/heads/staging",
        r"git\s+push[^\n]*\bHEAD:staging\b",
    ]
    for pattern in dangerous_pushes:
        if re.search(pattern, text):
            fail("Accounting release workflow must never push directly to main or staging")

    dry = text.find('python scripts/prepare_accounting_release.py "${VERSION}"')
    backup = text.find('BACKUP_SHA="${MAIN_SHA}"')
    apply = text.find("--apply", dry + 1)
    gate = text.find("python scripts/verify_prepare_accounting_release_workflow.py", apply)
    branch_push = text.find('git push origin "HEAD:refs/heads/${RELEASE_BRANCH}"')
    pr = text.find("gh pr create")
    if min(dry, backup, apply, gate, branch_push, pr) < 0:
        fail("could not establish Accounting release workflow ordering")
    if not (dry < backup < apply < gate < branch_push < pr):
        fail("required order is dry-run -> rollback SHA -> apply -> full gate -> branch push -> PR")

    gate_markers = (
        "python scripts/verify_automation_landing_intents.py",
        "python scripts/verify_public_seo_uniqueness.py",
        "python scripts/verify_public_contextual_links.py",
        "python scripts/test_demo_dialog_contract.py",
        "python scripts/test_public_faq_schema.py",
        "python scripts/verify_quality_gate_workflows.py",
        "python scripts/test_quality_gate_workflows.py",
        "python scripts/test_sitemap_freshness.py",
        "python scripts/verify_sitemap_freshness.py",
        "python scripts/test_live_host_normalization.py",
        "python scripts/test_live_cloudflare_privacy.py",
        "python scripts/test_live_sitemap.py",
        "python scripts/verify_release_gate_parity.py",
        "python scripts/test_release_gate_parity.py",
        "python scripts/test_release_changelog_counts.py",
        live_compile,
        "python scripts/verify_accounting_release.py",
        "python scripts/prepare_accounting_release.py --check-current",
        "python scripts/test_prepare_accounting_release.py",
        "python scripts/verify_release_metadata.py",
        "python scripts/prepare_public_release.py --check-current",
        "git diff --check",
    )
    for marker in gate_markers:
        pos = text.find(marker, apply)
        if pos <= apply or pos >= branch_push:
            fail(f"release gate marker must run after apply and before branch push: {marker}")

    print("Prepare Accounting release workflow guard: PASS")
    print("  manual workflow_dispatch only")
    print("  staging accepts installer + reviewed Windows receipt + authored changelog")
    print("  checksum/manifest/pages are generated after dry-run and immutable rollback SHA")
    print("  stable OutPOSt installer/checksum/version and protected backend files are excluded")
    print("  current SEO/quality/privacy/sitemap regressions plus Accounting and stable OutPOSt guards run before PR")
    print("  direct main/staging push, auto-merge and Cloudflare deploy are forbidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
