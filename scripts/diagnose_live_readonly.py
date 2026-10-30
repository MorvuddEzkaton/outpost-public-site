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



def diagnose_static_asset_failures() -> None:
    """Print only bounded, public URL paths and normalized failure classes.

    No HTTP bodies, response headers, redirect locations, query strings or
    exceptions are logged. The protected publisher's own acceptance remains
    unchanged; this diagnostic has no credentials and performs no writes.
    """
    from urllib.parse import urlparse
    import re
    import verify_live_static_assets as static

    urls, pages, demo = static.collect_public_assets()
    failures = []
    for url in urls:
        problem, cache = static.verify_asset(url, attempts=1, delay_seconds=0)
        reason = None
        if problem:
            status = re.fullmatch(r"expected HTTP 200, got ([0-9]{3})", problem)
            if status:
                reason = "http-" + status.group(1)
            elif problem.startswith("HTTP ") and " redirect -> " in problem:
                reason = "redirect"
            elif problem.startswith("content-type "):
                reason = "content-type-mismatch"
            elif problem.startswith("network error: "):
                reason = "network-error"
            else:
                reason = "other-http-check-failure"
        elif url in demo and not static.cache_control_revalidates(cache):
            reason = "demo-cache-policy"

        if reason:
            path = urlparse(url).path
            if not re.fullmatch(r"/[A-Za-z0-9_./%~-]{1,240}", path):
                path = "[redacted-path]"
            failures.append((path, reason))

    print(f"Static asset diagnostic: {len(urls)} public files from {pages} sitemap pages; "
          f"{len(failures)} failures. Read-only; not a deployment acceptance.", flush=True)
    for path, reason in failures[:30]:
        print(f"  asset: {path} | {reason}", flush=True)
    if len(failures) > 30:
        print(f"  ... {len(failures) - 30} additional failures omitted", flush=True)


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
            if command == 'verify_live_static_assets.py':
                try:
                    diagnose_static_asset_failures()
                except Exception:
                    print('Static asset diagnostic aborted without disclosing raw responses', flush=True)
    print(f'Diagnostic summary: {len(publisher.LIVE_COMMANDS) - len(failed)}/{len(publisher.LIVE_COMMANDS)} PASS; public GET only; no acceptance recorded', flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
