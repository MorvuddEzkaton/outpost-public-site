#!/usr/bin/env python3
"""Fail-closed parity guard for manual release gates versus Public site smoke checks."""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / ".github" / "workflows" / "public-site-smoke.yml"
RELEASE_WORKFLOWS = (
    ROOT / ".github" / "workflows" / "prepare-public-release.yml",
    ROOT / ".github" / "workflows" / "prepare-accounting-release.yml",
)


def normalized_commands(text: str) -> list[str]:
    commands: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("- run: "):
            line = line[7:].strip()
        elif line.startswith("run: "):
            line = line[5:].strip()
        commands.append(line)
    return commands


def direct_scripts(text: str) -> set[str]:
    scripts: set[str] = set()
    for line in normalized_commands(text):
        match = re.match(r"^(?:python|node)\s+(scripts/[^\s]+\.(?:py|mjs))(?:\s|$)", line)
        if match:
            scripts.add(match.group(1))
    return scripts


def py_compile_targets(text: str) -> set[str]:
    targets: set[str] = set()
    prefix = "python -m py_compile "
    for line in normalized_commands(text):
        if not line.startswith(prefix):
            continue
        for token in line[len(prefix):].split():
            if token.startswith("scripts/") and token.endswith(".py"):
                targets.add(token)
    return targets


def node_check_targets(text: str) -> set[str]:
    targets: set[str] = set()
    prefix = "node --check "
    for line in normalized_commands(text):
        if line.startswith(prefix):
            target = line[len(prefix):].strip()
            if target:
                targets.add(target)
    return targets


def compare_workflows(smoke_text: str, release_text: str, label: str) -> list[str]:
    errors: list[str] = []
    categories = (
        ("direct script", direct_scripts(smoke_text), direct_scripts(release_text)),
        ("py_compile target", py_compile_targets(smoke_text), py_compile_targets(release_text)),
        ("node --check target", node_check_targets(smoke_text), node_check_targets(release_text)),
    )
    for kind, expected, actual in categories:
        for missing in sorted(expected - actual):
            errors.append(f"{label}: missing smoke {kind}: {missing}")
    return errors


def main() -> int:
    paths = (SMOKE, *RELEASE_WORKFLOWS)
    missing = [path for path in paths if not path.is_file()]
    if missing:
        print("Release gate parity guard: FAIL", file=sys.stderr)
        for path in missing:
            print(f"  - missing workflow: {path.relative_to(ROOT)}", file=sys.stderr)
        return 1

    smoke_text = SMOKE.read_text(encoding="utf-8")
    errors: list[str] = []
    for path in RELEASE_WORKFLOWS:
        release_text = path.read_text(encoding="utf-8")
        errors.extend(compare_workflows(smoke_text, release_text, str(path.relative_to(ROOT))))

    if errors:
        print(f"Release gate parity guard: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Release gate parity guard: PASS")
    print(f"  smoke direct scripts: {len(direct_scripts(smoke_text))}")
    print(f"  smoke py_compile targets: {len(py_compile_targets(smoke_text))}")
    print(f"  smoke node --check targets: {len(node_check_targets(smoke_text))}")
    print("  public and Accounting manual release gates are supersets of smoke execution coverage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
