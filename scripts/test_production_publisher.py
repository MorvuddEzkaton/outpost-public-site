"""Synthetic publisher acceptance/negative tests. No real credentials or network."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import production_publisher as publisher
import production_deployment_gate as gate
import production_history as history
from test_production_deployment_gate import environment, project, protected_env, policies

SHA, HEAD = 'a' * 40, 'b' * 40
OLD = '11111111-1111-4111-8111-111111111111'
NEW = '22222222-2222-4222-8222-222222222222'
OTHER = '33333333-3333-4333-8333-333333333333'

def env():
    value = environment()
    value.update({'GITHUB_ACTIONS': 'true', 'RUNNER_OS': 'Linux', 'GITHUB_RUN_ID': '1234', 'GITHUB_RUN_ATTEMPT': '1',
                  'GITHUB_RUN_NUMBER': '2',
                  'OUTPOST_PRODUCTION_WRITER_ENABLED': '1', 'OUTPOST_PRODUCTION_ROLLBACK_ENABLED': '1',
                  'OUTPOST_SAVED_PLAN_URL': 'https://github.com/' + gate.REPOSITORY + '/actions/runs/1234/artifacts/5678'})
    return value

class FakeClient:
    def __init__(self):
        self.project = project()
        for config in self.project['deployment_configs'].values():
            config['wrangler_config_hash'] = publisher.ORIGINAL_CONFIG_HASH
        self.project['canonical_deployment']['deployment_trigger']['metadata']['commit_hash'] = 'c' * 40
        self.original = deepcopy(self.project['canonical_deployment'])
        self.items = [deepcopy(self.original)]
        self.health_value = {'ok': True, 'enabled': True, 'release_mode_schema': 1,
                             'confirmed_releases_enabled': True, 'legacy_release_notifications_enabled': False}
        self.main = SHA
        self.runs = [{'id': 1234, 'head_sha': SHA, 'head_branch': 'main', 'run_attempt': 1, 'run_number': 2,
                      'event': 'push', 'status': 'in_progress', 'conclusion': None, 'workflow_id': history.WORKFLOW_ID,
                      'path': history.WORKFLOW_PATH, 'repository': {'id': history.REPOSITORY_ID, 'full_name': gate.REPOSITORY},
                      'head_repository': {'id': history.REPOSITORY_ID}}]
        self.rollback_calls = []

    def publication_runs(self):
        first = {**self.runs[0], 'id': history.FIRST_RUN_ID, 'run_number': 1, 'head_sha': history.FIRST_SOURCE,
                 'status': 'completed', 'conclusion': 'success'} if self.runs else {
                     'id': history.FIRST_RUN_ID, 'run_number': 1, 'head_sha': history.FIRST_SOURCE,
                     'workflow_id': history.WORKFLOW_ID, 'path': history.WORKFLOW_PATH, 'run_attempt': 1,
                     'event': 'push', 'repository': {'id': history.REPOSITORY_ID, 'full_name': gate.REPOSITORY},
                     'head_repository': {'id': history.REPOSITORY_ID}}
        return deepcopy([first, *self.runs])

    def publication_artifacts(self, run):
        return []

    def skipped_publication_jobs(self, run):
        return [{'id': index + 1, 'name': name, 'run_id': run['id'], 'run_attempt': 1,
                 'head_sha': run['head_sha'], 'status': 'completed', 'conclusion': 'skipped',
                 'steps': [], 'runner_id': 0, 'runner_name': None}
                for index, name in enumerate(['static-quality', 'browser-quality', 'publish'])]

    def github(self, suffix):
        if suffix == '/git/ref/heads/main':
            return {'object': {'sha': self.main}}
        if suffix == '/environments/production':
            return protected_env()
        if suffix == '/environments/production/deployment-branch-policies':
            return policies()
        if '/reviews' in suffix:
            return [{'id': 10, 'user': {'login': gate.OWNER}, 'state': 'APPROVED', 'commit_id': HEAD, 'submitted_at': '2026-01-01T00:00:00Z'}]
        return [{'number': 10, 'merged_at': '2026-01-01T00:00:00Z', 'merge_commit_sha': SHA, 'head': {'sha': HEAD},
                 'base': {'ref': 'main', 'repo': {'full_name': gate.REPOSITORY}}}]

    def pages(self, suffix=''):
        return deepcopy(self.original if suffix else self.project)

    def inventory(self):
        return deepcopy(self.items)

    def health(self):
        return deepcopy(self.health_value)

    def publish(self, *args):
        item = deepcopy(self.original)
        item['id'] = NEW
        item['deployment_trigger']['metadata']['commit_hash'] = SHA
        self.project['canonical_deployment'] = item
        self.items.append(deepcopy(item))
        return 0

    def rollback(self, identity):
        self.rollback_calls.append(identity)
        self.project['canonical_deployment'] = deepcopy(self.original)

class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / 'checkout'
        self.root.mkdir()
        self.file = self.directory / 'journal.json'
        self.package = self.directory / 'upload'
        self.env = env()
        self.client = FakeClient()
        checkpoint_patch = patch.object(publisher.checkpoints, 'load_checked', return_value=[])
        checkpoint_patch.start()
        self.addCleanup(checkpoint_patch.stop)
        config = json.loads((gate.ROOT / 'wrangler.jsonc').read_text())
        self.source_patch = patch.object(gate, 'local_source', return_value=(config, publisher.ORIGINAL_CONFIG_HASH))
        self.source_patch.start()
        self.addCleanup(self.source_patch.stop)
        self.manifest_patch = patch.object(publisher, 'manifest', return_value=[{'path': 'site/demo.html', 'bytes': 4, 'sha256': 'd' * 64}])
        self.manifest_patch.start()
        self.addCleanup(self.manifest_patch.stop)
        self.journal = publisher.prepare(self.env, self.root, self.file, self.client)

    def execute(self, uploader=None):
        with patch.object(publisher, 'tool', return_value=Path('/pinned/wrangler.js')), patch.object(publisher, 'upload_package'), patch.object(publisher, 'verify_package'):
            return publisher.execute(self.env, self.root, self.journal, self.package, self.client, uploader or self.client.publish)

    def live(self, runner=lambda *_: True):
        with patch.object(gate, 'verify_current', return_value={}):
            publisher.verify_live(self.env, self.root, self.journal, self.client, runner)

    def fail_live(self):
        self.execute()
        with self.assertRaises(gate.GateError):
            self.live(lambda *_: False)

    def test_plan_is_readonly_minimal_and_persisted(self):
        self.assertEqual(self.journal.data['state'], 'prepared')
        self.assertEqual(json.loads(self.file.read_text()), self.journal.data)
        self.assertNotIn('env_vars', self.file.read_text())
        self.assertEqual(self.client.rollback_calls, [])

    def test_existing_plan_never_overwritten(self):
        before = self.file.read_bytes()
        with self.assertRaises(gate.GateError):
            publisher.prepare(self.env, self.root, self.file, self.client)
        self.assertEqual(before, self.file.read_bytes())

    def test_all_context_boundaries(self):
        for key, value in [('GITHUB_REPOSITORY', 'other/repo'), ('GITHUB_REF', 'refs/heads/topic'), ('GITHUB_EVENT_NAME', 'pull_request'),
                           ('GITHUB_SHA', 'bad'), ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_ACTIONS', 'false'), ('RUNNER_OS', 'Windows'),
                           ('GITHUB_WORKFLOW_REF', 'other'), ('OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED', '0'),
                           ('OUTPOST_PRODUCTION_WRITER_ENABLED', '0'), ('GITHUB_RUN_ID', 'bad')]:
            with self.subTest(key=key), self.assertRaises(gate.GateError):
                publisher.context({**self.env, key: value})

    def test_manual_dispatch_only_owner(self):
        self.assertEqual(publisher.context({**self.env, 'GITHUB_EVENT_NAME': 'workflow_dispatch'}), SHA)
        with self.assertRaises(gate.GateError):
            publisher.context({**self.env, 'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_ACTOR': 'other'})

    def test_prior_runs_even_without_metadata_block_new_plan(self):
        self.client.runs.append({**self.client.runs[0], 'id': 999})
        with self.assertRaises(gate.GateError):
            publisher.preflight(self.env, self.root, self.client)

    def test_missing_or_wrong_run_identity(self):
        for runs in [[], [{**self.client.runs[0], 'id': 999}], [{**self.client.runs[0], 'run_attempt': 2}],
                     [{**self.client.runs[0], 'head_sha': HEAD}], [{**self.client.runs[0], 'head_branch': 'staging'}]]:
            with self.subTest(runs=runs), self.assertRaises(gate.GateError):
                self.client.runs = runs
                publisher.preflight(self.env, self.root, self.client)

    def test_original_config_hash_required(self):
        with patch.object(gate, 'local_source', return_value=({}, '0' * 64)), self.assertRaises(gate.GateError):
            publisher.preflight(self.env, self.root, self.client)

    def test_release_hold_blocks(self):
        (self.root / '.release-hold').touch()
        with self.assertRaises(gate.GateError):
            publisher.preflight(self.env, self.root, self.client)

    def test_legacy_or_missing_health_blocks(self):
        for health in [{}, {**self.client.health_value, 'legacy_release_notifications_enabled': True},
                       {**self.client.health_value, 'confirmed_releases_enabled': False}]:
            self.client.health_value = health
            with self.subTest(health=health), self.assertRaises(gate.GateError):
                publisher.preflight(self.env, self.root, self.client)

    def test_no_pending_production_mutation(self):
        self.client.items[0]['latest_stage']['status'] = 'active'
        with self.assertRaises(gate.GateError):
            self.execute()
        self.assertEqual(self.journal.data['state'], 'prepared')

    def test_duplicate_inventory_identity_rejected(self):
        with self.assertRaises(gate.GateError):
            publisher.inventory_valid(self.client.items * 2)

    def test_failed_or_preview_baseline_rejected(self):
        for key, value in [('environment', 'preview'), ('latest_stage', {'status': 'failure'})]:
            changed = deepcopy(self.client.project)
            changed['canonical_deployment'][key] = value
            with self.subTest(key=key), self.assertRaises(gate.GateError):
                publisher.canonical(changed)

    def test_source_with_prior_deployment_blocks_plan(self):
        self.client.items[0]['deployment_trigger']['metadata']['commit_hash'] = SHA
        with self.assertRaises(gate.GateError):
            publisher.prepare(self.env, self.root, self.directory / 'another.json', self.client)

    def test_saved_artifact_before_upload_required(self):
        for receipt in ['', 'https://other.example/artifact', self.env['OUTPOST_SAVED_PLAN_URL'].replace('1234', '5555')]:
            self.env['OUTPOST_SAVED_PLAN_URL'] = receipt
            with self.subTest(receipt=receipt), self.assertRaises(gate.GateError):
                self.execute()
        self.assertEqual(self.journal.data['state'], 'prepared')

    def test_unrelated_rollout_after_plan_blocks_upload(self):
        unrelated = deepcopy(self.client.original)
        unrelated['id'] = OTHER
        self.client.items.append(unrelated)
        with self.assertRaises(gate.GateError):
            self.execute()

    def test_configuration_change_after_plan_blocks(self):
        self.client.project['extra_setting'] = True
        with self.assertRaises(gate.GateError):
            self.execute()

    def test_main_advanced_blocks_before_intent(self):
        self.client.main = HEAD
        with self.assertRaises(gate.GateError):
            self.execute()
        self.assertEqual(self.journal.data['state'], 'prepared')

    def test_single_upload_and_actual_metadata_success(self):
        self.assertEqual(self.execute(), NEW)
        self.assertEqual(self.journal.data['state'], 'deployment_success')
        self.assertEqual([e['state'] for e in self.journal.data['events']], ['prepared', 'upload_intent', 'upload_returned', 'deployment_success'])

    def test_intent_fsynced_before_uploader_called(self):
        def upload(*args):
            self.assertEqual(json.loads(self.file.read_text())['state'], 'upload_intent')
            return self.client.publish(*args)
        self.execute(upload)

    def test_repeated_upload_never_calls_uploader(self):
        self.execute()
        with self.assertRaises(gate.GateError):
            self.execute(lambda *_: self.fail('repeated upload'))

    def test_timeout_never_retried(self):
        calls = []
        def upload(*_):
            calls.append(1)
            raise TimeoutError()
        with self.assertRaises(gate.GateError):
            self.execute(upload)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.journal.data['state'], 'upload_unknown')
        with self.assertRaises(gate.GateError):
            self.execute(upload)
        self.assertEqual(len(calls), 1)

    def test_zero_exit_without_metadata_is_not_success(self):
        with self.assertRaises(gate.GateError):
            self.execute(lambda *_: 0)
        self.assertEqual(self.journal.data['state'], 'upload_unknown')

    def test_nonzero_exit_with_matching_success_readback(self):
        def upload(*args):
            self.client.publish(*args)
            return 1
        self.assertEqual(self.execute(upload), NEW)

    def test_pending_own_upload_waits_readonly_not_a_second_upload(self):
        self.client.publish()
        self.client.items[-1]['latest_stage']['status'] = 'active'
        def converge(_):
            self.client.items[-1]['latest_stage']['status'] = 'success'
        with patch.object(publisher.time, 'sleep', side_effect=converge):
            self.assertEqual(publisher.wait_for_publication(self.journal.data, self.client, 10), NEW)

    def test_failed_new_deployment_never_passes(self):
        def upload(*args):
            self.client.publish(*args)
            self.client.items[-1]['latest_stage']['status'] = 'failure'
            self.client.project['canonical_deployment'] = deepcopy(self.client.original)
            return 0
        with self.assertRaises(gate.GateError):
            self.execute(upload)
        self.assertEqual(self.journal.data['state'], 'upload_unknown')

    def test_active_unrelated_deployment_never_waited_or_canceled(self):
        self.client.publish()
        self.client.items[-1]['deployment_trigger']['metadata']['commit_hash'] = HEAD
        with patch.object(publisher.time, 'sleep', side_effect=AssertionError('must not wait for unrelated upload')), self.assertRaises(gate.GateError):
            publisher.wait_for_publication(self.journal.data, self.client, 10)

    def test_multiple_new_production_deployments_block(self):
        self.execute()
        other = deepcopy(self.client.items[-1])
        other['id'] = OTHER
        self.client.items.append(other)
        with self.assertRaises(gate.GateError):
            publisher.resolve(self.journal.data, self.client.project, self.client.items)

    def test_wrong_dirty_branch_or_source_blocks(self):
        self.execute()
        for key, value in [('commit_dirty', True), ('branch', 'staging'), ('commit_hash', HEAD)]:
            items = deepcopy(self.client.items)
            items[-1]['deployment_trigger']['metadata'][key] = value
            with self.subTest(key=key), self.assertRaises(gate.GateError):
                publisher.resolve(self.journal.data, self.client.project, items)

    def test_live_validation_all_commands_and_no_announcement(self):
        self.execute()
        commands = []
        self.live(lambda _, command: commands.append(command) or True)
        self.assertEqual(tuple(commands), publisher.LIVE_COMMANDS)
        self.assertEqual(self.journal.data['state'], 'live_pass')
        self.assertEqual(self.client.rollback_calls, [])

    def test_live_fails_closed_and_stops_following_commands(self):
        self.execute()
        commands = []
        with self.assertRaises(gate.GateError):
            self.live(lambda _, command: commands.append(command) or False)
        self.assertEqual(len(commands), 1)
        self.assertEqual(self.journal.data['state'], 'live_failed')

    def test_live_cannot_begin_on_unknown_upload(self):
        with self.assertRaises(gate.GateError):
            self.live()

    def test_failed_post_upload_proof_marks_live_failure_before_any_page_get(self):
        self.execute()
        with patch.object(gate, 'verify_current', side_effect=gate.GateError('broken_health')), self.assertRaises(gate.GateError):
            publisher.verify_live(self.env, self.root, self.journal, self.client, lambda *_: self.fail('no premature live page GET'))
        self.assertEqual(self.journal.data['state'], 'live_failed')
        self.client.health_value = {}
        publisher.rollback(self.env, self.root, self.journal, self.client)
        self.assertEqual(self.journal.data['state'], 'rolled_back')

    def test_rollback_only_after_live_failure(self):
        self.execute()
        with self.assertRaises(gate.GateError):
            publisher.rollback(self.env, self.root, self.journal, self.client)

    def test_rollback_activation_required(self):
        self.fail_live()
        with self.assertRaises(gate.GateError):
            publisher.rollback({**self.env, 'OUTPOST_PRODUCTION_ROLLBACK_ENABLED': '0'}, self.root, self.journal, self.client)

    def test_rollback_to_saved_successful_baseline(self):
        self.fail_live()
        publisher.rollback(self.env, self.root, self.journal, self.client)
        self.assertEqual(self.client.rollback_calls, [OLD])
        self.assertEqual(self.journal.data['state'], 'rolled_back')
        self.assertEqual(self.client.project['canonical_deployment']['id'], OLD)

    def test_broken_current_health_does_not_block_code_rollback(self):
        self.fail_live()
        self.client.health_value = {}
        publisher.rollback(self.env, self.root, self.journal, self.client)
        self.assertEqual(self.journal.data['state'], 'rolled_back')

    def test_repeated_rollback_never_sends_second_post(self):
        self.fail_live()
        publisher.rollback(self.env, self.root, self.journal, self.client)
        with self.assertRaises(gate.GateError):
            publisher.rollback(self.env, self.root, self.journal, self.client)
        self.assertEqual(len(self.client.rollback_calls), 1)

    def test_rollback_unknown_requires_inspection_not_retry(self):
        self.fail_live()
        def ambiguous(_):
            raise TimeoutError()
        with patch.object(self.client, 'rollback', side_effect=ambiguous), self.assertRaises(gate.GateError):
            publisher.rollback(self.env, self.root, self.journal, self.client)
        self.assertEqual(self.journal.data['state'], 'rollback_unknown')
        with self.assertRaises(gate.GateError):
            publisher.rollback(self.env, self.root, self.journal, self.client)

    def test_rollback_will_not_overwrite_other_rollout(self):
        self.fail_live()
        other = deepcopy(self.client.items[-1])
        other['id'] = OTHER
        self.client.items.append(other)
        self.client.project['canonical_deployment'] = other
        with self.assertRaises(gate.GateError):
            publisher.rollback(self.env, self.root, self.journal, self.client)
        self.assertEqual(self.client.rollback_calls, [])

    def test_rollback_target_environment_and_version_must_match(self):
        self.fail_live()
        self.client.original['environment'] = 'preview'
        with self.assertRaises(gate.GateError):
            publisher.rollback(self.env, self.root, self.journal, self.client)
        self.assertEqual(self.client.rollback_calls, [])

    def test_journal_extra_fields_or_foreign_source_rejected(self):
        for changed in [{**self.journal.data, 'token': 'not-secret'}, {**self.journal.data, 'source_sha': HEAD},
                        {**self.journal.data, 'run_id': '999'}, {**self.journal.data, 'baseline_id': 'bad'}]:
            with self.subTest(changed=changed), self.assertRaises(gate.GateError):
                publisher.validate_journal(changed, self.env)

    def test_nested_private_or_replayed_journal_rejected(self):
        for mutate in [lambda data: data['review'].update(token='not-secret'),
                       lambda data: data['events'][0].update(token='not-secret'),
                       lambda data: data['events'].extend([{'state': 'upload_intent', 'at': 'now'}] * 2)]:
            changed = deepcopy(self.journal.data)
            mutate(changed)
            with self.assertRaises(gate.GateError):
                publisher.validate_journal(changed, self.env)

    def test_state_inside_checkout_rejected(self):
        with self.assertRaises(gate.GateError):
            publisher.external_path(self.root, self.root / 'journal.json')

    def test_upload_changed_missing_config_and_extra_files_rejected(self):
        self.package.mkdir()
        (self.package / 'site').mkdir()
        (self.package / 'site/demo.html').write_bytes(b'demo')
        config = (gate.ROOT / 'wrangler.jsonc').read_bytes()
        (self.package / 'wrangler.jsonc').write_bytes(config)
        expected = publisher.digest([{'path': 'site/demo.html', 'bytes': 4, 'sha256': publisher.digest(b'demo')}])
        publisher.verify_package(self.package, expected)
        (self.package / 'extra.txt').touch()
        with self.assertRaises(gate.GateError):
            publisher.verify_package(self.package, expected)
        (self.package / 'extra.txt').unlink()
        (self.package / 'site/demo.html').write_bytes(b'changed')
        with self.assertRaises(gate.GateError):
            publisher.verify_package(self.package, expected)
        (self.package / 'wrangler.jsonc').unlink()
        with self.assertRaises(gate.GateError):
            publisher.verify_package(self.package, expected)

    def test_default_is_offline_and_does_not_get_clients(self):
        with patch('sys.argv', ['production_publisher.py']), patch.object(publisher, 'Clients', side_effect=AssertionError('network client created')):
            self.assertEqual(publisher.main(), 0)

    def test_readonly_ci_auth_does_not_broaden_metadata_allowlist(self):
        client = gate.ReadOnlyClients({'CLOUDFLARE_ACCOUNT_ID': 'd' * 32, 'CLOUDFLARE_API_TOKEN': 'synthetic-pages', 'GITHUB_TOKEN': 'synthetic-readonly'})
        with patch.object(client, '_json', return_value={}) as request:
            client.github('/git/ref/heads/main')
            self.assertEqual(request.call_args.args[1]['Authorization'], 'Bearer synthetic-readonly')
            with self.assertRaises(gate.GateError):
                client.github('/actions/secrets')
            self.assertEqual(request.call_count, 1)

if __name__ == '__main__':
    unittest.main()
