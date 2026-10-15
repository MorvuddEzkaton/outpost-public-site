"""Offline workflow and quality-inventory negative regressions."""
import unittest
import json
from verify_production_publisher_workflow import verify, WORKFLOW, NOTIFICATION_STEP
from run_production_quality import inventory, ROOT

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text()

    def test_valid_workflow(self):
        self.assertEqual(verify(self.text), [])

    def test_missing_guard_fails(self):
        for marker in ["vars.OUTPOST_PRODUCTION_WRITER_ENABLED == '1'", "environment: production", 'cancel-in-progress: false',
                       'needs: [static-quality, browser-quality]', 'steps.intent.outputs.artifact-url', 'if-no-files-found: error',
                       'python scripts/run_production_quality.py', 'persist-credentials: false', 'ref: ${{ github.sha }}',
                       'secrets.OUTPOST_PAGES_DEPLOY_TOKEN', 'sha256sum --check --strict', 'npm ci --ignore-scripts',
                       'node scripts/test_telegram_transport_workerd.mjs']:
            with self.subTest(marker=marker):
                self.assertTrue(verify(self.text.replace(marker, 'REMOVED', 1)))

    def test_credentials_never_in_quality_jobs(self):
        self.assertTrue(verify(self.text.replace('  static-quality:', '  static-quality:\n    env:\n      SECRET: ${{ secrets.OUTPOST_PAGES_DEPLOY_TOKEN }}', 1)))

    def test_confirmation_cannot_move_before_live_or_skip_a_guard(self):
        prefix = self.text.replace(NOTIFICATION_STEP, '')
        self.assertTrue(verify(NOTIFICATION_STEP + '\n' + prefix))
        for marker in ("success() && github.event_name == 'push'", "steps.live.outcome == 'success'", "steps.result.outcome == 'success'",
                       "vars.OUTPOST_AUTOMATIC_RELEASE_CONFIRMATION_ENABLED == '1'", "vars.OUTPOST_RELEASE_DELIVERY_MODE == 'subscribers'",
                       "OUTPOST_SAVED_RESULT_URL: ${{ steps.result.outputs.artifact-url }}", "id: result"):
            with self.subTest(marker=marker): self.assertTrue(verify(self.text.replace(marker, 'REMOVED', 1)))
        self.assertTrue(verify(self.text + '\n' + NOTIFICATION_STEP))

    def test_confirmation_key_cannot_leak_to_upload_or_gain_a_pump(self):
        for extra in ('OUTPOST_RELEASE_CONFIRM_KEY: ${{ secrets.OUTPOST_RELEASE_CONFIRM_KEY }}',
                      'OUTPOST_RELEASE_PUMP_KEY: ${{ secrets.OUTPOST_RELEASE_PUMP_KEY }}'):
            with self.subTest(extra=extra):
                self.assertTrue(verify(self.text.replace('      - name: Upload once', '      - name: ' + extra + '\n      - name: Upload once', 1)))

    def test_unsafe_triggers_privileges_logging_and_error_bypasses(self):
        for extra in ['pull_request_target:', 'pull_request:', 'workflow_run:', 'schedule:', 'contents: write',
                      'continue-on-error: true', 'printenv', 'set -x', '|| true', 'secrets.TELEGRAM_BOT_TOKEN']:
            with self.subTest(extra=extra):
                self.assertTrue(verify(self.text + '\n' + extra))

    def test_missing_browser_suite_fails(self):
        for suite in ['a11y', 'keyboard', 'runtime', 'ui']:
            with self.subTest(suite=suite):
                self.assertTrue(verify(self.text.replace('scripts/browser_' + suite + '.spec.mjs', 'REMOVED')))

    def test_upload_cannot_precede_saved_intent(self):
        self.assertTrue(verify(self.text.replace('production_publisher.py plan ', 'production_publisher.py execute ', 1)))
        self.assertTrue(verify(self.text.replace('id: intent', 'id: REMOVED', 1)))

    def test_actual_runtime_regression_cannot_move_after_the_production_operations(self):
        start=self.text.index('      - name: Verify Telegram transport in the actual offline edge runtime')
        end=self.text.index('      - name: Prepare read-only deployment plan',start)
        block=self.text[start:end]
        late=self.text[:start]+self.text[end:]+block
        self.assertTrue(verify(late))

    def test_commented_guard_cannot_substitute_for_code(self):
        self.assertTrue(verify(self.text.replace('    environment: production', '    # environment: production')))

    def test_quality_is_superset_of_smoke_without_live_gets(self):
        commands = inventory((ROOT / '.github/workflows/public-site-smoke.yml').read_text())
        self.assertGreater(len(commands), 80)
        self.assertIn(('python', 'scripts/verify_public_repository_security.py'), commands)
        self.assertIn(('python', 'scripts/verify_first_party_resources.py'), commands)
        self.assertIn(('python', 'scripts/verify_public_asset_budget.py'), commands)

    def test_inventory_rejects_injected_or_operational_commands(self):
        for line in ['run: python scripts/verify_live_production.py', 'node scripts/demo.mjs; printenv',
                     'python scripts/run_production_quality.py', 'python scripts/production_publisher.py execute']:
            with self.subTest(line=line), self.assertRaises(ValueError):
                inventory(line)

    def test_locked_toolchain_and_public_registry_integrity(self):
        directory = ROOT / 'scripts/publisher-tools'
        package = json.loads((directory / 'package.json').read_text())
        lock = json.loads((directory / 'package-lock.json').read_text())
        self.assertEqual(package['dependencies'], {'wrangler': '4.142.0'})
        self.assertEqual(lock['packages']['']['dependencies'], package['dependencies'])
        self.assertEqual(lock['packages']['node_modules/wrangler']['version'], '4.142.0')
        for name, entry in lock['packages'].items():
            if not name:
                continue
            self.assertTrue(entry['resolved'].startswith('https://registry.npmjs.org/'))
            self.assertTrue(entry['integrity'].startswith('sha512-'))

if __name__ == '__main__':
    unittest.main()
