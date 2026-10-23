#!/usr/bin/env python3
"""Read-only, credential-free diagnostic for current public production contracts.

This is not a publication acceptance or recovery proof: it identifies the
specific independently failing verifier before any more write attempts.
Never emits response bodies, URLs with tokens or the verifier's stdout/stderr.
"""
from __future__ import annotations

import os
from pathlib import Path
import production_publisher as publisher

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    # Bound diagnosis so a broken public endpoint does not hold a runner for
    # hours. Full protected publisher retains its stricter default retries.
    for name in publisher.LIVE_TUNING_ENV:
        if name.endswith('_ATTEMPTS'):
            os.environ[name] = '2'
        elif name.endswith('_DELAY_SECONDS'):
            os.environ[name] = '2'
        elif name.endswith('_WORKERS'):
            os.environ[name] = '2'
    failed = []
    for command in publisher.LIVE_COMMANDS:
        try:
            okay = publisher.run_live(ROOT, command)
        except Exception:
            print(f'Live verifier: ERROR — {command} (execution aborted)', flush=True)
            okay = False
        if not okay:
            failed.append(command)
    print(f'Diagnostic summary: {len(publisher.LIVE_COMMANDS) - len(failed)}/{len(publisher.LIVE_COMMANDS)} PASS; public GET only; no acceptance recorded', flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
