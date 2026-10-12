#!/usr/bin/env python3
"""Static fail-closed guard for the manual public-site rollback workflow."""

from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "prepare-safe-rollback.yml"


def fail(message: str) -> None:
    print("Safe rollback workflow guard: FAIL", file=sys.stderr)
    print(f"  - {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if not WORKFLOW.is_file():
        fail("prepare-safe-rollback.yml is missing")

    text = WORKFLOW.read_text(encoding="utf-8")

    allowed_top_level = {"name", "on", "permissions", "concurrency", "jobs"}
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):(?:\s|$)", line)
        if not match or match.group(1) not in allowed_top_level:
            fail(f"unexpected column-zero content at line {lineno}: {line}")

    required = {
        "manual-only trigger": "workflow_dispatch:",
        "write permission for backup/rollback branches": "contents: write",
        "write permission for rollback PR": "pull-requests: write",
        "current main checkout": "ref: main",
        "ancestor-only rollback gate": "git merge-base --is-ancestor",
        "current release extraction": 'CURRENT_RELEASE="$(extract_release_version "${CURRENT_SHA}")"',
        "target release extraction": 'TARGET_RELEASE="$(extract_release_version "${TARGET_SHA}")"',
        "same-release rollback gate": 'if [ "${CURRENT_RELEASE}" != "${TARGET_RELEASE}" ]; then',
        "cross-release rollback explanation": "Public-site rollback cannot cross release boundary",
        "explicit release rollback requirement": "Installer downgrade requires explicit release rollback",
        "automatic pre-rollback backup": "backup/rollback-pre-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}",
        "isolated rollback branch": "rollback/${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}",
        "public site restore": 'git restore --source "${TARGET_SHA}" --staged --worktree -- site',
        "current public Worker preserve": "site/_worker.js",
        "current Telegram support Worker preserve": "site/_telegram-support.js",
        "current Telegram FAQ preserve": "site/_telegram-faq.js",
        "current security headers preserve": "site/_headers",
        "current installer payload preserve": "site/downloads",
        "pull request creation": "gh pr create",
        "pull request targets main": "--base main",
        "no automatic merge statement": "does **not** merge the PR",
    }
    for label, marker in required.items():
        if marker not in text:
            fail(f"{label}: protected marker is missing: {marker}")

    if re.search(r"(?m)^\s{2}(push|pull_request|schedule):\s*$", text):
        fail("rollback workflow must remain workflow_dispatch-only")

    forbidden_literals = {
        "automatic PR merge": "gh pr merge",
        "Cloudflare/Wrangler deployment": "wrangler deploy",
        "hard reset": "git reset --hard",
        "force push flag": "--force",
        "force push short flag": " -f ",
    }
    for label, marker in forbidden_literals.items():
        if marker in text:
            fail(f"{label} is forbidden in the rollback preparation workflow")

    dangerous_push_patterns = [
        r"git\s+push[^\n]*refs/heads/main",
        r"git\s+push[^\n]*\bHEAD:main\b",
        r"git\s+push[^\n]*\borigin\s+main\b",
    ]
    for pattern in dangerous_push_patterns:
        if re.search(pattern, text):
            fail("rollback workflow must never push directly to main")

    broad_restore = text.find('git restore --source "${TARGET_SHA}" --staged --worktree -- site')
    protected_restore = text.find('git restore --source "${CURRENT_SHA}" --staged --worktree --')
    if broad_restore < 0 or protected_restore <= broad_restore:
        fail("protected current-version restore must happen after the target site restore")

    ancestor_gate = text.find("git merge-base --is-ancestor")
    release_gate = text.find('if [ "${CURRENT_RELEASE}" != "${TARGET_RELEASE}" ]; then')
    first_branch_write = text.find('git push origin "${CURRENT_SHA}:refs/heads/${BACKUP_BRANCH}"')
    if ancestor_gate < 0 or release_gate <= ancestor_gate or first_branch_write <= release_gate:
        fail("same-release gate must run after ancestor validation and before any backup/rollback branch write")

    print("Safe rollback workflow guard: PASS")
    print("  workflow structure has no unexpected column-zero content")
    print("  manual trigger only")
    print("  ancestor-only target + same-release-version gate before any branch write")
    print("  automatic pre-rollback backup")
    print("  protected Worker/security/installer paths stay current")
    print("  PR-only handoff; direct main push/merge/deploy forbidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
