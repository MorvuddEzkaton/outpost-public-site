#!/usr/bin/env python3
"""Synthetic tests for verify_release_gate_parity.py."""

from __future__ import annotations

from verify_release_gate_parity import compare_workflows


SMOKE = """jobs:
  smoke:
    steps:
      - run: python scripts/a.py
      - run: node scripts/b.mjs
      - run: python -m py_compile scripts/a.py scripts/c.py
      - run: node --check site/script.js
"""

RELEASE = """jobs:
  release:
    steps:
      - run: |
          python scripts/a.py
          node scripts/b.mjs
          python -m py_compile scripts/a.py scripts/c.py
          node --check site/script.js
          python scripts/release_only.py
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_superset_passes() -> None:
    require(compare_workflows(SMOKE, RELEASE, "release") == [], "superset release gate must pass")


def test_missing_direct_script_fails() -> None:
    broken = RELEASE.replace("          node scripts/b.mjs\n", "")
    errors = compare_workflows(SMOKE, broken, "release")
    require(any("direct script" in item and "b.mjs" in item for item in errors), "missing direct script must fail")


def test_missing_compile_target_fails() -> None:
    broken = RELEASE.replace(" scripts/c.py", "")
    errors = compare_workflows(SMOKE, broken, "release")
    require(any("py_compile target" in item and "c.py" in item for item in errors), "missing compile target must fail")


def test_missing_node_check_fails() -> None:
    broken = RELEASE.replace("          node --check site/script.js\n", "")
    errors = compare_workflows(SMOKE, broken, "release")
    require(any("node --check target" in item and "site/script.js" in item for item in errors), "missing node check must fail")


def main() -> int:
    tests = (
        test_superset_passes,
        test_missing_direct_script_fails,
        test_missing_compile_target_fails,
        test_missing_node_check_fails,
    )
    for test in tests:
        test()
    print("Release gate parity synthetic tests: PASS")
    print(f"  {len(tests)}/{len(tests)} offline tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
