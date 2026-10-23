"""Require real reviewed deployment provenance BEFORE any canonical live GET/confirmation."""
from pathlib import Path
import re
import sys
ROOT = Path(__file__).resolve().parents[1]

def verify_live(text):
    markers = ["github.repository == 'MorvuddEzkaton/outpost-public-site'", "github.ref == 'refs/heads/main'",
               "github.actor == github.repository_owner", "environment: production", "timeout-minutes: 45", "permissions:\n  contents: read",
               "vars.OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED == '1'", "ref: ${{ github.sha }}", "persist-credentials: false",
               "python scripts/production_deployment_gate.py --check --wait-seconds 2100",
               "secrets.OUTPOST_PAGES_DEPLOY_TOKEN", "GITHUB_TOKEN: ${{ github.token }}", 'OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED: ${{ vars.OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED }}', '"scripts/production_deployment_gate.py"', '"scripts/verify_cloudflare_config.py"']
    errors = [f'missing live provenance marker: {marker}' for marker in markers if marker not in text]
    guard = text.find('run: python scripts/production_deployment_gate.py --check')
    for command in re.findall(r'run: python (scripts/verify_live_[^\s]+\.py)', text):
        if guard < 0 or text.find('run: python ' + command) < guard:
            errors.append('canonical live verifier precedes exact deployment proof: ' + command)
    if any(x in text for x in ['continue-on-error:', 'contents: write', 'pull-requests: write', 'pull_request_target:', 'workflow_run:', 'printenv', 'set -x']):
        errors.append('unsafe privilege or failure/logging bypass in live workflow')
    return errors

def verify_confirmation(text):
    errors = []
    guard = text.find('run: python scripts/production_deployment_gate.py --check')
    for marker in ['run: python scripts/verify_live_production.py', 'python scripts/verify_live_production.py', 'secrets.OUTPOST_RELEASE_CONFIRM_KEY']:
        location = text.find(marker)
        if location >= 0 and (guard < 0 or location < guard):
            errors.append('release canonical GET/confirmation precedes production proof')
    if guard < 0 or 'secrets.OUTPOST_PAGES_DEPLOY_TOKEN' not in text:
        errors.append('confirmation deployment credential/provenance missing')
    if 'OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED: ${{ vars.OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED }}' not in text:
        errors.append('confirmation automatic-mode setting missing')
    return errors

def main():
    workflows=ROOT/'.github/workflows'
    errors=verify_live((workflows/'live-production-verify.yml').read_text(encoding='utf-8'))
    errors+=verify_confirmation((workflows/'confirm-telegram-release.yml').read_text(encoding='utf-8'))
    smoke=(workflows/'public-site-smoke.yml').read_text(encoding='utf-8')
    for marker in ['python scripts/verify_production_deployment_workflows.py','python scripts/test_production_deployment_gate.py',
                   'python scripts/test_production_deployment_workflows.py','node scripts/test_release_mode_health.mjs']:
        if marker not in smoke: errors.append('offline PR coverage missing: '+marker)
    if errors:
        print('Production deployment workflow guard: FAIL\n'+'\n'.join(errors));return 1
    print('Production deployment workflow guard: PASS; reviewed SHA/deployment/notification safety before canonical GETs; activation NOT implied')
    return 0

if __name__=='__main__':sys.exit(main())
