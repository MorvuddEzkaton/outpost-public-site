"""Regression tests for the owner-reviewed, exact production frontier.

Missing old ZIPs are never fabricated. Only run 42 is a reviewed exception,
and a newer ambiguous attempt must continue blocking uploads.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import production_deployment_gate as gate
import production_history as history


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.anchor = dict(history.RECOVERY_FRONTIER)
        self.run = {
            'id': self.anchor['id'],
            'run_number': self.anchor['run_number'],
            'head_sha': self.anchor['head_sha'],
            'status': 'completed',
            'conclusion': 'success',
        }
        self.record = {
            'kind': 'journal',
            'proof': [
                {'id': self.anchor['intent_id'], 'digest': self.anchor['intent_digest']},
                {'id': self.anchor['result_id'], 'digest': self.anchor['result_digest'],
                 'journal': {'state': 'live_pass', 'events': [
                     {'state': 'live_pass', 'deployment_id': self.anchor['deployment_id']}]}}
            ],
        }
        self.client = Mock()
        self.client.publication_artifacts.return_value = [{'id': self.anchor['intent_id']}]

    def test_exact_anchor_accepts_real_journal_record(self):
        with patch.object(history, 'read_resolved_record', return_value=self.record) as read:
            result = history.verified_recovery_frontier(self.client, self.run, {}, lambda *_: None)
        self.assertEqual(result, self.anchor['head_sha'])
        read.assert_called_once()

    def test_foreign_run_sha_or_missing_deployment_blocks(self):
        for field, value in [('id', 1), ('run_number', 41), ('head_sha', 'e'*40),
                             ('status', 'queued'), ('conclusion', 'failure')]:
            with self.subTest(field=field), self.assertRaises(gate.GateError):
                history.verified_recovery_frontier(self.client,
                    dict(self.run, **{field: value}), {}, lambda *_: None)
        bad = deepcopy(self.record)
        bad['proof'][1]['journal']['events'][-1]['deployment_id'] = '0'*36
        with patch.object(history, 'read_resolved_record', return_value=bad), self.assertRaises(gate.GateError):
            history.verified_recovery_frontier(self.client, self.run, {}, lambda *_: None)

    def test_expired_anchor_requires_provider_successful_steps(self):
        self.client.publication_artifacts.return_value = []
        def job(name, status='success'):
            return {'name': name, 'run_id': self.run['id'], 'head_sha': self.run['head_sha'],
                    'status': 'completed', 'conclusion': status}
        writer = job('publish')
        writer['steps'] = [
            {'name': name, 'conclusion': 'success'} for name in (
                'Prepare read-only deployment plan',
                'Persist intent before any upload',
                'Upload once and require actual matching canonical deployment',
                'Verify all live contracts only after exact deployment proof',
                'Save final journal even on failure; never upload credentials or raw logs')]
        jobs = [job('static-quality'),job('browser-quality'),writer]
        self.client.skipped_publication_jobs.return_value = jobs
        self.assertEqual(history.verified_recovery_frontier(self.client, self.run, {}, lambda *_: None),
                         self.run['head_sha'])
        for mutate in [lambda v: v[2]['steps'].pop(), lambda v: v[2].update(conclusion='failure'),
                       lambda v: v[0].update(head_sha='f'*40)]:
            invalid=deepcopy(jobs);mutate(invalid)
            self.client.skipped_publication_jobs.return_value=invalid
            with self.assertRaises(gate.GateError):
                history.verified_recovery_frontier(self.client, self.run, {}, lambda *_: None)

    def test_future_successful_frontier_works_with_verified_original_journals(self):
        future = dict(self.run, run_number=45, id=7777, head_sha='a'*40)
        evidence = {'kind': 'journal', 'proof': [
            {'journal': {'state':'prepared','events':[{'state':'prepared'}]}},
            {'journal': {'state':'live_pass','events':[{'state':'live_pass'}]}}]}
        with patch.object(history,'read_resolved_record',return_value=evidence):
            self.assertEqual(history.verified_successful_frontier(
                self.client,future,{},lambda *_:None),future['head_sha'])
        broken=deepcopy(evidence);broken['proof'][1]['journal']['state']='upload_unknown'
        with patch.object(history,'read_resolved_record',return_value=broken),self.assertRaises(gate.GateError):
            history.verified_successful_frontier(self.client,future,{},lambda *_:None)

    def test_future_expired_success_cannot_skip_failed_upload_proof(self):
        future = dict(self.run, run_number=45, id=7777, head_sha='a'*40)
        self.client.publication_artifacts.return_value=[]
        def job(name):
            return {'name':name,'run_id':future['id'],'head_sha':future['head_sha'],
                    'run_attempt':1,'status':'completed','conclusion':'success'}
        publisher=job('publish')
        required=[
            'Prepare read-only deployment plan',
            'Persist intent before any upload',
            'Upload once and require actual matching canonical deployment',
            'Verify all live contracts only after exact deployment proof',
            'Save final journal even on failure; never upload credentials or raw logs',
        ]
        publisher['steps']=[{'name':name,'conclusion':'success'} for name in required]
        jobs=[job('static-quality'),job('browser-quality'),publisher]
        self.client.skipped_publication_jobs.return_value=jobs
        self.assertEqual(history.verified_successful_frontier(self.client,future,{},None),future['head_sha'])
        for edit in [lambda j:j[2]['steps'][2].update(conclusion='failure'),
                     lambda j:j[1].update(run_attempt=2),
                     lambda j:j[0].update(conclusion='failure')]:
            broken=deepcopy(jobs);edit(broken)
            self.client.skipped_publication_jobs.return_value=broken
            with self.assertRaises(gate.GateError):
                history.verified_successful_frontier(self.client,future,{},None)
        with self.assertRaises(gate.GateError):
            history.verified_successful_frontier(self.client,
                dict(future,conclusion='failure'),{},None)

    def test_marker_cannot_be_edited_or_created_without_reviewed_git_blob(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/history.RECOVERY_MARKER
            path.parent.mkdir()
            record={
                'schema':1, 'incident':'expired_production_journal_run_18_not_reconstructed',
                'first_unarchived_run_number':17, 'last_reconciled_run_number':42,
                'frontier':self.anchor,
                'resolution':'last_successful_live_deployment_is_new_frontier_only',
            }
            raw=(json.dumps(record)+'\n').encode()
            path.write_bytes(raw)
            def fake_git(args, **kwargs):
                return b'c'*40 if args[1]=='rev-parse' else raw
            with patch('subprocess.check_output', side_effect=fake_git):
                self.assertTrue(history.recovery_marker(root))
                path.write_text('{"schema":1}',encoding='utf-8')
                with self.assertRaises(gate.GateError):
                    history.recovery_marker(root)
                path.write_bytes(raw)
                changed=dict(record, first_unarchived_run_number=18)
                wrong=json.dumps(changed).encode()
                with patch('subprocess.check_output',side_effect=lambda a,**k:b'c'*40 if a[1]=='rev-parse' else wrong),self.assertRaises(gate.GateError):
                    history.recovery_marker(root)

    def test_exact_frontier_keeps_newer_ambiguous_attempt_blocked(self):
        anchor_run=dict(self.run)
        after=dict(self.run,run_number=43,id=888,head_sha='a'*40,
                   conclusion='failure')
        current=dict(self.run,run_number=44,id=889,head_sha='b'*40,
                     status='in_progress',conclusion=None)
        self.client.publication_runs.return_value=[anchor_run,after,current]
        self.client.publication_artifacts.return_value=[{'id':self.anchor['intent_id']}]
        with patch.object(history,'merge_runs',return_value=[anchor_run,after,current]), \
             patch.object(history,'validate_runs',return_value=current), \
             patch.object(history,'verified_recovery_frontier',return_value=anchor_run['head_sha']), \
             patch.object(history,'read_resolved_record',side_effect=gate.GateError('unknown_attempt')):
            with self.assertRaises(gate.GateError):
                history.assert_clear(self.client,{},lambda *_:None,recovery=True)

    def test_recovery_requires_explicit_frontier_even_if_other_runners_are_green(self):
        current=dict(self.run,run_number=43,id=999,head_sha='c'*40,
                     status='in_progress',conclusion=None)
        with patch.object(history,'merge_runs',return_value=[current]), \
             patch.object(history,'validate_runs',return_value=current):
            with self.assertRaises(gate.GateError):
                history.assert_clear(self.client,{},lambda *_:None,recovery=True)


if __name__=='__main__':
    unittest.main()
