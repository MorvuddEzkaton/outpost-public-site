"""Read-only production provenance gate. No D1, secret mutations or Telegram calls.

Local default is offline validation. Network modes require trusted protected-main
GitHub context. A commit-subject PR marker is NOT accepted as review evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'MorvuddEzkaton/outpost-public-site'
OWNER = 'MorvuddEzkaton'
PROJECT = 'outpost-web'
WORKFLOWS = ('deploy-public-production.yml', 'live-production-verify.yml', 'confirm-telegram-release.yml')

class GateError(RuntimeError):
    pass

def require(ok, code):
    if not ok:
        raise GateError(code)

def trusted_context(env):
    require(env.get('GITHUB_REPOSITORY') == REPOSITORY and env.get('GITHUB_REPOSITORY_OWNER') == OWNER,
            'repository_identity_rejected')
    require(env.get('GITHUB_REF') == 'refs/heads/main', 'only_main_allowed')
    require(env.get('GITHUB_EVENT_NAME') in ('push', 'workflow_dispatch'), 'event_rejected')
    if env['GITHUB_EVENT_NAME'] == 'workflow_dispatch':
        require(env.get('GITHUB_ACTOR') == OWNER, 'dispatch_requires_owner')
    sha = env.get('GITHUB_SHA', '')
    require(re.fullmatch(r'[a-f0-9]{40}', sha) is not None, 'invalid_source_sha')
    require(env.get('OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED') == '1', 'production_activation_missing')
    allowed = [REPOSITORY + '/.github/workflows/' + name + '@refs/heads/main' for name in WORKFLOWS]
    require(env.get('GITHUB_WORKFLOW_REF') in allowed, 'untrusted_workflow_source')
    return sha

def validate_review(main, prs, reviews, sha):
    require(main.get('object', {}).get('sha') == sha, 'main_advanced_or_mismatched')
    matching = [p for p in prs if p.get('merged_at') and p.get('merge_commit_sha') == sha and
                p.get('base', {}).get('ref') == 'main' and p.get('base', {}).get('repo', {}).get('full_name') == REPOSITORY]
    require(len(matching) == 1, 'no_unique_actual_merged_pr')
    pr = matching[0]
    owner_reviews = [r for r in reviews if r.get('user', {}).get('login') == OWNER and r.get('state') != 'COMMENTED']
    require(owner_reviews, 'human_codeowner_review_missing')
    latest = max(owner_reviews, key=lambda r: (r.get('submitted_at') or '', r.get('id', 0)))
    require(latest.get('state') == 'APPROVED' and latest.get('commit_id') == pr.get('head', {}).get('sha'),
            'review_not_approved_for_exact_head')
    return {'pr': pr['number'], 'head_sha': pr['head']['sha'], 'owner_review_id': latest['id']}

def validate_environment(environment, policies):
    require(environment.get('name') == 'production', 'production_environment_missing')
    rules = [r for r in environment.get('protection_rules', []) if r.get('type') == 'required_reviewers']
    require(len(rules) == 1 and any(r.get('type') == 'User' and r.get('reviewer', {}).get('login') == OWNER
                                  for r in rules[0].get('reviewers', [])), 'human_deployment_approval_missing')
    require(environment.get('deployment_branch_policy') == {'protected_branches': False, 'custom_branch_policies': True},
            'main_only_environment_policy_required')
    entries = policies.get('branch_policies', [])
    require(policies.get('total_count') == 1 and len(entries) == 1 and entries[0].get('name') == 'main' and
            entries[0].get('type') == 'branch', 'environment_not_main_only')

def validate_notification_mode(health):
    require(health.get('ok') is True and health.get('enabled') is True and type(health.get('release_mode_schema')) is int and health.get('release_mode_schema') == 1 and
            health.get('confirmed_releases_enabled') is True and health.get('legacy_release_notifications_enabled') is False,
            'unsafe_legacy_or_unknown_notification_mode')

def sanitized(value):
    if isinstance(value, list):
        return [sanitized(v) for v in value]
    if isinstance(value, dict):
        if value.get('type') == 'secret_text':
            return {'type': 'secret_text'}
        return {k: sanitized(v) for k, v in value.items()}
    return value

def stable_project(value):
    result = sanitized(value)
    result.pop('canonical_deployment', None)
    result.pop('latest_deployment', None)
    return result

def validate_project(project, config, config_hash):
    from verify_cloudflare_config import EXPECTED_PRODUCTION_D1, EXPECTED_PREVIEW_D1, as_binding_map
    require(project.get('name') == PROJECT and project.get('production_branch') == 'main', 'wrong_pages_project')
    require(project.get('source', {}).get('type') == 'github' and
            project['source'].get('config', {}).get('production_deployments_enabled') is False, 'old_git_autodeploy_not_disabled')
    require(config.get('name') == PROJECT and config.get('pages_build_output_dir') == './site' and
            config.get('compatibility_date') == '2026-08-22', 'wrong_local_configuration')
    require(as_binding_map(config.get('d1_databases', [])) == EXPECTED_PRODUCTION_D1 and
            as_binding_map(config.get('env', {}).get('preview', {}).get('d1_databases', [])) == EXPECTED_PREVIEW_D1,
            'local_binding_drift')
    require(set(config) == {'$schema', 'name', 'pages_build_output_dir', 'compatibility_date', 'd1_databases', 'env'} and
            set(config['env']) == {'preview'} and set(config['env']['preview']) == {'d1_databases'}, 'unexpected_config_fields')
    for name, expected in [('production', EXPECTED_PRODUCTION_D1), ('preview', EXPECTED_PREVIEW_D1)]:
        value = project.get('deployment_configs', {}).get(name, {})
        require(value.get('d1_databases') == {binding: {'id': pair[1]} for binding, pair in expected.items()}, 'remote_binding_drift')
        require(value.get('compatibility_date') == config['compatibility_date'] and value.get('compatibility_flags') == [] and
                value.get('wrangler_config_hash') == config_hash, 'runtime_or_configuration_hash_drift')
    require(set(project.get('domains', [])) >= {'outpost.com.ua', 'www.outpost.com.ua'}, 'production_domains_missing')

def validate_deployment(project, sha, deployment_id=None):
    deploy = project.get('canonical_deployment') or {}
    metadata = deploy.get('deployment_trigger', {}).get('metadata', {})
    require(deploy.get('environment') == 'production' and deploy.get('latest_stage', {}).get('status') == 'success' and
            metadata.get('branch') == 'main' and metadata.get('commit_hash') == sha and metadata.get('commit_dirty') is False,
            'canonical_deployment_not_exact_success')
    require(re.fullmatch(r'[a-f0-9-]{36}', deploy.get('id', '')) is not None, 'invalid_deployment_identity')
    if deployment_id is not None:
        require(deploy['id'] == deployment_id, 'deployment_identity_changed')
    require(sanitized(deploy.get('env_vars', {})) == sanitized(project['deployment_configs']['production'].get('env_vars', {})),
            'deployed_secret_names_or_environment_differ')
    return deploy['id']

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

class ReadOnlyClients:
    def __init__(self, env):
        self.account = env.get('CLOUDFLARE_ACCOUNT_ID', '')
        self.token = env.get('CLOUDFLARE_API_TOKEN', '')
        require(re.fullmatch(r'[a-f0-9]{32}', self.account) is not None and self.token, 'pages_credential_missing')
        self.base = '/accounts/' + self.account + '/pages/projects/' + PROJECT

    @staticmethod
    def _json(url, headers):
        try:
            with build_opener(NoRedirect).open(Request(url, headers=headers, method='GET'), timeout=20) as response:
                require(response.status == 200, 'readonly_http_not_success')
                body = response.read(2_000_001)
                require(len(body) <= 2_000_000, 'readonly_response_too_large')
                return json.loads(body)
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            raise GateError('readonly_request_failed') from None

    def github(self, suffix):
        require(suffix in ('/git/ref/heads/main', '/environments/production', '/environments/production/deployment-branch-policies') or
                re.fullmatch(r'/commits/[a-f0-9]{40}/pulls\?per_page=100', suffix) or
                re.fullmatch(r'/pulls/\d+/reviews\?per_page=100', suffix), 'unapproved_github_read')
        # Public metadata can be read without a token. Never obtain broader GitHub permissions here.
        return self._json('https://api.github.com/repos/' + REPOSITORY + suffix,
                          {'Accept': 'application/vnd.github+json', 'User-Agent': 'OutPOSt-Production-Provenance'})

    def pages(self, suffix=''):
        require(suffix in ('', '/deployments') or re.fullmatch(r'/deployments/[a-f0-9-]{36}', suffix), 'unapproved_pages_read')
        value = self._json('https://api.cloudflare.com/client/v4' + self.base + suffix, {'Authorization': 'Bearer ' + self.token})
        require(value.get('success') is True, 'pages_read_unsuccessful')
        return value['result']

    def health(self):
        return self._json('https://outpost.com.ua/api/telegram/health', {'User-Agent': 'OutPOSt-Notification-Mode-Guard'})

def review_proof(client, sha):
    main = client.github('/git/ref/heads/main')
    prs = client.github('/commits/' + sha + '/pulls?per_page=100')
    matches = [p for p in prs if p.get('merged_at') and p.get('merge_commit_sha') == sha]
    require(len(matches) == 1, 'no_unique_actual_merged_pr')
    reviews = client.github('/pulls/' + str(matches[0]['number']) + '/reviews?per_page=100')
    require(len(prs) < 100 and len(reviews) < 100, 'provenance_pagination_requires_review')
    proof = validate_review(main, prs, reviews, sha)
    validate_environment(client.github('/environments/production'), client.github('/environments/production/deployment-branch-policies'))
    return proof

def local_source(root, sha):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    require(head == sha, 'checkout_not_exact_event_sha')
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip(), 'dirty_checkout_rejected')
    for directory in [root, *root.parents]:
        require(not (directory / '.env').exists() and not (directory / '.dev.vars').exists(), 'development_secrets_near_upload')
    config_bytes = (root / 'wrangler.jsonc').read_bytes()
    blob = subprocess.check_output(['git', 'show', sha + ':wrangler.jsonc'], cwd=root)
    require(blob == config_bytes, 'config_not_reviewed_blob')
    return json.loads(config_bytes), hashlib.sha256(config_bytes).hexdigest()

def verify_current(env, root=ROOT, client=None, wait_seconds=0):
    sha = trusted_context(env)
    config, config_hash = local_source(root, sha)
    client = client or ReadOnlyClients(env)
    review = review_proof(client, sha)
    # Safe read-only health, not /download or /; no legacy notifier side effects.
    validate_notification_mode(client.health())
    deadline = time.monotonic() + wait_seconds
    while True:
        project = client.pages()
        validate_project(project, config, config_hash)
        try:
            deployment_id = validate_deployment(project, sha)
            break
        except GateError:
            require(time.monotonic() < deadline, 'matching_successful_deployment_not_available')
            require(client.github('/git/ref/heads/main')['object']['sha'] == sha, 'main_advanced_during_wait')
            time.sleep(5)
    require(client.github('/git/ref/heads/main')['object']['sha'] == sha, 'main_advanced_after_deployment')
    validate_notification_mode(client.health())
    return {'schema_version': 1, 'kind': 'production-provenance-not-release-announcement', 'source_sha': sha,
            'deployment_id': deployment_id, 'configuration_sha256': config_hash, 'review': review,
            'confirmed_mode': True, 'legacy_sender': False, 'database_writes': 0, 'messages_sent': 0}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only remote proof; trusted CI context required')
    parser.add_argument('--wait-seconds', type=int, default=0)
    args = parser.parse_args()
    require(0 <= args.wait_seconds <= 300, 'invalid_wait_bound')
    if not args.check:
        from verify_cloudflare_config import main as config_check
        require(config_check() == 0, 'offline_config_rejected')
        print('Production provenance: OFFLINE ONLY; activation/credentials/remote deployment NOT verified')
        return 0
    print(json.dumps(verify_current(os.environ, wait_seconds=args.wait_seconds)))
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except GateError as error:
        print('Production provenance: BLOCKED — ' + str(error))
        raise SystemExit(1)
