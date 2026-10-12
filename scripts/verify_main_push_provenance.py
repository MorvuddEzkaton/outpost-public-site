#!/usr/bin/env python3
"""Detect direct/unreviewed pushes to main after live production verification.

GitHub branch protection/rulesets are unavailable for this private repository on
the current plan. This post-check does not prevent deployment, but it makes the
live-production workflow fail visibly when an automatic main push does not look
like one of the GitHub PR merge styles actually used by this repository.

Manual workflow_dispatch runs are intentionally allowed regardless of HEAD shape.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

PR_SUFFIX_RE = re.compile(r"\(#\d+\)\s*$")
MERGE_PR_SUBJECT_RE = re.compile(r"^Merge pull request #\d+\b", re.IGNORECASE)


def has_pr_subject_marker(subject: str) -> bool:
    value = subject.strip()
    return bool(PR_SUFFIX_RE.search(value) or MERGE_PR_SUBJECT_RE.search(value))


def validate_provenance(event_name: str, parent_hashes: list[str], subject: str) -> list[str]:
    if event_name != "push":
        return []

    errors: list[str] = []
    if len(parent_hashes) not in {1, 2}:
        errors.append(
            "automatic main update must look like a GitHub PR merge: "
            f"one parent for squash PR merge or two parents for merge commit; "
            f"HEAD has {len(parent_hashes)} parent(s)"
        )

    if not has_pr_subject_marker(subject):
        errors.append(
            "automatic main update subject must carry a GitHub PR marker, "
            "either a suffix like '(#209)' or 'Merge pull request #209 ...'"
        )

    return errors


def head_metadata() -> tuple[list[str], str]:
    output = subprocess.check_output(
        ["git", "show", "-s", "--format=%P%n%s", "HEAD"],
        text=True,
        encoding="utf-8",
    )
    lines = output.splitlines()
    parents = lines[0].split() if lines else []
    subject = lines[1] if len(lines) > 1 else ""
    return parents, subject


def main() -> int:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "").strip()

    if event_name != "push":
        print("Main push provenance guard: PASS")
        print(f"  event {event_name or '<unknown>'!r} is not an automatic push; provenance enforcement skipped")
        return 0

    try:
        parents, subject = head_metadata()
    except (OSError, subprocess.CalledProcessError) as exc:
        print("Main push provenance guard: FAIL", file=sys.stderr)
        print(f"  - cannot inspect HEAD commit metadata: {exc}", file=sys.stderr)
        return 1

    errors = validate_provenance(event_name, parents, subject)
    if errors:
        print(f"Main push provenance guard: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print(f"  HEAD subject: {subject!r}", file=sys.stderr)
        print(f"  HEAD parents: {len(parents)}", file=sys.stderr)
        return 1

    print("Main push provenance guard: PASS")
    print(f"  automatic main update has a recognized PR merge shape ({len(parents)} parent(s))")
    print(f"  merge subject: {subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
