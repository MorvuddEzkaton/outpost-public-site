"""Pure synthetic provenance/privilege regression tests. No real credentials or network."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import production_deployment_gate as gate
from verify_cloudflare_config import EXPECTED_PRODUCTION_D1, EXPECTED_PREVIEW_D1, EXPECTED_PREVIEW_CONFIG_HASH, configuration_errors, APPROVED_CONFIG_HASH, LEGACY_CONFIG_HASH

SHA = 'a' * 40
HEAD = 'b' * 40
HASH = 'c' * 64
DEPLOYMENT = '11111111-1111-4111-8111-111111111111'

def environment():
    return {'GITHUB_REPOSITORY': gate.REPOSITORY, 'GITHUB_REPOSITORY_OWNER': gate.OWNER, 'GITHUB_REF': 'refs/heads/main',
            'GITHUB_EVENT_NAME': 'push', 'GITHUB_SHA': SHA, 'GITHUB_ACTOR': gate.OWNER,
            'OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED': '1',
            'GITHUB_WORKFLOW_REF': gate.REPOSITORY + '/.github/workflows/deploy-public-production.yml@refs/heads/main'}

def project():
    prod = {'d1_databases': {k: {'id': v[1]} for k, v in EXPECTED_PRODUCTION_D1.items()}, 'compatibility_date': '2026-08-22',
            'compatibility_flags': [], 'wrangler_config_hash': HASH, 'env_vars': {'DEMO_SECRET': {'type': 'secret_text'}}}
    preview = {'d1_databases': {k: {'id': v[1]} for k, v in EXPECTED_PREVIEW_D1.items()}, 'compatibility_date': '2026-08-22',
               'compatibility_flags': [], 'wrangler_config_hash': EXPECTED_PREVIEW_CONFIG_HASH, 'env_vars': {}}
    return {'name': gate.PROJECT, 'production_branch': 'main', 'domains': ['outpost.com.ua', 'www.outpost.com.ua'],
            'source': {'type': 'github', 'config': {'production_deployments_enabled': False}},
            'deployment_configs': {'production': prod, 'preview': preview},
            'canonical_deployment': {'id': DEPLOYMENT, 'environment': 'production', 'latest_stage': {'status': 'success'},
                'env_vars': deepcopy(prod['env_vars']), 'deployment_trigger': {'metadata': {'branch': 'main', 'commit_hash': SHA, 'commit_dirty': False}}}}

def prs():
    return [{'number': 10, 'merged_at': '2026-01-01T00:00:00Z', 'merge_commit_sha': SHA, 'head': {'sha': HEAD},
             'base': {'ref': 'main', 'repo': {'full_name': gate.REPOSITORY}}}]

def reviews():
    return [{'id': 10, 'user': {'login': gate.OWNER}, 'state': 'APPROVED', 'commit_id': HEAD, 'submitted_at': '2026-01-01T00:00:01Z'}]

def owner_pr():
    value = deepcopy(prs()[0])
    value['user'] = {'login': gate.OWNER}
    return value

def owner_pr_detail():
    value = owner_pr()
    return {**value, 'merged': True, 'merged_by': {'login': gate.OWNER}}

def protected_env():
    return {'name': 'production', 'protection_rules': [{'type': 'required_reviewers', 'reviewers': [{'type': 'User', 'reviewer': {'login': gate.OWNER}}]}],
            'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True}}

def automatic_env():
    value = protected_env()
    value['protection_rules'] = []
    return value

def policies():
    return {'total_count': 1, 'branch_policies': [{'name': 'main', 'type': 'branch'}]}

def health():
    return {'ok': True, 'enabled': True, 'release_mode_schema': 1, 'confirmed_releases_enabled': True, 'legacy_release_notifications_enabled': False}

class GateTests(unittest.TestCase):
    def test_trusted_context(self):
        self.assertEqual(gate.trusted_context(environment()), SHA)
        self.assertEqual(gate.trusted_context({**environment(), 'GITHUB_EVENT_NAME': 'workflow_dispatch'}), SHA)

    def test_forks_refs_events_and_activation_fail_closed(self):
        mutations = {'GITHUB_REPOSITORY': 'attacker/fork', 'GITHUB_REPOSITORY_OWNER': 'attacker', 'GITHUB_REF': 'refs/heads/staging',
                     'GITHUB_SHA': 'a'*39, 'OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED': '0',
                     'GITHUB_WORKFLOW_REF': gate.REPOSITORY+'/.github/workflows/deploy-public-production.yml@refs/heads/topic'}
        for key, value in mutations.items():
            with self.subTest(key=key), self.assertRaises(gate.GateError): gate.trusted_context({**environment(), key: value})
        for event in ['pull_request', 'pull_request_target', 'workflow_run', 'schedule', 'release', '']:
            with self.subTest(event=event), self.assertRaises(gate.GateError): gate.trusted_context({**environment(), 'GITHUB_EVENT_NAME': event})

    def test_other_actor_cannot_dispatch(self):
        with self.assertRaises(gate.GateError): gate.trusted_context({**environment(), 'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_ACTOR': 'attacker'})

    def test_real_review_proof(self):
        self.assertEqual(gate.validate_review({'object': {'sha': SHA}}, prs(), reviews(), SHA)['pr'], 10)

    def test_owner_self_merge_requires_real_exact_pr_metadata(self):
        proof = gate.validate_review({'object': {'sha': SHA}}, [owner_pr()], [], SHA, owner_pr_detail())
        self.assertEqual(proof, {'pr': 10, 'head_sha': HEAD, 'owner_review_id': None,
                                 'authorization': 'owner_self_merge'})
        # Read-only GitHub PR details, not the PR title or commit subject, prove authorization.
        for wrong in (None, {}, {'number': 10}, {**owner_pr_detail(), 'merged': False},
                      {**owner_pr_detail(), 'merged_by': {'login': 'bot[bot]'}},
                      {**owner_pr_detail(), 'user': {'login': 'other'}},
                      {**owner_pr_detail(), 'head': {'sha': SHA}},
                      {**owner_pr_detail(), 'merge_commit_sha': HEAD},
                      {**owner_pr_detail(), 'base': {'ref': 'staging', 'repo': {'full_name': gate.REPOSITORY}}},
                      {**owner_pr_detail(), 'merged_at': None}):
            with self.subTest(wrong=wrong), self.assertRaises(gate.GateError):
                gate.validate_review({'object': {'sha': SHA}}, [owner_pr()], [], SHA, wrong)

    def test_bot_or_other_author_still_requires_exact_codeowner_approval(self):
        unreviewed = prs()
        unreviewed[0]['user'] = {'login': 'outpost-public-pr-helper[bot]'}
        with self.assertRaisesRegex(gate.GateError, 'human_codeowner_review_missing'):
            gate.validate_review({'object': {'sha': SHA}}, unreviewed, [], SHA)
        approved = gate.validate_review({'object': {'sha': SHA}}, unreviewed, reviews(), SHA)
        self.assertEqual(approved['owner_review_id'], 10)
        self.assertNotIn('authorization', approved)

    def test_fake_commit_subject_or_no_associated_merged_pr(self):
        for candidates in [[], [{**prs()[0], 'merged_at': None}], [{**prs()[0], 'merge_commit_sha': HEAD}], prs()+prs()]:
            with self.subTest(candidates=candidates), self.assertRaises(gate.GateError): gate.validate_review({'object': {'sha': SHA}}, candidates, reviews(), SHA)

    def test_stale_rejected_dismissed_bot_or_wrong_head_review(self):
        for changes in [{'state': 'CHANGES_REQUESTED'}, {'state': 'DISMISSED'}, {'state': 'COMMENTED'}, {'commit_id': SHA}, {'user': {'login': 'bot[bot]'}}]:
            with self.subTest(changes=changes), self.assertRaises(gate.GateError): gate.validate_review({'object': {'sha': SHA}}, prs(), [{**reviews()[0], **changes}], SHA)

    def test_latest_owner_review_is_authoritative(self):
        rejected = {**reviews()[0], 'id': 11, 'state': 'CHANGES_REQUESTED', 'submitted_at': '2026-01-02T00:00:00Z'}
        with self.assertRaises(gate.GateError): gate.validate_review({'object': {'sha': SHA}}, prs(), reviews()+[rejected], SHA)

    def test_main_moved_or_wrong_repository(self):
        with self.assertRaises(gate.GateError): gate.validate_review({'object': {'sha': HEAD}}, prs(), reviews(), SHA)
        candidate = prs(); candidate[0]['base']['repo']['full_name'] = 'attacker/fork'
        with self.assertRaises(gate.GateError): gate.validate_review({'object': {'sha': SHA}}, candidate, reviews(), SHA)

    def test_environment_requires_human_and_main_only(self):
        gate.validate_environment(protected_env(), policies())
        for changes in [{'name': 'preview'}, {'protection_rules': []}, {'deployment_branch_policy': None}]:
            with self.subTest(changes=changes), self.assertRaises(gate.GateError): gate.validate_environment({**protected_env(), **changes}, policies())
        for value in [{'total_count': 1, 'branch_policies': [{'name': '*', 'type': 'branch'}]},
                      {'total_count': 1, 'branch_policies': [{'name': 'main', 'type': 'tag'}]},
                      {'total_count': 2, 'branch_policies': policies()['branch_policies']*2}]:
            with self.subTest(value=value), self.assertRaises(gate.GateError): gate.validate_environment(protected_env(), value)

    def test_auto_mode_needs_explicit_variable_and_no_human_reviewers(self):
        self.assertFalse(gate.automatic_approval_enabled(environment()))
        self.assertTrue(gate.automatic_approval_enabled({**environment(), 'OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED': '1'}))
        for value in ['', 'true', 'yes', '2', None]:
            with self.subTest(value=value), self.assertRaisesRegex(gate.GateError, 'invalid_automatic_approval_setting'):
                gate.automatic_approval_enabled({**environment(), 'OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED': value})
        gate.validate_environment(automatic_env(), policies(), automatic=True)
        for automatic, cfg in [(True, protected_env()), (False, automatic_env())]:
            with self.subTest(automatic=automatic), self.assertRaises(gate.GateError):
                gate.validate_environment(cfg, policies(), automatic=automatic)
        for bad in [
            {'name': 'preview'},
            {'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': False}},
            {'deployment_branch_policy': None},
            {'protection_rules': [{'type': 'required_reviewers', 'reviewers': []}]},
        ]:
            with self.subTest(change=bad), self.assertRaises(gate.GateError):
                gate.validate_environment({**automatic_env(), **bad}, policies(), automatic=True)
        for changed in [{'total_count': 0, 'branch_policies': []},
                        {'total_count': 1, 'branch_policies': [{'name': '*', 'type': 'branch'}]},
                        {'total_count': 1, 'branch_policies': [{'name': 'main', 'type': 'tag'}]}]:
            with self.subTest(policies=changed), self.assertRaises(gate.GateError):
                gate.validate_environment(automatic_env(), changed, automatic=True)

    def test_old_missing_legacy_or_disabled_health_blocks(self):
        gate.validate_notification_mode(health())
        for field in health():
            mutated = health(); mutated.pop(field)
            with self.subTest(field=field), self.assertRaises(gate.GateError): gate.validate_notification_mode(mutated)
        for changes in [{'legacy_release_notifications_enabled': True}, {'confirmed_releases_enabled': False}, {'enabled': False}, {'release_mode_schema': 2}, {'release_mode_schema': True}]:
            with self.subTest(changes=changes), self.assertRaises(gate.GateError): gate.validate_notification_mode({**health(), **changes})

    def test_original_project_contract(self):
        config = json.loads((gate.ROOT/'wrangler.jsonc').read_text(encoding='utf-8'))
        gate.validate_project(project(), config, HASH)
        for mutation in ['project', 'auto', 'binding', 'runtime', 'hash', 'domains', 'preview']:
            changed = project()
            if mutation == 'project': changed['name'] = 'another-project'
            elif mutation == 'auto': changed['source']['config']['production_deployments_enabled'] = True
            elif mutation == 'binding': changed['deployment_configs']['production']['d1_databases']['CMS_DB']['id'] = 'demo-other-db'
            elif mutation == 'preview': changed['deployment_configs']['preview']['d1_databases'] = changed['deployment_configs']['production']['d1_databases']
            elif mutation == 'runtime': changed['deployment_configs']['production']['compatibility_flags'] = ['nodejs_compat']
            elif mutation == 'hash': changed['deployment_configs']['production'].pop('wrangler_config_hash')
            elif mutation == 'domains': changed['domains'] = []
            with self.subTest(mutation=mutation), self.assertRaises(gate.GateError): gate.validate_project(changed, config, HASH)

    def test_local_preview_config_or_new_vars_cannot_upload(self):
        config = json.loads((gate.ROOT/'wrangler.jsonc').read_text(encoding='utf-8'))
        with self.assertRaises(gate.GateError): gate.validate_project(project(), {**config, 'vars': {'DEMO': 'value'}}, HASH)
        config['d1_databases'] = config['env']['preview']['d1_databases']
        with self.assertRaises(gate.GateError): gate.validate_project(project(), config, HASH)

    def test_declared_runtime_mode_and_preview_isolation_are_exact(self):
        config = json.loads((gate.ROOT/'wrangler.jsonc').read_text(encoding='utf-8'))
        self.assertEqual(configuration_errors(config), [])
        for value in [None, {}, {'TELEGRAM_CONFIRMED_RELEASES_ENABLED': '0'}, {'TELEGRAM_CONFIRMED_RELEASES_ENABLED': 1},
                      {'TELEGRAM_CONFIRMED_RELEASES_ENABLED': True}, {'TELEGRAM_CONFIRMED_RELEASES_ENABLED': 'true'},
                      {**config['vars'], 'TELEGRAM_BOT_TOKEN': 'SYNTHETIC-ONLY'}]:
            changed = deepcopy(config); changed['vars'] = value
            with self.subTest(value=value), self.assertRaises(gate.GateError): gate.validate_project(project(), changed, HASH)
        for value in [None, {'TELEGRAM_CONFIRMED_RELEASES_ENABLED': '1'}, {'OUTPOST_PREVIEW_ONLY': '1'}]:
            changed = deepcopy(config); changed['env']['preview']['vars'] = value
            with self.subTest(preview=value), self.assertRaises(gate.GateError): gate.validate_project(project(), changed, HASH)
        changed = deepcopy(config); del changed['env']['preview']['vars']
        with self.assertRaises(gate.GateError): gate.validate_project(project(), changed, HASH)

    def test_preview_marker_is_pinned_independently_not_silently_updated(self):
        config = json.loads((gate.ROOT/'wrangler.jsonc').read_text(encoding='utf-8'))
        self.assertEqual(EXPECTED_PREVIEW_CONFIG_HASH, LEGACY_CONFIG_HASH)
        for value in [None, APPROVED_CONFIG_HASH, '0'*64]:
            changed = project(); changed['deployment_configs']['preview']['wrangler_config_hash'] = value
            with self.subTest(marker=value), self.assertRaises(gate.GateError): gate.validate_project(changed, config, HASH)

    def test_subscriber_mode_cannot_be_omitted_changed_or_inherited_by_preview(self):
        config = json.loads((gate.ROOT/'wrangler.jsonc').read_text(encoding='utf-8'))
        self.assertEqual(config['vars'], {'TELEGRAM_CONFIRMED_RELEASES_ENABLED':'1', 'TELEGRAM_RELEASE_DELIVERY_MODE':'subscribers'})
        for mode in [None, '', 'pilot', 'off', 'SUBSCRIBERS', 1, True]:
            changed = deepcopy(config)
            if mode is None: del changed['vars']['TELEGRAM_RELEASE_DELIVERY_MODE']
            else: changed['vars']['TELEGRAM_RELEASE_DELIVERY_MODE'] = mode
            with self.subTest(mode=mode), self.assertRaises(gate.GateError): gate.validate_project(project(), changed, HASH)
        changed = deepcopy(config); changed['env']['preview']['vars'] = deepcopy(config['vars'])
        with self.assertRaises(gate.GateError): gate.validate_project(project(), changed, HASH)

    def test_previous_confirmed_only_config_is_historical_not_current(self):
        from verify_cloudflare_config import CONFIRMED_MODE_CONFIG_HASH
        config = json.loads((gate.ROOT/'wrangler.jsonc').read_text(encoding='utf-8'))
        changed = project(); changed['deployment_configs']['production']['wrangler_config_hash'] = CONFIRMED_MODE_CONFIG_HASH
        with self.assertRaises(gate.GateError): gate.validate_project(changed, config, APPROVED_CONFIG_HASH)
        self.assertNotEqual(APPROVED_CONFIG_HASH, CONFIRMED_MODE_CONFIG_HASH)
        self.assertEqual(EXPECTED_PREVIEW_CONFIG_HASH, LEGACY_CONFIG_HASH)

    def test_successful_exact_canonical_only(self):
        self.assertEqual(gate.validate_deployment(project(), SHA, DEPLOYMENT), DEPLOYMENT)
        for mutation in ['environment', 'failure', 'queued', 'sha', 'dirty', 'branch', 'identity', 'secrets']:
            changed = project(); dep = changed['canonical_deployment']; meta = dep['deployment_trigger']['metadata']
            if mutation == 'environment': dep['environment'] = 'preview'
            elif mutation in ['failure', 'queued']: dep['latest_stage']['status'] = mutation
            elif mutation == 'sha': meta['commit_hash'] = HEAD
            elif mutation == 'dirty': meta['commit_dirty'] = True
            elif mutation == 'branch': meta['branch'] = 'staging'
            elif mutation == 'identity': dep['id'] = 'invalid'
            elif mutation == 'secrets': dep['env_vars'] = {}
            with self.subTest(mutation=mutation), self.assertRaises(gate.GateError): gate.validate_deployment(changed, SHA, DEPLOYMENT)

    def test_unknown_secret_values_are_not_equality_claim(self):
        self.assertEqual(gate.sanitized({'key': {'type': 'secret_text', 'value': 'demo-not-a-real-secret'}}), {'key': {'type': 'secret_text'}})
        self.assertNotIn('canonical_deployment', gate.stable_project(project()))

    def test_client_rejects_writes_other_projects_or_private_services(self):
        client = gate.ReadOnlyClients({'CLOUDFLARE_ACCOUNT_ID': 'a'*32, 'CLOUDFLARE_API_TOKEN': 'demo-not-a-real-token'})
        with patch.object(client, '_json', side_effect=AssertionError('No network expected')):
            for path in ['/domains', '/settings', '/query', '/../another', '/deployments/bad']:
                with self.subTest(path=path), self.assertRaises(gate.GateError): client.pages(path)
            for path in ['/actions/secrets', '/git/ref/heads/topic', '/pulls/1/merge', '/issues', '/contents/.env']:

                with self.subTest(path=path), self.assertRaises(gate.GateError): client.github(path)

    def fake_client(self, sequence=None, change_main=False, unsafe_after=False, automatic=False):
        class Client:
            pages_calls=0
            main_calls=0
            health_calls=0
            def github(self, suffix):
                if suffix=='/git/ref/heads/main':
                    self.main_calls+=1
                    return {'object': {'sha': HEAD if change_main and self.main_calls>1 else SHA}}
                if suffix.startswith('/commits/'):return prs()
                if suffix.startswith('/pulls/'):return reviews()
                if suffix.endswith('/deployment-branch-policies'):return policies()
                if suffix.endswith('/production'):return automatic_env() if automatic else protected_env()
                raise AssertionError('Unexpected route')
            def pages(self):
                self.pages_calls+=1
                return deepcopy((sequence or [project()])[min(self.pages_calls-1,len(sequence or [project()])-1)])
            def health(self):
                self.health_calls+=1
                return {**health(), **({'legacy_release_notifications_enabled': True} if unsafe_after and self.health_calls>1 else {})}
        return Client()

    def verify_with(self, client, wait_seconds=0, automatic=False):
        config=json.loads((gate.ROOT/'wrangler.jsonc').read_text(encoding='utf-8'))
        with patch.object(gate,'local_source',return_value=(config,HASH)),patch.object(gate.time,'sleep'):
            return gate.verify_current({**environment(), 'OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED': '1' if automatic else '0'},client=client,wait_seconds=wait_seconds)

    def test_remote_orchestration_is_readonly_exact_and_rechecks_health(self):
        client=self.fake_client()
        proof=self.verify_with(client)
        self.assertEqual(proof['deployment_id'],DEPLOYMENT)
        self.assertEqual(proof['database_writes'],0)
        self.assertEqual(client.health_calls,2)
        self.assertEqual(client.pages_calls,1)

    def test_auto_mode_requires_matching_remote_environment_during_full_proof(self):
        client=self.fake_client(automatic=True)
        self.assertEqual(self.verify_with(client, automatic=True)['deployment_id'], DEPLOYMENT)
        with self.assertRaisesRegex(gate.GateError, 'human_deployment_approval_missing'):
            self.verify_with(self.fake_client(automatic=True))
        with self.assertRaisesRegex(gate.GateError, 'automatic_mode_requires_no_required_reviewers'):
            self.verify_with(self.fake_client(), automatic=True)

    def test_wait_old_version_until_matching_actual_success(self):
        old=project();old['canonical_deployment']['deployment_trigger']['metadata']['commit_hash']=HEAD
        client=self.fake_client([old,project()])
        self.assertEqual(self.verify_with(client,wait_seconds=10)['source_sha'],SHA)
        self.assertEqual(client.pages_calls,2)

    def test_without_wait_old_production_is_not_pass(self):
        old=project();old['canonical_deployment']['deployment_trigger']['metadata']['commit_hash']=HEAD
        with self.assertRaises(gate.GateError):self.verify_with(self.fake_client([old]))

    def test_main_changes_during_wait_or_after_success_block(self):
        old=project();old['canonical_deployment']['deployment_trigger']['metadata']['commit_hash']=HEAD
        for sequence in [[old,project()],[project()]]:
            with self.subTest(sequence=sequence),self.assertRaises(gate.GateError):self.verify_with(self.fake_client(sequence,change_main=True),wait_seconds=10)

    def test_health_changes_after_wait_block_canonical_checks(self):
        with self.assertRaises(gate.GateError):self.verify_with(self.fake_client(unsafe_after=True))

    def test_fork_context_blocks_before_credentials_or_network(self):
        with patch.object(gate,'ReadOnlyClients',side_effect=AssertionError('No credentials/network allowed')):
            with self.assertRaises(gate.GateError):gate.verify_current({**environment(),'GITHUB_REPOSITORY':'attacker/fork'})

if __name__ == '__main__': unittest.main()
