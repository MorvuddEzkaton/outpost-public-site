"""Synthetic post-live tests: no real GitHub, Cloudflare, D1 or Telegram calls."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
import confirm_published_releases as auto
import production_publisher as publisher
import production_deployment_gate as gate
from release_integrity import IntegrityError
from release_test_fixtures import synthetic_pe, fixture_row, write_synthetic_receipt
from test_production_publisher import env, SHA, HEAD, OLD, NEW


class AutomaticConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / 'checkout'
        (self.root / 'site/downloads').mkdir(parents=True)
        shutil.copyfile(auto.ROOT / auto.POLICY, self.root / auto.POLICY)
        self.env = {**env(), 'OUTPOST_AUTOMATIC_RELEASE_CONFIRMATION_ENABLED': '1',
                    'OUTPOST_RELEASE_DELIVERY_MODE': 'subscribers',
                    'OUTPOST_RELEASE_CONFIRM_KEY': 'SYNTHETIC-NOT-REAL-'.ljust(40, 'x'),
                    'OUTPOST_SAVED_RESULT_URL': 'https://github.com/' + gate.REPOSITORY + '/actions/runs/1234/artifacts/5679'}
        self.rows = [{'path': 'site/demo.html', 'bytes': 4, 'sha256': 'd' * 64}]
        change = patch.object(publisher, 'manifest', return_value=self.rows)
        change.start(); self.addCleanup(change.stop)
        states = ['prepared', 'upload_intent', 'upload_returned', 'deployment_success', 'live_intent', 'live_pass']
        events = [{'at': publisher.now(), 'state': state,
                   **({'command_returned': True} if state == 'upload_returned' else {}),
                   **({'deployment_id': NEW} if state in ('deployment_success', 'live_pass') else {})} for state in states]
        self.journal = {'schema': 1, 'run_id': '1234', 'source_sha': SHA,
                        'configuration_sha256': publisher.APPROVED_CONFIG_HASH,
                        'package_sha256': publisher.digest(self.rows), 'project_sha256': 'e' * 64,
                        'baseline_id': OLD, 'baseline_sha': 'c' * 40, 'initial_ids': [OLD],
                        'review': {'pr': 10, 'head_sha': HEAD, 'owner_review_id': 10}, 'state': 'live_pass', 'events': events}
        self.proof = {'source_sha': SHA, 'deployment_id': NEW, 'review': self.journal['review']}
        self.verify = Mock(return_value=self.proof)
        self.request = Mock(side_effect=lambda payload, key: {'ok': True, 'audience': 'subscribers',
                            'confirmed': True, 'product': payload['product'], 'version': payload['version'], 'notification_sent': False})
        self.fixture()

    def fixture(self, outpost='0.24.40', accounting='1.0.2'):
        rows = []; links = []
        for product, release in (('outpost', outpost), ('accounting', accounting)):
            filename = auto.COUNTERPART[product] + release + '.exe'
            installer = self.root / 'site/downloads' / filename
            installer.write_bytes(synthetic_pe(2048))
            import hashlib
            installer.with_suffix('.sha256.txt').write_text(hashlib.sha256(installer.read_bytes()).hexdigest().upper() + ' *' + filename)
            rows.append(fixture_row(installer, product, release))
            write_synthetic_receipt(self.root, installer, product, release)
            links.append('<a href="/downloads/' + filename + '">SYNTHETIC</a>')
        (self.root / 'site/download.html').write_text(''.join(links), encoding='utf-8')
        target = self.root / 'release/artifact-registry.json'
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps({'schema_version': 1, 'artifacts': rows}), encoding='utf-8')
        # Keep only this fixture's immutable artifact inventory.
        for file in (self.root / 'site/downloads').iterdir():
            if file.name not in {name for row in rows for name in (row['installer'], row['checksum'])}:
                file.unlink()  # Synthetic temporary test data only.

    def run_confirmation(self, apply=True, **changes):
        return auto.confirm_future({**self.env, **changes}, self.root, self.journal, apply, self.verify, self.request)

    def assert_no_requests(self):
        self.verify.assert_not_called(); self.request.assert_not_called()

    def test_current_versions_never_require_credentials_or_network(self):
        result = self.run_confirmation(OUTPOST_RELEASE_CONFIRM_KEY='')
        self.assertTrue(result['ok']); self.assertEqual(result['state'], 'no_future_releases')
        self.assertFalse(result['notification_sent']); self.assert_no_requests()

    def test_missing_historical_receipt_does_not_promote_it_to_a_notice(self):
        with patch.object(auto.manual, 'confirmation_payload', side_effect=AssertionError('No historical receipt should be loaded')):
            self.assertEqual(auto.candidates(self.root, SHA), [])

    def test_default_is_plan_only_even_when_activation_exists(self):
        self.fixture(outpost='0.24.41')
        result = self.run_confirmation(apply=False)
        self.assertEqual(result['eligible'], [{'product': 'outpost', 'version': '0.24.41'}])
        self.assertEqual(result['state'], 'plan_only'); self.assert_no_requests()

    def test_semantic_cutoff_for_both_independent_products(self):
        for outpost, accounting, wanted in [('0.24.39', '1.0.1', []), ('0.24.41', '1.0.2', ['outpost']),
                                           ('0.24.40', '1.0.10', ['accounting']), ('0.25.0', '2.0.0', ['outpost', 'accounting'])]:
            with self.subTest(versions=(outpost, accounting)):
                self.fixture(outpost, accounting)
                self.assertEqual([p['product'] for p in auto.candidates(self.root, SHA)], wanted)

    def test_malformed_or_overflow_version_rejected(self):
        for value in ['01.2.3', '1.2', '1.-2.3', '1.2.3 ', '1.2.3-beta', '9007199254740992.0.0', None, True]:
            with self.subTest(value=value), self.assertRaises(IntegrityError): auto.version(value)

    def test_owner_cutoff_cannot_silently_change_or_gain_fields(self):
        for policy in [{'schema': True, 'minimum_exclusive': auto.PINNED_CUTOFF},
                       {'schema': 1, 'minimum_exclusive': {**auto.PINNED_CUTOFF, 'outpost': '0.24.39'}},
                       {'schema': 1, 'minimum_exclusive': auto.PINNED_CUTOFF, 'all': True}]:
            with self.subTest(policy=policy):
                (self.root / auto.POLICY).write_text(json.dumps(policy))
                with self.assertRaises(IntegrityError): self.run_confirmation()
        self.assert_no_requests()

    def test_ambiguous_product_version_never_confirms(self):
        with (self.root / 'site/download.html').open('a') as stream: stream.write('OutPOSt-Setup-v0.24.41.exe')
        with self.assertRaises(IntegrityError): self.run_confirmation()
        self.assert_no_requests()

    def test_missing_or_unapproved_future_windows_receipt_is_blocked(self):
        self.fixture(outpost='0.24.41')
        receipt = self.root / 'release/evidence/outpost-v0.24.41.json'
        data = json.loads(receipt.read_text())
        receipt.write_text(json.dumps({**data, 'approved_for_publication': False}))
        with self.assertRaises(IntegrityError): self.run_confirmation()
        receipt.unlink()
        with self.assertRaises(IntegrityError): self.run_confirmation()
        self.assert_no_requests()

    def test_changed_installer_or_package_fails_before_credentials(self):
        self.fixture(outpost='0.24.41')
        (self.root / 'site/downloads/OutPOSt-Setup-v0.24.41.exe').write_bytes(b'BROKEN')
        with self.assertRaises(IntegrityError): self.run_confirmation()
        self.fixture(outpost='0.24.41')
        self.journal['package_sha256'] = 'f' * 64
        with self.assertRaises(gate.GateError): self.run_confirmation()
        self.assert_no_requests()

    def test_all_trusted_context_boundaries(self):
        changes = {'GITHUB_REPOSITORY': 'other/repo', 'GITHUB_REF': 'refs/heads/staging',
                   'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_WORKFLOW_REF': gate.REPOSITORY + '/.github/workflows/other.yml@refs/heads/main',
                   'GITHUB_SHA': 'wrong', 'GITHUB_RUN_ATTEMPT': '2', 'GITHUB_RUN_ID': 'wrong', 'GITHUB_RUN_NUMBER': '0',
                   'GITHUB_ACTIONS': 'false', 'RUNNER_OS': 'Windows', 'OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED': '0',
                   'OUTPOST_PRODUCTION_WRITER_ENABLED': '0'}
        for key, value in changes.items():
            with self.subTest(key=key), self.assertRaises(gate.GateError): self.run_confirmation(**{key: value})
        self.assert_no_requests()

    def test_live_pass_and_exact_saved_run_artifact_are_required(self):
        original = deepcopy(self.journal)
        self.journal['state'] = 'prepared'
        with self.assertRaises(gate.GateError): self.run_confirmation()
        self.journal = original
        for url in ['', 'https://github.com/' + gate.REPOSITORY + '/actions/runs/9999/artifacts/5679', 'https://evil.invalid/artifact']:
            with self.subTest(url=url), self.assertRaises(gate.GateError): self.run_confirmation(OUTPOST_SAVED_RESULT_URL=url)
        self.assert_no_requests()

    def test_activation_and_subscriber_mode_are_explicit(self):
        for change in [{'OUTPOST_AUTOMATIC_RELEASE_CONFIRMATION_ENABLED': '0'}, {'OUTPOST_RELEASE_DELIVERY_MODE': 'pilot'}, {'OUTPOST_RELEASE_DELIVERY_MODE': 'off'}]:
            with self.subTest(change=change), self.assertRaises(gate.GateError): self.run_confirmation(**change)
        self.assert_no_requests()

    def test_fresh_canonical_source_deployment_review_and_key_are_required(self):
        self.fixture(outpost='0.24.41')
        for change in [{'source_sha': 'f' * 40}, {'deployment_id': OLD}, {'review': {**self.journal['review'], 'owner_review_id': 999}}]:
            self.verify.return_value = {**self.proof, **change}
            with self.subTest(change=change), self.assertRaises(gate.GateError): self.run_confirmation()
        self.verify.return_value = self.proof
        with self.assertRaises(gate.GateError): self.run_confirmation(OUTPOST_RELEASE_CONFIRM_KEY='')
        self.request.assert_not_called()

    def test_future_confirmation_never_requests_a_tick_or_recipient(self):
        self.fixture(outpost='0.24.41')
        result = self.run_confirmation()
        self.assertTrue(result['ok']); self.assertFalse(result['notification_sent']); self.assertEqual(result['confirmed'], 1)
        self.assertEqual(self.request.call_count, 1)
        payload, key = self.request.call_args.args
        self.assertEqual(payload['action'], 'confirm'); self.assertEqual(payload['version'], '0.24.41')
        self.assertEqual(set(payload), {'action', 'product', 'version', 'sha256', 'size_bytes', 'source_sha'})
        self.assertEqual(key, self.env['OUTPOST_RELEASE_CONFIRM_KEY'])

    def test_two_products_are_independent_and_notification_failure_cannot_change_publication(self):
        self.fixture('0.24.41', '1.0.3')
        journal = deepcopy(self.journal)
        self.request.side_effect = [TimeoutError('PRIVATE'), {'ok': True, 'audience': 'subscribers', 'confirmed': True,
            'product': 'accounting', 'version': '1.0.3', 'notification_sent': False}]
        result = self.run_confirmation()
        self.assertFalse(result['ok']); self.assertEqual(result['confirmed'], 1); self.assertEqual(self.request.call_count, 2)
        self.assertEqual(result['state'], 'operator_attention_required'); self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertEqual(self.journal, journal); self.assertEqual(self.journal['state'], 'live_pass')

    def test_lost_or_mismatched_confirmation_ack_is_explicit_not_retried(self):
        self.fixture(outpost='0.24.41')
        for reply in [{'ok': False}, {'ok': True, 'audience': 'pilot'}, {'ok': True, 'confirmed': True, 'notification_sent': True}]:
            self.request.reset_mock(); self.request.side_effect = None; self.request.return_value = reply
            result = self.run_confirmation()
            self.assertFalse(result['ok']); self.assertFalse(result['notification_sent']); self.assertEqual(self.request.call_count, 1)

    def test_known_block_is_visible_in_summary_without_failing_or_rolling_back_code(self):
        file = self.directory / 'journal.json'; file.write_text(json.dumps(self.journal))
        summary = self.directory / 'summary.md'
        output = io.StringIO()
        with (patch.object(auto, 'ROOT', self.root), patch.object(auto, 'confirm_future', side_effect=gate.GateError('PRIVATE KEY')),
              patch.dict(auto.os.environ, {'GITHUB_STEP_SUMMARY': str(summary)}, clear=True), redirect_stdout(output)):
            self.assertEqual(auto.main(['--journal', str(file), '--apply']), 0)
        self.assertIn('confirmation_blocked', output.getvalue()); self.assertIn('::warning::', output.getvalue())
        self.assertNotIn('PRIVATE KEY', output.getvalue() + summary.read_text()); self.assert_no_requests()


if __name__ == '__main__': unittest.main()
