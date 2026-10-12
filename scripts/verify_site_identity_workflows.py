#!/usr/bin/env python3
"""Fail-closed wiring guard for OutPOSt site-identity checks."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

SMOKE = WORKFLOWS / "public-site-smoke.yml"
PUBLIC_RELEASE = WORKFLOWS / "prepare-public-release.yml"
ACCOUNTING_RELEASE = WORKFLOWS / "prepare-accounting-release.yml"
LIVE = WORKFLOWS / "live-production-verify.yml"

SOURCE_RUN = "python scripts/verify_site_identity.py"
LIVE_RUN = "python scripts/verify_live_site_identity.py"
WIRING_RUN = "python scripts/verify_site_identity_workflows.py"


def fail(message: str) -> None:
    print("Site identity workflow wiring guard: FAIL", file=sys.stderr)
    print(f"  - {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: Path) -> str:
    if not path.is_file():
        fail(f"missing workflow: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def require(text: str, marker: str, label: str) -> None:
    if marker not in text:
        fail(f"{label}: missing marker: {marker}")


def require_between(text: str, marker: str, after: str, before: str, label: str) -> None:
    after_pos = text.find(after)
    marker_pos = text.find(marker, max(0, after_pos + len(after)))
    before_pos = text.find(before, max(0, marker_pos + len(marker)))
    if after_pos < 0 or marker_pos < 0 or before_pos < 0 or not (after_pos < marker_pos < before_pos):
        fail(f"{label}: required ordering is not preserved")


def main() -> int:
    smoke = read(SMOKE)
    public_release = read(PUBLIC_RELEASE)
    accounting_release = read(ACCOUNTING_RELEASE)
    live = read(LIVE)

    for marker in (
        '"scripts/verify_site_identity.py"',
        '"scripts/verify_live_site_identity.py"',
        '"scripts/verify_site_identity_workflows.py"',
        SOURCE_RUN,
        WIRING_RUN,
    ):
        require(smoke, marker, "public-site-smoke")
    require(
        smoke,
        "python -m py_compile scripts/verify_site_identity.py scripts/verify_live_site_identity.py scripts/verify_site_identity_workflows.py",
        "public-site-smoke compile gate",
    )

    public_apply = 'python scripts/prepare_public_release.py "${VERSION}" --apply'
    public_push = 'git push origin "HEAD:refs/heads/${RELEASE_BRANCH}"'
    require_between(public_release, SOURCE_RUN, public_apply, public_push, "public release source identity gate")
    require_between(public_release, WIRING_RUN, public_apply, public_push, "public release wiring self-guard")
    require(
        public_release,
        "python -m py_compile scripts/verify_site_identity.py scripts/verify_live_site_identity.py scripts/verify_site_identity_workflows.py",
        "public release identity compile gate",
    )

    accounting_apply = "--apply"
    accounting_push = 'git push origin "HEAD:refs/heads/${RELEASE_BRANCH}"'
    require_between(accounting_release, SOURCE_RUN, accounting_apply, accounting_push, "Accounting release source identity gate")
    require_between(accounting_release, WIRING_RUN, accounting_apply, accounting_push, "Accounting release wiring self-guard")
    require(
        accounting_release,
        "python -m py_compile scripts/verify_site_identity.py scripts/verify_live_site_identity.py scripts/verify_site_identity_workflows.py",
        "Accounting release identity compile gate",
    )

    for marker in (
        '"scripts/verify_site_identity.py"',
        '"scripts/verify_live_site_identity.py"',
        SOURCE_RUN,
        LIVE_RUN,
    ):
        require(live, marker, "live-production-verify")
    require_between(
        live,
        LIVE_RUN,
        SOURCE_RUN,
        "python scripts/verify_live_cabinet_entry.py",
        "live source-before-live identity ordering",
    )

    print("Site identity workflow wiring guard: PASS")
    print("  PR/staging smoke runs the source identity guard and protects wiring")
    print("  public and Accounting release gates run source identity checks before branch push")
    print("  identity verifiers are compile-checked in smoke and both release workflows")
    print("  post-merge production verification runs source identity before live source/asset parity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
