#!/usr/bin/env python3
"""Static fail-closed guard for the manual public-release PR workflow."""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "prepare-public-release.yml"


def fail(message: str) -> None:
    print("Prepare public release workflow guard: FAIL", file=sys.stderr)
    print(f"  - {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if not WORKFLOW.is_file():
        fail("prepare-public-release.yml is missing")

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
        "manual-only trigger": "workflow_dispatch:",
        "target version input": "version:",
        "branch write permission": "contents: write",
        "pull request write permission": "pull-requests: write",
        "prepared staging checkout": "ref: staging",
        "full history for scope checks": "fetch-depth: 0",
        "main/staging refresh": "git fetch origin main staging --prune",
        "staging based on current main": 'git merge-base --is-ancestor "${MAIN_SHA}" "${STAGING_SHA}"',
        "target installer input": 'TARGET_EXE="site/downloads/OutPOSt-Setup-v${VERSION}.exe"',
        "target checksum input": 'TARGET_SHA="site/downloads/OutPOSt-Setup-v${VERSION}.sha256.txt"',
        "changelog-only metadata input": 'CHANGELOG="site/changelog.html"',
        "exact-three-input gate": 'if [ "${changed}" -ne 3 ]',
        "dry-run release preparation": 'python scripts/prepare_public_release.py "${VERSION}"',
        "automatic pre-release backup": 'BACKUP_BRANCH="backup/pre-v${VERSION}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"',
        "isolated release branch": 'RELEASE_BRANCH="release/v${VERSION}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"',
        "release apply": 'python scripts/prepare_public_release.py "${VERSION}" --apply',
        "generated public allowlist": 'site/*.html|site/sitemap.xml|"${TARGET_EXE}"|"${TARGET_SHA}"',
        "Worker protection": "site/_worker.js",
        "Telegram Worker protection": "site/_telegram-support.js",
        "Telegram FAQ protection": "site/_telegram-faq.js",
        "security headers protection": "site/_headers",
        "Cloudflare config protection": "wrangler.jsonc",
        "automation landing intent guard": "python scripts/verify_automation_landing_intents.py",
        "public SEO uniqueness guard": "python scripts/verify_public_seo_uniqueness.py",
        "public contextual link guard": "python scripts/verify_public_contextual_links.py",
        "demo contract regression": "python scripts/test_demo_dialog_contract.py",
        "FAQ schema regression": "python scripts/test_public_faq_schema.py",
        "quality workflow guard": "python scripts/verify_quality_gate_workflows.py",
        "quality workflow regression": "python scripts/test_quality_gate_workflows.py",
        "main provenance regression": "python scripts/test_main_push_provenance.py",
        "release workflow self guard": "python scripts/verify_prepare_release_workflow.py",
        "Accounting release workflow self guard": "python scripts/verify_prepare_accounting_release_workflow.py",
        "release gate parity guard": "python scripts/verify_release_gate_parity.py",
        "release gate parity regression": "python scripts/test_release_gate_parity.py",
        "release changelog count regression": "python scripts/test_release_changelog_counts.py",
        "Accounting current-release tool check": "python scripts/prepare_accounting_release.py --check-current",
        "Accounting synthetic next-release regression": "python scripts/test_prepare_accounting_release.py",
        "404 source guard": "python scripts/verify_404_page.py",
        "phone CTA guard": "python scripts/verify_phone_ctas.py",
        "installer verification": "python scripts/verify_installers.py",
        "Accounting pre-release verification": "python scripts/verify_accounting_release.py",
        "release metadata verification": "python scripts/verify_release_metadata.py",
        "release sitemap verification": "python scripts/verify_release_sitemap.py",
        "current-release final check": "python scripts/prepare_public_release.py --check-current",
        "synthetic next-release regression": "python scripts/test_prepare_public_release.py",
        "live verifier compilation": live_compile,
        "commercial terms guard": "python scripts/verify_public_license_terms.py",
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
        "Cabinet entry guard": "python scripts/verify_cabinet_entry.py",
        "diff whitespace gate": "git diff --check",
        "release branch push": 'git push origin "HEAD:refs/heads/${RELEASE_BRANCH}"',
        "pull request creation": "gh pr create",
        "pull request targets main": "--base main",
        "no automatic merge statement": "does **not** merge the PR",
    }
    for label, marker in required.items():
        if marker not in text:
            fail(f"{label}: protected marker is missing: {marker}")

    if re.search(r"(?m)^\s{2}(push|pull_request|schedule):\s*$", text):
        fail("release preparation workflow must remain workflow_dispatch-only")

    forbidden_literals = {
        "automatic PR merge": "gh pr merge",
        "Cloudflare/Wrangler deployment": "wrangler deploy",
        "hard reset": "git reset --hard",
        "force push flag": "--force",
        "force push short flag": " -f ",
    }
    for label, marker in forbidden_literals.items():
        if marker in text:
            fail(f"{label} is forbidden in the release preparation workflow")

    dangerous_push_patterns = [
        r"git\s+push[^\n]*refs/heads/main",
        r"git\s+push[^\n]*\bHEAD:main\b",
        r"git\s+push[^\n]*\borigin\s+main\b",
        r"git\s+push[^\n]*refs/heads/staging",
        r"git\s+push[^\n]*\bHEAD:staging\b",
    ]
    for pattern in dangerous_push_patterns:
        if re.search(pattern, text):
            fail("release workflow must never push directly to main or mutate staging")

    dry_run = text.find('python scripts/prepare_public_release.py "${VERSION}"')
    apply = text.find('python scripts/prepare_public_release.py "${VERSION}" --apply')
    backup = text.find('BACKUP_BRANCH="backup/pre-v${VERSION}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"')
    branch_push = text.find('git push origin "HEAD:refs/heads/${RELEASE_BRANCH}"')
    pr_create = text.find("gh pr create")
    if dry_run < 0 or apply <= dry_run:
        fail("dry-run must happen before --apply")
    if backup <= dry_run or backup >= apply:
        fail("automatic backup/isolated branch creation must happen after dry-run and before apply")
    if branch_push <= apply:
        fail("release branch push must happen only after release apply")
    if pr_create <= branch_push:
        fail("PR creation must happen only after the verified release branch is pushed")

    gate_markers = [
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
        "python scripts/verify_prepare_release_workflow.py",
        "python scripts/verify_prepare_accounting_release_workflow.py",
        "python scripts/verify_release_gate_parity.py",
        "python scripts/test_release_gate_parity.py",
        "python scripts/test_release_changelog_counts.py",
        "python scripts/prepare_accounting_release.py --check-current",
        "python scripts/test_prepare_accounting_release.py",
        "python scripts/verify_404_page.py",
        "python scripts/verify_phone_ctas.py",
        "python scripts/test_prepare_public_release.py",
        live_compile,
        "git diff --check",
    ]
    for marker in gate_markers:
        position = text.find(marker, apply)
        if position <= apply or position >= branch_push:
            fail(f"complete release gate marker must run after apply and before release branch push: {marker}")

    print("Prepare public release workflow guard: PASS")
    print("  manual trigger only; staging is read as prepared release input")
    print("  staging diff is constrained to installer + checksum + changelog")
    print("  dry-run -> automatic backup -> isolated branch -> apply ordering is fixed")
    print("  protected Worker/Telegram/headers/Cloudflare files are outside release scope")
    print("  release gate mirrors current SEO/quality/privacy/sitemap regressions and all live-verifier compile checks")
    print("  complete static release gate runs before branch push/PR")
    print("  direct main/staging push, auto-merge and deploy are forbidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
