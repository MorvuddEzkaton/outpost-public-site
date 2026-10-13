"""Run all credential-free smoke commands plus the other static quality gates.

Read the reviewed smoke inventory rather than maintaining a shorter deploy-only
list. Browser suites run in a separate unprivileged job. No canonical live GETs.
"""
from pathlib import Path
import os
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXTRA = ['python scripts/test_public_repository_security.py', 'python scripts/verify_public_repository_security.py',
         'python scripts/verify_public_asset_budget.py', 'python scripts/verify_first_party_resources.py',
         'python scripts/test_sitemap_freshness.py', 'python scripts/verify_sitemap_freshness.py',
         'python scripts/verify_navigation_style_contract.py']

def inventory(text):
    commands = []
    for raw in text.splitlines():
        line = re.sub(r'^run:\s*', '', raw.strip())
        if not line.startswith(('python ', 'node ')):
            continue
        if not re.fullmatch(r'(?:python|node) [A-Za-z0-9_./ -]+', line):
            raise ValueError('nonliteral_quality_command')
        if re.match(r'python scripts/(?:verify_live_|production_publisher\.py|run_production_quality\.py)', line):
            raise ValueError('recursive_or_operational_quality_command')
        commands.append(shlex.split(line))
    for line in EXTRA:
        commands.append(shlex.split(line))
    return list(dict.fromkeys(tuple(command) for command in commands))

def main():
    # No credentials are needed or passed through to test subprocesses.
    env = {name: value for name, value in os.environ.items() if not name.startswith('GIT_CONFIG_') and
           not any(part in name.upper() for part in ('TOKEN', 'SECRET', 'PASSWORD', 'KEY'))}
    # Trust only this explicitly selected checkout for read-only Git history under
    # a local sandbox account; do not alter global Git trust or retain auth headers.
    env.update({'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'safe.directory', 'GIT_CONFIG_VALUE_0': str(ROOT)})
    commands = inventory((ROOT / '.github/workflows/public-site-smoke.yml').read_text())
    for command in commands:
        runtime = sys.executable if command[0] == 'python' else 'node'
        print('CHECK: ' + ' '.join(command), flush=True)
        result = subprocess.run([runtime, *command[1:]], cwd=ROOT, env=env, timeout=180, check=False)
        if result.returncode != 0:
            print('Production static quality: FAIL; no deployment authorized')
            return 1
    print(f'Production static quality: PASS ({len(commands)} commands); browser/remote publication NOT certified')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
