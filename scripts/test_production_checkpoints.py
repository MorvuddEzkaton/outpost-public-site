"""Offline regressions: expiry is safe only for immutable reviewed evidence."""
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import production_checkpoints as checkpoints
import production_deployment_gate as gate
import production_history as history
import production_publisher as publisher
import verify_production_checkpoints as cli
import test_production_history as history_tests
from verify_production_publisher_workflow import verify_checkpoints, ROOT

VALIDATOR = publisher.validate_journal_evidence


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.fixture = history_tests.HistoryTests()
        self.fixture.setUp()
        self.fixture.checkpoint_patch.stop()
        self.addCleanup(self.fixture.doCleanups)
        self.client, self.env = self.fixture.client, self.fixture.env
        self.first = self.client.publication_runs()[0]
        self.value = checkpoints.genesis()
        for run in (self.first, self.fixture.prior):
            self.add_record(run)

    def add_record(self, run):
        evidence = history.read_resolved_record(self.client, run, self.env, publisher.validate_journal)
        previous = self.value['records'][-1]['record_sha256'] if self.value['records'] else checkpoints.ZERO
        self.value['records'].append(checkpoints.seal(evidence, previous))

    def reseal(self, value):
        previous = checkpoints.ZERO
        for index, record in enumerate(value['records']):
            value['records'][index] = checkpoints.seal(checkpoints.body(record), previous)
            previous = value['records'][index]['record_sha256']
        return value

    def test_empty_genesis_valid(self):
        checkpoints.validate(checkpoints.genesis(), VALIDATOR)

    def test_resolved_prepared_and_skipped_valid(self):
        self.assertEqual(checkpoints.validate(self.value, VALIDATOR), self.value)

    def test_live_pass_and_rollback_can_be_preserved(self):
        for state, conclusion in [('live_pass', 'success'), ('rolled_back', 'failure')]:
            self.fixture.prior['conclusion'] = conclusion
            self.fixture.set_result(state)
            self.value['records'] = self.value['records'][:1]
            self.add_record(self.fixture.prior)
            checkpoints.validate(self.value, VALIDATOR)

    def test_all_unknown_or_intermediate_states_cannot_be_preserved(self):
        for state in ('upload_intent', 'upload_returned', 'upload_unknown', 'deployment_success',
                      'live_intent', 'live_failed', 'rollback_intent', 'rollback_unknown'):
            self.fixture.set_result(state)
            value = deepcopy(self.value)
            value['records'][1]['proof'][1]['journal'] = self.fixture.result
            with self.subTest(state=state), self.assertRaises(gate.GateError):
                checkpoints.validate(self.reseal(value), VALIDATOR)

    def test_no_extra_data_logs_tokens_or_actor_fields(self):
        for place in ('header', 'record', 'run', 'artifact', 'journal', 'job'):
            value = deepcopy(self.value)
            target = {'header': value, 'record': value['records'][1], 'run': value['records'][1]['run'],
                      'artifact': value['records'][1]['proof'][0], 'journal': value['records'][1]['proof'][0]['journal'],
                      'job': value['records'][0]['proof']}[place]
            target['unreviewed_data'] = 'not permitted'
            with self.subTest(place=place), self.assertRaises(gate.GateError):
                checkpoints.validate(self.reseal(value), VALIDATOR)

    def test_changed_hash_or_chain_fails(self):
        for field in ('previous_sha256', 'record_sha256'):
            value = deepcopy(self.value)
            value['records'][1][field] = 'f' * 64
            with self.subTest(field=field), self.assertRaises(gate.GateError):
                checkpoints.validate(value, VALIDATOR)

    def test_missing_duplicate_or_reordered_run_fails(self):
        for rows in [self.value['records'][1:], self.value['records'] * 2, list(reversed(self.value['records']))]:
            with self.subTest(rows=len(rows)), self.assertRaises(gate.GateError):
                checkpoints.validate(self.reseal({**self.value, 'records': deepcopy(rows)}), VALIDATOR)

    def test_foreign_identity_rerun_nonmain_bad_status_fails(self):
        for field, val in [('id', True), ('run_number', True), ('run_attempt', 2), ('workflow_id', 999),
                           ('head_branch', 'other'), ('head_sha', 'f' * 40), ('status', 'in_progress'), ('conclusion', None)]:
            value = deepcopy(self.value)
            value['records'][0]['run'][field] = val
            with self.subTest(field=field), self.assertRaises(gate.GateError):
                checkpoints.validate(self.reseal(value), VALIDATOR)

    def test_executed_job_cannot_be_skipped_proof(self):
        for field, val in [('steps', [{'name': 'upload'}]), ('runner_id', 5), ('runner_id', False),
                           ('runner_name', 'runner'), ('conclusion', 'success')]:
            value = deepcopy(self.value)
            value['records'][0]['proof'][field] = val
            with self.subTest(field=field), self.assertRaises(gate.GateError):
                checkpoints.validate(self.reseal(value), VALIDATOR)

    def test_journal_from_another_run_or_modified_intent_fails(self):
        for kind in ('source', 'link', 'artifact'):
            value = deepcopy(self.value)
            proof = value['records'][1]['proof']
            if kind == 'source':
                proof[1]['journal']['source_sha'] = 'f' * 40
            elif kind == 'link':
                proof[1]['journal']['package_sha256'] = 'f' * 64
            else:
                proof[1]['workflow_run']['repository_id'] = 123
            with self.subTest(kind=kind), self.assertRaises(gate.GateError):
                checkpoints.validate(self.reseal(value), VALIDATOR)

    def test_cancelled_unstarted_provider_proof_can_be_preserved_without_relabeling(self):
        value = deepcopy(self.value)
        record = value['records'][0]
        record['run']['conclusion'] = 'cancelled'
        record['proof']['conclusion'] = 'cancelled'
        checkpoints.validate(self.reseal(value), VALIDATOR)
        self.assertEqual(value['records'][0]['proof']['conclusion'], 'cancelled')
        for field, val in [('steps', [{'name': 'Set up job'}]), ('runner_id', 5),
                           ('runner_id', False), ('runner_name', 'runner')]:
            changed = deepcopy(value)
            changed['records'][0]['proof'][field] = val
            with self.subTest(field=field), self.assertRaises(gate.GateError):
                checkpoints.validate(self.reseal(changed), VALIDATOR)
        value['records'][0]['run']['conclusion'] = 'success'
        with self.assertRaises(gate.GateError):
            checkpoints.validate(self.reseal(value), VALIDATOR)

    def test_deleted_or_changed_past_rows_are_not_append_only(self):
        for change in (checkpoints.genesis(), {**self.value, 'records': self.value['records'][:1]}):
            with self.assertRaises(gate.GateError):
                checkpoints.append_only(self.value, change)
        changed = deepcopy(self.value)
        changed['records'][0]['run']['conclusion'] = 'failure'
        with self.assertRaises(gate.GateError):
            checkpoints.append_only(self.value, self.reseal(changed))

    def test_duplicate_json_keys_and_oversized_input_rejected(self):
        for raw in (b'{"schema":1,"schema":1}', b'x' * (checkpoints.MAX_BYTES + 1), b'not json'):
            with self.assertRaises(gate.GateError):
                checkpoints.parse(raw)

    def test_existing_records_need_no_provider_reads(self):
        client = Mock()
        self.assertEqual(checkpoints.verify_new(client, self.value, self.value, VALIDATOR), 0)
        self.assertEqual(client.mock_calls, [])

    def test_new_records_need_matching_live_provider_evidence(self):
        self.assertEqual(checkpoints.verify_new(self.client, checkpoints.genesis(), self.value, VALIDATOR), 2)

    def test_forged_safe_looking_record_cannot_be_added(self):
        value = deepcopy(self.value)
        value['records'][1]['proof'][0]['digest'] = 'sha256:' + 'a' * 64
        with self.assertRaises(gate.GateError):
            checkpoints.verify_new(self.client, checkpoints.genesis(), self.reseal(value), VALIDATOR)

    def test_expired_artifacts_cannot_be_added(self):
        self.client.records[self.fixture.prior['id']][0]['expired'] = True
        with self.assertRaises(gate.GateError):
            checkpoints.verify_new(self.client, checkpoints.genesis(), self.value, VALIDATOR)

    def test_saved_records_survive_artifact_expiry(self):
        self.client.publication_artifacts = Mock(side_effect=AssertionError('archived evidence must not fetch expired artifacts'))
        history.assert_clear(self.client, self.env, publisher.validate_journal, self.value['records'])

    def test_saved_prefix_survives_workflow_run_retention(self):
        self.client.publication_runs = Mock(return_value=[self.client.runs[-1]])
        history.assert_clear(self.client, self.env, publisher.validate_journal, self.value['records'])

    def test_absent_unarchived_run_still_blocks(self):
        self.client.publication_runs = Mock(return_value=[self.client.runs[-1]])
        with self.assertRaises(gate.GateError):
            history.assert_clear(self.client, self.env, publisher.validate_journal, self.value['records'][:1])

    def test_live_rerun_or_identity_drift_of_archived_record_blocks(self):
        for field, val in [('run_attempt', 2), ('head_sha', 'f' * 40), ('conclusion', 'success')]:
            prior = deepcopy(self.fixture.prior)
            prior[field] = val
            self.client.runs = [prior, self.client.runs[-1]]
            with self.subTest(field=field), self.assertRaises(gate.GateError):
                history.assert_clear(self.client, self.env, publisher.validate_journal, self.value['records'])

    def test_archived_source_replay_still_blocks(self):
        self.client.runs[-1]['head_sha'] = self.fixture.prior['head_sha']
        env = {**self.env, 'GITHUB_SHA': self.fixture.prior['head_sha']}
        with self.assertRaises(gate.GateError):
            history.assert_clear(self.client, env, publisher.validate_journal, self.value['records'])

    def test_unresolved_newer_run_is_not_hidden_by_checkpoint(self):
        self.fixture.set_result('upload_unknown')
        with self.assertRaises(gate.GateError):
            history.assert_clear(self.client, self.env, publisher.validate_journal, self.value['records'][:1])

    def test_capture_rejects_running_or_unknown_attempt(self):
        with self.assertRaises(gate.GateError):
            cli.capture(self.client, checkpoints.genesis())
        self.fixture.set_result('upload_unknown')
        with self.assertRaises(gate.GateError):
            cli.capture(self.client, checkpoints.genesis())

    def test_capture_emits_safe_complete_prefix_only(self):
        self.client.publication_runs = Mock(return_value=[self.first, self.fixture.prior])
        result = cli.capture(self.client, checkpoints.genesis())
        self.assertEqual(result, self.value)
        self.assertNotIn('archive_download_url', json.dumps(result))

    def test_checkpoint_failure_stops_publisher_before_upload(self):
        with patch.object(publisher.checkpoints, 'load_checked', side_effect=gate.GateError('corrupted_checkpoint')):
            with self.assertRaises(gate.GateError):
                self.fixture.execute(lambda *_: self.fail('must not upload'))


class GitCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / checkpoints.PATH
        self.file.parent.mkdir()
        for args in [('init', '-q'), ('config', 'user.name', 'Offline Test'),
                     ('config', 'user.email', 'offline-test@example.invalid')]:
            self.git(*args)
        self.commit(checkpoints.genesis())

    def git(self, *args):
        return subprocess.check_output(['git', '-c', 'commit.gpgsign=false', '-c', 'core.autocrlf=false', *args],
                                       cwd=self.root, stderr=subprocess.DEVNULL).decode().strip()

    def commit(self, value):
        self.file.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
        self.git('add', checkpoints.PATH)
        self.git('commit', '-qm', 'offline checkpoint fixture')
        return self.git('rev-parse', 'HEAD')

    def load(self):
        return checkpoints.load_checked(self.root, self.git('rev-parse', 'HEAD'), VALIDATOR)

    def test_exact_genesis_and_full_git_history(self):
        self.assertEqual(self.load(), [])

    def test_modified_worktree_bytes_rejected(self):
        self.file.write_text('{}', encoding='utf-8')
        with self.assertRaises(gate.GateError):
            self.load()

    def test_deleted_or_missing_checkpoint_rejected(self):
        self.file.unlink()
        with self.assertRaises(gate.GateError):
            self.load()

    def test_shallow_checkout_rejected(self):
        (self.root / '.git/shallow').write_text(self.git('rev-parse', 'HEAD') + '\n', encoding='utf-8')
        with self.assertRaises(gate.GateError):
            self.load()

    def test_append_then_reset_cannot_hide_past_record(self):
        fixture = CheckpointTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.commit(fixture.value)
        self.assertEqual(self.load(), fixture.value['records'])
        self.commit(checkpoints.genesis())
        with self.assertRaises(gate.GateError):
            self.load()

    def test_old_revision_with_new_worktree_rejected(self):
        old = self.git('rev-parse', 'HEAD')
        fixture = CheckpointTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.commit(fixture.value)
        with self.assertRaises(gate.GateError):
            checkpoints.load_checked(self.root, old, VALIDATOR)

    def test_default_cli_never_uses_token_or_network(self):
        factory = Mock(side_effect=AssertionError('no network in default mode'))
        with patch('sys.stdout', new=io.StringIO()):
            self.assertEqual(cli.main([], {'GITHUB_TOKEN': 'unused'}, self.root, factory), 0)
        factory.assert_not_called()

    def test_zero_new_records_ci_mode_also_needs_no_token_or_network(self):
        factory = Mock(side_effect=AssertionError('no network for empty genesis'))
        with patch('sys.stdout', new=io.StringIO()):
            self.assertEqual(cli.main(['--check-new'], {'CHECKPOINT_BASE_SHA': self.git('rev-parse', 'HEAD')}, self.root, factory), 0)
        factory.assert_not_called()

    def test_bad_base_and_capture_output_cannot_write(self):
        for argv, env in [(['--check-new'], {}), (['--capture', '--output', str(self.root / 'unsafe.json')], {}),
                          (['--output', str(self.root / 'unsafe.json')], {})]:
            with self.subTest(argv=argv), patch('sys.stdout', new=io.StringIO()):
                self.assertEqual(cli.main(argv, env, self.root, Mock()), 1)
        self.assertFalse((self.root / 'unsafe.json').exists())


class CheckpointWorkflowTests(unittest.TestCase):
    def test_provider_verification_wiring(self):
        text = (ROOT / '.github/workflows/public-repository-security.yml').read_text()
        self.assertEqual(verify_checkpoints(text), [])
        for marker in ('actions: read', 'fetch-depth: 0', 'persist-credentials: false',
                       'CHECKPOINT_BASE_SHA: ${{ github.event.pull_request.base.sha || github.sha }}',
                       'GITHUB_TOKEN: ${{ github.token }}', '--check-new'):
            with self.subTest(marker=marker):
                self.assertTrue(verify_checkpoints(text.replace(marker, 'REMOVED')))

    def test_checkpoint_check_is_readonly_not_a_publisher(self):
        text = (ROOT / '.github/workflows/public-repository-security.yml').read_text()
        for bypass in ('contents: write', 'actions: write', 'secrets.CLOUDFLARE_API_TOKEN',
                       'continue-on-error: true', 'workflow_run:', 'schedule:', '--capture', '|| true'):
            with self.subTest(bypass=bypass):
                self.assertTrue(verify_checkpoints(text + '\n' + bypass))


if __name__ == '__main__':
    unittest.main()
