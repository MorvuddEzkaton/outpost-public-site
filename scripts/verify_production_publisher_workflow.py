"""Fail-closed wiring guard for the dormant protected Pages writer."""
from pathlib import Path
import re
import sys
ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/deploy-public-production.yml'
NOTIFICATION_STEP = '''      - name: Confirm future releases only after accepted live publication
        if: >-
          success() && github.event_name == 'push' &&
          steps.live.outcome == 'success' && steps.result.outcome == 'success' &&
          vars.OUTPOST_AUTOMATIC_RELEASE_CONFIRMATION_ENABLED == '1' &&
          vars.OUTPOST_RELEASE_DELIVERY_MODE == 'subscribers'
        env:
          OUTPOST_AUTOMATIC_RELEASE_CONFIRMATION_ENABLED: ${{ vars.OUTPOST_AUTOMATIC_RELEASE_CONFIRMATION_ENABLED }}
          OUTPOST_RELEASE_DELIVERY_MODE: ${{ vars.OUTPOST_RELEASE_DELIVERY_MODE }}
          OUTPOST_SAVED_RESULT_URL: ${{ steps.result.outputs.artifact-url }}
          OUTPOST_RELEASE_CONFIRM_KEY: ${{ secrets.OUTPOST_RELEASE_CONFIRM_KEY }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.OUTPOST_PAGES_DEPLOY_TOKEN }}
          GITHUB_TOKEN: ${{ github.token }}
        run: python scripts/confirm_published_releases.py --journal "$RUNNER_TEMP/outpost-production-journal.json" --apply'''

def verify(text):
    text = re.sub(r'(?m)^\s*#.*$', '', text)
    errors = []
    if not text.rstrip().endswith(NOTIFICATION_STEP) or text.count(NOTIFICATION_STEP) != 1:
        errors.append('exact disabled post-result confirmation step required; no writer credential expansion')
    writer = text.removesuffix(NOTIFICATION_STEP + '\n')
    markers = [
        "vars.OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED == '1'", "vars.OUTPOST_PRODUCTION_WRITER_ENABLED == '1'",
        "github.repository == 'MorvuddEzkaton/outpost-public-site'", "github.ref == 'refs/heads/main'",
        'github.actor == github.repository_owner', 'cancel-in-progress: false', 'group: outpost-production-writer',
        'permissions:\n  contents: read', 'needs: [static-quality, browser-quality]', 'environment: production',
        'python scripts/run_production_quality.py', 'Pillow==12.3.0', 'sha256sum --check --strict',
        'gitleaks" dir .', 'gitleaks" git .', '--redact=100', 'actions: read',
        'GITHUB_TOKEN: ${{ github.token }}', 'secrets.OUTPOST_PAGES_DEPLOY_TOKEN',
        'steps.intent.outputs.artifact-url', 'if-no-files-found: error', 'retention-days: 7',
        'scripts/publisher-tools/package-lock.json', 'npm ci --ignore-scripts',
        'node scripts/test_telegram_transport_workerd.mjs',
        "failure() && steps.live.outcome == 'failure' && vars.OUTPOST_PRODUCTION_ROLLBACK_ENABLED == '1'",
        "always() && steps.plan.outcome == 'success'", 'outpost-production-result-${{ github.sha }}-${{ github.run_id }}'
    ]
    errors += ['missing required writer guard: ' + marker for marker in markers if marker not in text]
    jobs = re.findall(r'^  ([a-z-]+):\n    (?:if:|needs:)', text, re.MULTILINE)
    if jobs != ['static-quality', 'browser-quality', 'publish']:
        errors.append('writer requires exactly the three reviewed jobs')
    for name in ['pull_request:', 'pull_request_target:', 'workflow_run:', 'schedule:', 'continue-on-error:',
                 'contents: write', 'pull-requests: write', 'deployments: write', 'secrets.TELEGRAM',
                 'printenv', 'set -x', '|| true', 'secrets.CLOUDFLARE_API_TOKEN']:
        if name in text:
            errors.append('unsafe writer bypass or privilege: ' + name)
    if text.count('ref: ${{ github.sha }}') != 3 or text.count('persist-credentials: false') != 3:
        errors.append('all quality and protected checkouts must be exact and unpersisted')
    if 'OUTPOST_RELEASE_CONFIRM_KEY' in writer or 'OUTPOST_RELEASE_PUMP_KEY' in text or 'confirm_published_releases.py' in writer:
        errors.append('confirmation credential/code must be confined to the exact post-result step, never a pump')
    if text.count('if-no-files-found: error') != 2 or writer.count('secrets.OUTPOST_PAGES_DEPLOY_TOKEN') != 4 or text.count('secrets.OUTPOST_PAGES_DEPLOY_TOKEN') != 5:
        errors.append('both durable artifacts and all four authenticated operations must retain their guards')
    if not re.search(r'^on:\n  push:\n    branches:\n      - main\n  workflow_dispatch:', text, re.MULTILINE):
        errors.append('only push-main and owner manual dispatch may trigger writer')
    suites = ['a11y', 'keyboard', 'runtime', 'ui']
    for suite in suites:
        if 'npx playwright test scripts/browser_' + suite + '.spec.mjs --reporter=line --workers=1' not in text:
            errors.append('missing browser coverage: ' + suite)
    positions = [text.find('production_publisher.py plan '), text.find('id: intent'),
                 text.find('production_publisher.py execute '), text.find('production_publisher.py verify-live '),
                 text.find('production_publisher.py rollback '), text.find('name: Save final journal')]
    if min(positions) < 0 or positions != sorted(positions):
        errors.append('durable intent/upload/live/conditional rollback/final journal order is required')
    if '        id: result' not in writer or text.find(NOTIFICATION_STEP) < positions[-1]:
        errors.append('notification must follow the separately saved final result, never control rollback')
    runtime_test = text.find('run: node scripts/test_telegram_transport_workerd.mjs')
    install = text.find('npm ci --ignore-scripts')
    if not (0 <= install < runtime_test < positions[0]):
        errors.append('offline actual-runtime transport check must precede any plan or upload')
    before_publish = text.split('  publish:', 1)[0]
    if 'secrets.' in before_publish:
        errors.append('quality jobs must not have operational credentials')
    return errors

def main():
    errors = verify(WORKFLOW.read_text(encoding='utf-8'))
    errors += verify_checkpoints((ROOT / '.github/workflows/public-repository-security.yml').read_text(encoding='utf-8'))
    for name in ['public-site-smoke.yml', 'prepare-public-release.yml', 'prepare-accounting-release.yml']:
        text = (ROOT / '.github/workflows' / name).read_text(encoding='utf-8')
        for command in ['python scripts/test_production_publisher.py', 'python scripts/test_production_history.py', 'python scripts/verify_production_publisher_workflow.py',
                        'python scripts/test_production_publisher_workflow.py', 'python scripts/test_production_checkpoints.py',
                        'python scripts/verify_production_checkpoints.py']:
            if command not in text:
                errors.append('publisher regression missing from ' + name + ': ' + command)
        for target in ['scripts/production_history.py', 'scripts/test_production_history.py', 'scripts/production_checkpoints.py',
                       'scripts/verify_production_checkpoints.py', 'scripts/test_production_checkpoints.py']:
            if not any(target in line for line in text.splitlines() if 'python -m py_compile ' in line):
                errors.append('history compilation missing from ' + name + ': ' + target)
    if errors:
        print('Production publisher workflow: FAIL\n' + '\n'.join(errors))
        return 1
    print('Production publisher workflow: PASS; dormant opt-in, protected main, all quality gates, durable intent and conditional code-only rollback')
    return 0


def verify_checkpoints(text):
    text = re.sub(r'(?m)^\s*#.*$', '', text)
    required = ['permissions:\n      contents: read\n      actions: read', 'fetch-depth: 0', 'persist-credentials: false',
                'CHECKPOINT_BASE_SHA: ${{ github.event.pull_request.base.sha || github.sha }}',
                'GITHUB_TOKEN: ${{ github.token }}', 'run: python scripts/verify_production_checkpoints.py --check-new']
    errors = ['missing checkpoint guard: ' + marker for marker in required if marker not in text]
    for marker in ['contents: write', 'actions: write', 'secrets.', 'continue-on-error:', 'pull_request_target:',
                   'workflow_run:', 'schedule:', '--capture', '|| true']:
        if marker in text:
            errors.append('unsafe checkpoint verification privilege/bypass: ' + marker)
    return errors

if __name__ == '__main__':
    sys.exit(main())
