"""Offline quarantine regressions: different SHAs, missing evidence and ZIP safety."""
from copy import deepcopy
from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from urllib.error import HTTPError
from zipfile import ZipFile, ZipInfo
import production_deployment_gate as gate
import production_publisher as publisher
import production_history as history
from test_production_publisher import FakeClient, env, SHA, NEW


def zipped(value, names=None):
    stream = BytesIO()
    with ZipFile(stream, 'w') as archive:
        for name in names or [history.JOURNAL_NAME]:
            archive.writestr(name, value if isinstance(value, str) else json.dumps(value))
    return stream.getvalue()


class HistoryClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.records, self.archives = {}, {}

    def publication_artifacts(self, run):
        return deepcopy(self.records.get(run['id'], []))

    def publication_journal(self, artifact):
        return history.archive_journal(self.archives[artifact['id']], artifact)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / 'checkout'
        self.root.mkdir()
        self.env = env()
        self.client = HistoryClient()
        checkpoint_patch = patch.object(publisher.checkpoints, 'load_checked', return_value=[])
        checkpoint_patch.start()
        self.addCleanup(checkpoint_patch.stop)
        self.checkpoint_patch = checkpoint_patch
        config = json.loads((gate.ROOT / 'wrangler.jsonc').read_text())
        for target, value in [(gate, ('local_source', (config, publisher.APPROVED_CONFIG_HASH))),
                              (publisher, ('manifest', [{'path': 'site/demo.html', 'bytes': 4, 'sha256': 'd' * 64}]))]:
            change = patch.object(target, value[0], return_value=value[1])
            change.start()
            self.addCleanup(change.stop)
        self.journal = publisher.prepare(self.env, self.root, self.directory / 'journal.json', self.client)
        self.prior = {**self.client.runs[0], 'id': 1200, 'run_number': 2, 'head_sha': 'd' * 40,
                      'status': 'completed', 'conclusion': 'failure'}
        self.client.runs = [self.prior, {**self.client.runs[0], 'run_number': 3}]
        self.env['GITHUB_RUN_NUMBER'] = '3'
        self.intent = {**deepcopy(self.journal.data), 'run_id': '1200', 'source_sha': 'd' * 40}
        self.set_result('prepared')

    def set_result(self, state):
        chains = {
            'prepared': [], 'upload_intent': ['upload_intent'],
            'upload_returned': ['upload_intent', 'upload_returned'],
            'upload_unknown': ['upload_intent', 'upload_unknown'],
            'deployment_success': ['upload_intent', 'upload_returned', 'deployment_success'],
        }
        deployed = chains['deployment_success']
        chains.update({'live_intent': deployed + ['live_intent'],
                       'live_failed': deployed + ['live_intent', 'live_failed'],
                       'live_pass': deployed + ['live_intent', 'live_pass']})
        for suffix in ('rollback_intent', 'rollback_unknown', 'rolled_back'):
            chains[suffix] = chains['live_failed'] + ['rollback_intent'] + ([] if suffix == 'rollback_intent' else [suffix])
        result = deepcopy(self.intent)
        for item in chains[state]:
            event = {'at': publisher.now(), 'state': item}
            if item == 'upload_returned':
                event['command_returned'] = True
            if item in ('deployment_success', 'live_failed', 'live_pass'):
                event['deployment_id'] = NEW
            result['events'].append(event)
        result['state'] = state
        self.result = result
        self.write_records()

    def write_records(self):
        records = []
        for identity, kind, data in [(9001, 'intent', self.intent), (9002, 'result', self.result)]:
            payload = zipped(data)
            self.client.archives[identity] = payload
            records.append({'id': identity, 'name': history.artifact_name(kind, self.prior), 'expired': False,
                            'size_in_bytes': len(payload), 'digest': 'sha256:' + hashlib.sha256(payload).hexdigest(),
                            'workflow_run': {'id': self.prior['id'], 'head_sha': self.prior['head_sha'],
                                             'head_branch': 'main', 'repository_id': history.REPOSITORY_ID,
                                             'head_repository_id': history.REPOSITORY_ID}})
        self.client.records[self.prior['id']] = records

    def clear(self):
        history.assert_clear(self.client, self.env, publisher.validate_historical_journal)

    def execute(self, uploader):
        with patch.object(publisher, 'tool', return_value=Path('/pinned/wrangler.js')), \
                patch.object(publisher, 'upload_package'), patch.object(publisher, 'verify_package'):
            publisher.execute(self.env, self.root, self.journal, self.directory / 'upload', self.client, uploader)

    def test_different_source_prepared_without_upload_is_safe(self):
        self.clear()
        self.assertNotEqual(self.intent['source_sha'], self.env['GITHUB_SHA'])

    def test_reviewed_legacy_config_history_is_preserved_without_replay(self):
        self.intent['configuration_sha256'] = publisher.LEGACY_CONFIG_HASH
        self.set_result('prepared')
        publisher.history_clear(self.client, self.env, self.root)
        self.set_result('upload_unknown')
        with self.assertRaises(gate.GateError):
            self.execute(lambda *_: self.fail('legacy unresolved evidence must still block'))
        self.assertEqual(self.journal.data['state'], 'prepared')

    def test_accepted_previous_live_pass_is_safe(self):
        self.prior['conclusion'] = 'success'
        self.set_result('live_pass')
        self.clear()

    def test_resolved_rollback_is_safe_but_previous_workflow_remains_failure(self):
        self.set_result('rolled_back')
        self.clear()
        self.assertEqual(self.prior['conclusion'], 'failure')

    def test_all_unresolved_prior_states_block_other_source_before_upload(self):
        for state in ('upload_intent', 'upload_returned', 'upload_unknown', 'deployment_success',
                      'live_intent', 'live_failed', 'rollback_intent', 'rollback_unknown'):
            self.set_result(state)
            with self.subTest(state=state), self.assertRaises(gate.GateError):
                self.execute(lambda *_: self.fail('must not upload after an unresolved older SHA'))
            self.assertEqual(self.journal.data['state'], 'prepared')

    def test_unresolved_history_blocks_plan_creation(self):
        self.set_result('upload_unknown')
        file = self.directory / 'another.json'
        with self.assertRaises(gate.GateError):
            publisher.prepare(self.env, self.root, file, self.client)
        self.assertFalse(file.exists())

    def test_older_unknown_is_not_hidden_by_a_newer_skipped_run(self):
        self.set_result('upload_unknown')
        newer = {**deepcopy(self.prior), 'id': 1220, 'run_number': 3, 'head_sha': 'e' * 40}
        self.client.runs = [self.prior, newer, {**self.client.runs[-1], 'run_number': 4}]
        self.env['GITHUB_RUN_NUMBER'] = '4'
        with self.assertRaises(gate.GateError):
            self.clear()

    def test_unresolved_history_blocks_rollback_post(self):
        self.set_result('upload_unknown')
        for state, details in [('upload_intent', {}), ('upload_returned', {'command_returned': True}),
                               ('deployment_success', {'deployment_id': NEW}), ('live_intent', {}),
                               ('live_failed', {'deployment_id': NEW})]:
            self.journal.event(state, **details)
        with self.assertRaises(gate.GateError):
            publisher.rollback(self.env, self.root, self.journal, self.client)
        self.assertEqual(self.client.rollback_calls, [])

    def test_last_read_catches_history_change_after_initial_preflight(self):
        original = self.client.publication_runs
        reads = []
        def changed():
            reads.append(1)
            if len(reads) == 2:
                self.set_result('upload_unknown')
            return original()
        with patch.object(self.client, 'publication_runs', side_effect=changed), self.assertRaises(gate.GateError):
            self.execute(lambda *_: self.fail('must recheck before upload intent'))
        self.assertEqual(len(reads), 2)
        self.assertEqual(self.journal.data['state'], 'prepared')

    def test_missing_one_or_both_journals_does_not_mean_success(self):
        original = deepcopy(self.client.records[self.prior['id']])
        for rows in (original[:1], original[1:], []):
            self.client.records[self.prior['id']] = rows
            if not rows:
                job = self.client.skipped_publication_jobs(self.prior)
                job[2].update(conclusion='failure', steps=[{'name': 'upload'}], runner_id=100)
                self.client.skipped_publication_jobs = lambda _: job
            with self.subTest(count=len(rows)), self.assertRaises(gate.GateError):
                self.clear()

    def test_expired_tampered_foreign_or_duplicate_artifact_blocks(self):
        original = deepcopy(self.client.records[self.prior['id']])
        for mutate in (lambda row: row.update(expired=True), lambda row: row.update(digest='sha256:' + '0' * 64),
                       lambda row: row.update(size_in_bytes=history.MAX_ARCHIVE + 1),
                       lambda row: row['workflow_run'].update(id=1234),
                       lambda row: row['workflow_run'].update(head_repository_id=999),
                       lambda row: row.update(name='unrelated-journal'), lambda row: row.update(id=9001)):
            self.client.records[self.prior['id']] = deepcopy(original)
            mutate(self.client.records[self.prior['id']][1])
            with self.subTest(mutation=mutate), self.assertRaises(gate.GateError):
                self.clear()

    def test_missing_history_or_anchor_replacement_blocks(self):
        runs = self.client.publication_runs()
        for changed in (runs[1:], [*runs, runs[0]], [dict(runs[0], id=999), *runs[1:]],
                        [dict(runs[0], head_sha=SHA), *runs[1:]], [dict(runs[0], run_number=9), *runs[1:]]):
            with self.subTest(runs=changed), patch.object(self.client, 'publication_runs', return_value=changed), self.assertRaises(gate.GateError):
                self.clear()

    def test_rerun_foreign_repository_workflow_or_current_identity_blocks(self):
        runs = self.client.publication_runs()
        for key, value in [('run_attempt', 2), ('workflow_id', 999), ('path', '.github/workflows/other.yml'),
                           ('repository', {'id': 999}), ('head_repository', {'id': 999}), ('event', 'pull_request')]:
            changed = deepcopy(runs)
            changed[1][key] = value
            with self.subTest(key=key), patch.object(self.client, 'publication_runs', return_value=changed), self.assertRaises(gate.GateError):
                self.clear()
        for key, value in [('GITHUB_RUN_NUMBER', '4'), ('GITHUB_RUN_ID', '999'), ('GITHUB_SHA', 'f' * 40)]:
            with self.subTest(key=key), self.assertRaises(gate.GateError):
                history.assert_clear(self.client, {**self.env, key: value}, publisher.validate_journal)

    def test_any_same_source_previous_run_remains_replay_blocked(self):
        self.prior['head_sha'] = SHA
        with self.assertRaises(gate.GateError):
            self.clear()

    def test_incomplete_previous_run_blocks_even_if_artifact_looks_terminal(self):
        self.set_result('rolled_back')
        self.prior['status'] = 'in_progress'
        with self.assertRaises(gate.GateError):
            self.clear()

    def test_skipped_publisher_needs_actual_empty_job_proof(self):
        self.client.records[self.prior['id']] = []
        self.clear()
        original = self.client.skipped_publication_jobs(self.prior)
        for key, value in [('conclusion', 'success'), ('steps', [{'name': 'upload'}]), ('runner_id', 100),
                           ('run_attempt', 2), ('head_sha', SHA), ('run_id', 999)]:
            jobs = deepcopy(original)
            jobs[2][key] = value
            with self.subTest(key=key), patch.object(self.client, 'skipped_publication_jobs', return_value=jobs), self.assertRaises(gate.GateError):
                self.clear()

    def test_exact_readonly_plan_failure_can_be_proven_without_artifact(self):
        self.prior['conclusion'] = 'failure'
        self.client.records[self.prior['id']] = []
        jobs = self.client.skipped_publication_jobs(self.prior)
        for job in jobs:
            job['conclusion'] = 'failure' if job['name'] == 'publish' else 'success'
        publish = next(job for job in jobs if job['name'] == 'publish')
        names = ['Set up job', 'Checkout', 'Set up Python', 'Set up Node',
                 'Install tool', 'Verify Telegram transport in the actual offline edge runtime']
        names += [history.PREFLIGHT_STEPS[i][0] for i in range(7, 14)]
        publish['steps'] = [{'number': i, 'name': name, 'status': 'completed',
                             'conclusion': 'success' if i <= 6 else history.PREFLIGHT_STEPS[i][1]}
                            for i, name in enumerate(names, 1)]
        with self.prior_jobs(jobs):
            self.clear()
            record = history.read_resolved_record(self.client, self.prior, self.env, publisher.validate_journal)
            self.assertEqual(record['kind'], 'preflight_failed')
            self.assertEqual(record['proof']['steps'][8]['conclusion'], 'skipped')
            for number, status in ((7, 'success'), (8, 'success'), (9, 'failure'),
                                   (10, 'success'), (12, 'success')):
                mutated = deepcopy(jobs)
                target = next(job for job in mutated if job['name'] == 'publish')
                target['steps'][number - 1]['conclusion'] = status
                with self.subTest(number=number), self.prior_jobs(mutated), self.assertRaises(gate.GateError):
                    self.clear()
            wrong = deepcopy(jobs)
            next(job for job in wrong if job['name'] == 'publish')['steps'] = publish['steps'][:9]
            with self.prior_jobs(wrong), self.assertRaises(gate.GateError):
                self.clear()
            wrong = deepcopy(jobs)
            next(job for job in wrong if job['name'] == 'browser-quality')['conclusion'] = 'failure'
            with self.prior_jobs(wrong), self.assertRaises(gate.GateError):
                self.clear()

    def test_result_must_link_exactly_to_original_intent(self):
        self.result['package_sha256'] = '1' * 64
        self.write_records()
        with self.assertRaises(gate.GateError):
            self.clear()

    def test_cancelled_environment_wait_without_runner_is_not_an_upload(self):
        self.prior['conclusion'] = 'cancelled'
        self.client.records[self.prior['id']] = []
        jobs = self.client.skipped_publication_jobs(self.prior)
        jobs[2].update(conclusion='cancelled', steps=[], runner_id=None, runner_name=None)
        with self.prior_jobs(jobs):
            self.clear()

    def prior_jobs(self, jobs):
        original = self.client.skipped_publication_jobs
        return patch.object(self.client, 'skipped_publication_jobs',
                            side_effect=lambda run: deepcopy(jobs) if run['id'] == self.prior['id'] else original(run))

    def test_cancelled_job_with_any_execution_evidence_still_blocks_upload(self):
        self.prior['conclusion'] = 'cancelled'
        self.client.records[self.prior['id']] = []
        original = self.client.skipped_publication_jobs(self.prior)
        original[2].update(conclusion='cancelled', steps=[], runner_id=None, runner_name=None)
        for field, value in [('steps', [{'name': 'Set up job'}]), ('runner_id', 5),
                             ('runner_id', False), ('runner_name', 'runner'), ('status', 'in_progress'),
                             ('run_attempt', 2), ('head_sha', SHA), ('run_id', 999)]:
            jobs = deepcopy(original)
            jobs[2][field] = value
            with self.subTest(field=field), self.prior_jobs(jobs), self.assertRaises(gate.GateError):
                self.execute(lambda *_: self.fail('must not upload after an executed or unproven cancellation'))
            self.assertEqual(self.journal.data['state'], 'prepared')
        self.prior['conclusion'] = 'success'
        with self.prior_jobs(original), self.assertRaises(gate.GateError):
            self.clear()

    def test_cancelled_empty_job_cannot_hide_an_existing_unknown_upload(self):
        self.prior['conclusion'] = 'cancelled'
        self.set_result('upload_unknown')
        jobs = self.client.skipped_publication_jobs(self.prior)
        jobs[2].update(conclusion='cancelled', steps=[], runner_id=None, runner_name=None)
        with self.prior_jobs(jobs), self.assertRaises(gate.GateError):
            self.execute(lambda *_: self.fail('a cancelled result must not hide an unknown upload'))

    def test_intent_cannot_itself_be_an_upload_or_contain_a_foreign_source(self):
        original = deepcopy(self.intent)
        for mutate in (lambda row: row.update(source_sha=SHA), lambda row: row.update(run_id='1234'),
                       lambda row: row.update(state='upload_intent', events=[*row['events'],
                           {'at': publisher.now(), 'state': 'upload_intent'}])):
            self.intent = deepcopy(original)
            mutate(self.intent)
            self.write_records()
            with self.subTest(mutate=mutate), self.assertRaises(gate.GateError):
                self.clear()

    def test_terminal_journal_cannot_fake_event_details_or_deployment_identity(self):
        self.prior['conclusion'] = 'success'
        self.set_result('live_pass')
        original = deepcopy(self.result)
        for mutate in (lambda row: row['events'][-1].update(deployment_id=self.intent['baseline_id']),
                       lambda row: row['events'][2].update(command_returned=False),
                       lambda row: row['events'][-1].pop('deployment_id'),
                       lambda row: row['events'][-1].update(at='invalid'),
                       lambda row: row.update(schema=True)):
            self.result = deepcopy(original)
            mutate(self.result)
            self.write_records()
            with self.subTest(mutate=mutate), self.assertRaises(gate.GateError):
                self.clear()

    def test_workflow_success_cannot_clear_unknown_result_or_failed_live_proof(self):
        self.prior['conclusion'] = 'success'
        self.set_result('rollback_unknown')
        with self.assertRaises(gate.GateError):
            self.clear()
        self.set_result('live_pass')
        self.prior['conclusion'] = 'failure'
        with self.assertRaises(gate.GateError):
            self.clear()


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.client = publisher.Clients({'CLOUDFLARE_ACCOUNT_ID': 'e' * 32,
                                        'CLOUDFLARE_API_TOKEN': 'synthetic-pages', 'GITHUB_TOKEN': 'synthetic-readonly'})

    def test_all_pages_read_without_source_branch_or_status_filters(self):
        rows = list(range(201))
        replies = [{'id': history.WORKFLOW_ID, 'path': history.WORKFLOW_PATH},
                   *({'total_count': 201, 'workflow_runs': rows[start:start + 100]} for start in (0, 100, 200))]
        with patch.object(self.client, '_json', side_effect=replies) as request:
            self.assertEqual(self.client.publication_runs(), rows)
            self.assertEqual(request.call_count, 4)
            for call in request.call_args_list:
                self.assertNotIn('head_sha=', call.args[0])
                self.assertNotIn('branch=', call.args[0])
                self.assertNotIn('status=', call.args[0])

    def test_changed_total_truncated_page_or_limit_blocks(self):
        for pages in ([{'total_count': 101, 'workflow_runs': [None] * 100}, {'total_count': 100, 'workflow_runs': [None]}],
                      [{'total_count': 101, 'workflow_runs': [None] * 5}],
                      [{'total_count': 1001, 'workflow_runs': [None] * 100}]):
            with self.subTest(pages=pages), patch.object(self.client, 'history_json', side_effect=[
                {'id': history.WORKFLOW_ID, 'path': history.WORKFLOW_PATH}, *pages
            ]), self.assertRaises(gate.GateError):
                self.client.publication_runs()

    def test_workflow_recreation_requires_review(self):
        with patch.object(self.client, 'history_json', return_value={'id': 999, 'path': history.WORKFLOW_PATH}), self.assertRaises(gate.GateError):
            self.client.publication_runs()

    def test_history_allowlist_excludes_logs_mutations_secrets_and_sha_filter(self):
        with patch.object(self.client, '_json') as request:
            for endpoint in ('/actions/secrets', '/actions/runs/123/logs', '/actions/runs/123/rerun',
                             '/actions/workflows/' + history.WORKFLOW + '/runs?head_sha=' + SHA):
                with self.subTest(endpoint=endpoint), self.assertRaises(gate.GateError):
                    self.client.history_json(endpoint)
            self.assertEqual(request.call_count, 0)

    def test_artifact_and_skipped_job_count_must_be_complete(self):
        for response in ({'total_count': 3, 'artifacts': [{}, {}]}, {'total_count': 1, 'artifacts': []}):
            with self.subTest(response=response), patch.object(self.client, '_json', return_value=response), self.assertRaises(gate.GateError):
                self.client.publication_artifacts({'id': 123})
        with patch.object(self.client, '_json', return_value={'total_count': 4, 'jobs': [{}, {}, {}]}), self.assertRaises(gate.GateError):
            self.client.skipped_publication_jobs({'id': 123})

    def test_download_never_forwards_github_auth_to_signed_storage(self):
        payload = zipped({'sample': 'non-secret'})
        artifact = {'id': 123, 'digest': 'sha256:' + hashlib.sha256(payload).hexdigest()}
        redirect = HTTPError('https://api.github.com', 302, '', {'Location': 'https://example.blob.core.windows.net/artifact?sig=synthetic'}, None)
        response = Mock(status=200)
        response.read.return_value = payload
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.side_effect = [redirect, response]
        with patch.object(history, 'build_opener', return_value=opener):
            self.assertEqual(self.client.publication_journal(artifact), {'sample': 'non-secret'})
        first, second = [call.args[0] for call in opener.open.call_args_list]
        self.assertEqual(first.get_header('Authorization'), 'Bearer synthetic-readonly')
        self.assertIsNone(second.get_header('Authorization'))

    def test_redirect_to_insecure_local_or_unrelated_host_is_rejected(self):
        for url in ('http://example.blob.core.windows.net/a', 'https://127.0.0.1/a', 'https://attacker.example/a',
                    'https://' + 'user:pass@example.blob.core.windows.net/a', 'https://example.blob.core.windows.net:444/a',
                    'https://example.blob.core.windows.net:invalid/a',
                    'https://example.blob.core.windows.net.attacker.example/a', 'https://example.blob.core.windows.net/a#fragment'):
            with self.subTest(url=url), self.assertRaises(gate.GateError):
                history.download_location(url)

    def test_archives_cannot_extract_extra_traversal_symlink_or_unbounded_data(self):
        link = ZipInfo(history.JOURNAL_NAME)
        link.external_attr = 0o120777 << 16
        for payload in (zipped('{}', ['../' + history.JOURNAL_NAME]), zipped('{}', [history.JOURNAL_NAME, 'extra.txt']),
                        zipped('{}', [link]), zipped('x' * (history.MAX_JOURNAL + 1))):
            artifact = {'digest': 'sha256:' + hashlib.sha256(payload).hexdigest()}
            with self.subTest(size=len(payload)), self.assertRaises(gate.GateError):
                history.archive_journal(payload, artifact)

    def test_duplicate_json_keys_digest_mismatch_and_corrupt_archives_block(self):
        for payload, digest in [(zipped('{"state":"prepared","state":"live_pass"}'), None),
                                (zipped('{}'), 'sha256:' + '0' * 64), (b'not a zip', None)]:
            artifact = {'digest': digest or 'sha256:' + hashlib.sha256(payload).hexdigest()}
            with self.subTest(payload_bytes=len(payload)), self.assertRaises(gate.GateError):
                history.archive_journal(payload, artifact)


if __name__ == '__main__':
    unittest.main()
