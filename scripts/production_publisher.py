"""Opt-in Pages publisher. Default is OFFLINE; no credentials or network are used.

Plan/upload/verify/rollback are separate commands in protected main CI. A durable
intent must be saved as a GitHub artifact before the single upload attempt.
This code never edits Pages settings, D1, DNS, secrets, or Telegram state.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.request import Request, build_opener
import production_deployment_gate as gate
import production_history as history
import production_checkpoints as checkpoints
from verify_cloudflare_config import APPROVED_CONFIG_HASH, LEGACY_CONFIG_HASH, CONFIRMED_MODE_CONFIG_HASH

WRANGLER_VERSION = '4.142.0'
# Only already reviewed pins are understood by the read-only historical validator.
# Current plan/upload/live/rollback accepts only the current subscriber config.
# Older exact pins validate immutable resolved evidence, NEVER new operations.
EVIDENCE_CONFIG_HASHES = frozenset({LEGACY_CONFIG_HASH, CONFIRMED_MODE_CONFIG_HASH, APPROVED_CONFIG_HASH})
TERMINAL = {'success', 'failure', 'canceled', 'skipped'}
PAGES_PER_PAGE = 20
MAX_PRODUCTION_DEPLOYMENTS = 1000
LIVE_COMMANDS = (
    'verify_live_production.py', 'verify_live_site_identity.py', 'verify_live_public_ctas.py',
    'verify_live_phone_ctas.py', 'verify_live_sitemap.py', 'verify_live_robots.py',
    'verify_live_indexability.py', 'verify_live_404.py', 'verify_live_public_links.py',
    'verify_live_security_headers.py', 'verify_live_static_assets.py',
    'verify_live_url_normalization.py', 'verify_live_host_normalization.py',
    'verify_live_cloudflare_privacy.py', 'verify_live_social_metadata.py',
    'verify_live_structured_metadata.py', 'verify_live_product_maturity.py',
    'verify_live_accounting_release.py', 'verify_live_support_discovery.py',
    'verify_live_cabinet_entry.py',
)
# Public GET verifiers need runtime/TLS settings and bounded retry controls, not
# the parent publisher's Pages/Actions credentials or trusted workflow context.
LIVE_RUNTIME_ENV = frozenset({
    'PATH', 'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE', 'TEMP', 'TMP', 'TMPDIR',
    'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ', 'LD_LIBRARY_PATH',
    'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH',
    'PYTHONUTF8', 'PYTHONIOENCODING', 'PYTHONPYCACHEPREFIX',
    'SSL_CERT_FILE', 'SSL_CERT_DIR',
})
LIVE_TUNING_ENV = frozenset(
    'OUTPOST_LIVE_' + name + '_' + suffix
    for name in ('VERIFY', 'IDENTITY', '404', 'CLOUDFLARE_PRIVACY', 'CABINET',
                 'HOST_NORMALIZATION', 'INDEXABILITY', 'PHONE', 'MATURITY',
                 'LINKS', 'ROBOTS', 'SECURITY', 'SITEMAP', 'ASSETS', 'STRUCTURED',
                 'SOCIAL', 'SUPPORT', 'NORMALIZATION')
    for suffix in ('ATTEMPTS', 'DELAY_SECONDS')
) | frozenset('OUTPOST_LIVE_' + name + '_WORKERS' for name in
              ('IDENTITY', 'HOST_NORMALIZATION', 'NORMALIZATION', 'SOCIAL', 'STRUCTURED'))

def digest(value):
    payload = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(payload).hexdigest()

def now():
    return datetime.now(timezone.utc).isoformat()

def context(env):
    sha = gate.trusted_context(env)
    gate.require(env.get('GITHUB_WORKFLOW_REF') == gate.REPOSITORY + '/.github/workflows/deploy-public-production.yml@refs/heads/main', 'writer_workflow_rejected')
    gate.require(env.get('OUTPOST_PRODUCTION_WRITER_ENABLED') == '1', 'writer_activation_missing')
    gate.require(env.get('GITHUB_RUN_ATTEMPT') == '1', 'rerun_inspect_only_no_replay')
    gate.require(re.fullmatch(r'[1-9][0-9]*', env.get('GITHUB_RUN_ID', '')) is not None, 'invalid_run_identity')
    gate.require(re.fullmatch(r'[1-9][0-9]*', env.get('GITHUB_RUN_NUMBER', '')) is not None, 'invalid_run_number')
    gate.require(env.get('GITHUB_ACTIONS') == 'true' and env.get('RUNNER_OS') == 'Linux', 'protected_linux_ci_required')
    return sha

def uuid(value):
    gate.require(isinstance(value, str) and re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', value) is not None, 'invalid_deployment_id')
    return value

def source_metadata(deployment):
    return deployment.get('deployment_trigger', {}).get('metadata', {})

def inventory_valid(items):
    gate.require(isinstance(items, list) and len({uuid(item.get('id')) for item in items}) == len(items), 'invalid_deployment_inventory')
    gate.require(all(item.get('latest_stage', {}).get('status') in TERMINAL for item in items if item.get('environment') == 'production'), 'other_production_deployment_in_flight')

def project_digest(project):
    # Hash normalized metadata only; no encrypted values are available or stored.
    return digest(gate.stable_project(project))

def canonical(project):
    item = project.get('canonical_deployment') or {}
    metadata = source_metadata(item)
    gate.require(item.get('environment') == 'production' and item.get('latest_stage', {}).get('status') == 'success' and
                 metadata.get('branch') == 'main' and metadata.get('commit_dirty') is False and
                 re.fullmatch(r'[a-f0-9]{40}', metadata.get('commit_hash', '')) is not None, 'successful_production_baseline_required')
    uuid(item.get('id'))
    gate.require(gate.sanitized(item.get('env_vars', {})) == gate.sanitized(project['deployment_configs']['production'].get('env_vars', {})), 'baseline_environment_mismatch')
    return item

def manifest(root, sha):
    listing = subprocess.check_output(['git', 'ls-tree', '-rz', sha, '--', 'site'], cwd=root).split(b'\0')
    rows = []
    for record in filter(None, listing):
        descriptor, encoded_name = record.split(b'\t', 1)
        mode, kind, _ = descriptor.split()
        name = encoded_name.decode('utf-8')
        path = Path(name)
        gate.require(mode in (b'100644', b'100755') and kind == b'blob' and name.startswith('site/') and
                     not path.is_absolute() and '..' not in path.parts and '\\' not in name, 'unsafe_tracked_upload_path')
        file = root / path
        gate.require(file.is_file() and not any(p.is_symlink() for p in [file, *file.parents]), 'upload_symlink_or_missing_file')
        payload = file.read_bytes()
        blob = subprocess.check_output(['git', 'show', sha + ':' + name], cwd=root)
        gate.require(payload == blob, 'upload_not_reviewed_bytes')
        rows.append({'path': name, 'bytes': len(payload), 'sha256': digest(payload)})
    gate.require(rows, 'empty_site_package')
    return sorted(rows, key=lambda row: row['path'])

def external_path(root, file):
    resolved = file.resolve()
    gate.require(not resolved.is_relative_to(root.resolve()) and not any(p.is_symlink() for p in [file, *file.parents]), 'state_or_package_must_be_outside_checkout')
    return resolved

class Journal:
    """Fsync before mutation; atomic replace. No full project metadata or API logs."""
    def __init__(self, file, data):
        self.file, self.data = file, data

    @classmethod
    def create(cls, file, data):
        gate.require(not file.exists(), 'existing_attempt_inspect_no_replay')
        with file.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        return cls(file, data)

    def event(self, state, **details):
        self.data['events'].append({'at': now(), 'state': state, **details})
        self.data['state'] = state
        temporary = self.file.with_suffix('.next')
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(self.data, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.file)
        if os.name != 'nt':
            descriptor = os.open(self.file.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

def validate_journal(data, env):
    sha = context(env)
    value = validate_journal_evidence(data, sha, env['GITHUB_RUN_ID'])
    gate.require(value['configuration_sha256'] == APPROVED_CONFIG_HASH, 'current_journal_configuration_mismatch')
    return value


def validate_journal_evidence(data, sha, run_id):
    """Pure evidence validation; this does NOT authorize a publisher operation."""
    gate.require(isinstance(data, dict) and set(data) == {'schema', 'run_id', 'source_sha', 'configuration_sha256', 'package_sha256', 'project_sha256',
                              'baseline_id', 'baseline_sha', 'initial_ids', 'review', 'state', 'events'}, 'invalid_journal_schema')
    gate.require(type(data['schema']) is int and data['schema'] == 1 and data['run_id'] == run_id and data['source_sha'] == sha and
                 isinstance(data['configuration_sha256'], str) and data['configuration_sha256'] in EVIDENCE_CONFIG_HASHES and isinstance(data['events'], list) and
                 1 <= len(data['events']) <= 10 and all(isinstance(event, dict) for event in data['events']), 'journal_context_mismatch')
    for name in ('package_sha256', 'project_sha256'):
        gate.require(re.fullmatch(r'[a-f0-9]{64}', data[name]) is not None, 'invalid_journal_digest')
    uuid(data['baseline_id'])
    gate.require(re.fullmatch(r'[a-f0-9]{40}', data['baseline_sha']) is not None and isinstance(data['initial_ids'], list) and
                 len(set(data['initial_ids'])) == len(data['initial_ids']) and data['baseline_id'] in data['initial_ids'], 'invalid_journal_baseline')
    for identity in data['initial_ids']:
        uuid(identity)
    review = data['review']
    gate.require(isinstance(review, dict) and type(review.get('pr')) is int and review['pr'] > 0 and
                 isinstance(review.get('head_sha'), str) and
                 re.fullmatch(r'[a-f0-9]{40}', review['head_sha']) is not None,
                 'invalid_journal_review')
    if set(review) == {'pr', 'head_sha', 'owner_review_id'}:
        # Historical CODEOWNER-reviewed evidence keeps its exact immutable shape.
        gate.require(type(review['owner_review_id']) is int and review['owner_review_id'] > 0,
                     'invalid_journal_review')
    else:
        # Self-merged owner PR: explicit authorization, with no invented review ID.
        gate.require(set(review) == {'pr', 'head_sha', 'owner_review_id', 'authorization'} and
                     review['authorization'] == 'owner_self_merge' and review['owner_review_id'] is None,
                     'invalid_journal_review')
    allowed = {'prepared', 'upload_intent', 'upload_returned', 'upload_unknown', 'deployment_success',
               'live_intent', 'live_failed', 'live_pass', 'rollback_intent', 'rollback_unknown', 'rolled_back'}
    states = [item.get('state') for item in data['events']]
    gate.require(data['state'] in allowed and states and states[0] == 'prepared' and states[-1] == data['state'] and
                 all(state in allowed for state in states) and states.count('upload_intent') <= 1 and states.count('rollback_intent') <= 1,
                 'invalid_or_replayed_journal')
    transitions = {'prepared': {'upload_intent'}, 'upload_intent': {'upload_returned', 'upload_unknown'},
                   'upload_returned': {'deployment_success', 'upload_unknown'}, 'deployment_success': {'live_intent'},
                   'live_intent': {'live_pass', 'live_failed'}, 'live_failed': {'rollback_intent'},
                   'rollback_intent': {'rolled_back', 'rollback_unknown'}}
    gate.require(all(right in transitions.get(left, set()) for left, right in zip(states, states[1:])), 'invalid_journal_transition')
    event_fields = {'prepared': set(), 'upload_intent': set(), 'upload_returned': {'command_returned'},
                    'upload_unknown': set(), 'deployment_success': {'deployment_id'}, 'live_intent': set(),
                    'live_failed': {'deployment_id'}, 'live_pass': {'deployment_id'}, 'rollback_intent': set(),
                    'rolled_back': set(), 'rollback_unknown': set()}
    stamps, identities = [], set()
    for event in data['events']:
        gate.require(set(event) <= {'at', 'state', 'deployment_id', 'command_returned'} and isinstance(event.get('at'), str), 'unexpected_journal_event_data')
        gate.require(set(event) == {'at', 'state'} | event_fields[event['state']] and
                     ('command_returned' not in event or event['command_returned'] is True), 'invalid_journal_event_details')
        try:
            stamp = datetime.fromisoformat(event['at'].replace('Z', '+00:00'))
            gate.require(stamp.tzinfo is not None, 'invalid_journal_timestamp')
            stamps.append(stamp)
        except (TypeError, ValueError):
            raise gate.GateError('invalid_journal_timestamp') from None
        if 'deployment_id' in event:
            uuid(event['deployment_id'])
            identities.add(event['deployment_id'])
    gate.require(stamps == sorted(stamps) and len(identities) <= 1 and
                 not identities.intersection(data['initial_ids']), 'journal_order_or_deployment_mismatch')
    return data


def validate_historical_journal(data, metadata):
    # Evidence only: the surrounding current protected context is still required,
    # but resolved prior runs may carry the explicitly pinned legacy config.
    return validate_journal_evidence(data, context(metadata), metadata['GITHUB_RUN_ID'])


def history_clear(client, env, root):
    records = checkpoints.load_checked(root, env['GITHUB_SHA'], validate_journal_evidence)
    return history.assert_clear(client, env, validate_historical_journal, records,
                                recovery=history.recovery_marker(root))

class Clients(history.HistoryReads, gate.ReadOnlyClients):
    def __init__(self, env):
        super().__init__(env)
        self.github_token = env.get('GITHUB_TOKEN', '')
        gate.require(self.github_token, 'readonly_run_history_credential_missing')

    def inventory(self):
        # Pages rejects per_page=100. Scope to production: preview versions
        # cannot be rollback targets or competing production rollouts.
        # Never interpret a truncated/shifted page as a complete history.
        items, total, seen = [], None, set()
        for page in range(1, MAX_PRODUCTION_DEPLOYMENTS // PAGES_PER_PAGE + 1):
            response = self._json('https://api.cloudflare.com/client/v4' + self.base +
                                  '/deployments?env=production&per_page=' + str(PAGES_PER_PAGE) + '&page=' + str(page),
                                  {'Authorization': 'Bearer ' + self.token})
            gate.require(isinstance(response, dict) and response.get('success') is True and
                         isinstance(response.get('result'), list) and isinstance(response.get('result_info'), dict), 'inventory_read_failed')
            chunk = response['result']
            info = response['result_info']
            count = info.get('total_count')
            gate.require(type(count) is int and 0 <= count <= MAX_PRODUCTION_DEPLOYMENTS,
                         'inventory_too_large_or_invalid_manual_review_required')
            pages = (count + PAGES_PER_PAGE - 1) // PAGES_PER_PAGE
            gate.require(type(info.get('page')) is int and info['page'] == page and
                         type(info.get('per_page')) is int and info['per_page'] == PAGES_PER_PAGE and
                         type(info.get('count')) is int and info['count'] == len(chunk) and
                         type(info.get('total_pages')) is int and
                         info['total_pages'] in ((0, 1) if count == 0 else (pages,)) and
                         (total is None or total == count), 'inventory_pagination_drift_or_incomplete')
            total = count
            gate.require(len(chunk) == max(0, min(PAGES_PER_PAGE, total - len(items))), 'inventory_pagination_drift_or_incomplete')
            for item in chunk:
                gate.require(isinstance(item, dict) and item.get('environment') == 'production', 'inventory_scope_mismatch')
                identity = uuid(item.get('id'))
                gate.require(identity not in seen, 'inventory_duplicate_or_shifted_page')
                seen.add(identity)
            items.extend(chunk)
            if len(items) == total:
                return items
        raise gate.GateError('inventory_too_large_manual_review_required')

    def rollback(self, target):
        uuid(target)
        try:
            request = Request('https://api.cloudflare.com/client/v4' + self.base + '/deployments/' + target + '/rollback',
                              headers={'Authorization': 'Bearer ' + self.token}, method='POST')
            with build_opener(gate.NoRedirect).open(request, timeout=30) as response:
                # No retry on any response. Read-back determines actual acceptance.
                gate.require(response.status == 200, 'rollback_response_ambiguous')
        except Exception:
            raise gate.GateError('rollback_response_ambiguous') from None

def preflight(env, root, client, notification_mode=True, rollback_own_deployment=None):
    sha = context(env)
    # Different source commits cannot escape an older unresolved attempt.
    # This is transaction/replay evidence, never a CI quality PASS substitute.
    recovered_source = history_clear(client, env, root)
    config, config_hash = gate.local_source(root, sha)
    gate.require(config_hash == APPROVED_CONFIG_HASH and not (root / '.release-hold').exists(), 'approved_configuration_or_release_hold_rejected')
    review = gate.review_proof(client, sha, automatic=gate.automatic_approval_enabled(env))
    if notification_mode:
        gate.validate_notification_mode(client.health())
    project = client.pages()
    gate.validate_project(project, config, config_hash)
    items = client.inventory()
    inventory_valid(items)
    base = canonical(project)
    gate.require(base['id'] in {item['id'] for item in items}, 'canonical_not_in_inventory')
    if rollback_own_deployment is not None:
        # Rollback runs AFTER our upload. The canonical source must therefore
        # be our exact in-flight deployment, not the pre-upload recovery frontier.
        # The separate saved journal and baseline target are checked below.
        gate.require(base['id'] == rollback_own_deployment and
                     source_metadata(base).get('commit_hash') == sha and
                     source_metadata(base).get('branch') == 'main' and
                     source_metadata(base).get('commit_dirty') is False,
                     'rollback_current_deployment_not_proven')
    elif recovered_source is not None:
        # Normal plan/upload still REQUIRE the reviewed recovery baseline.
        gate.require(source_metadata(base).get('commit_hash') == recovered_source and
                     source_metadata(base).get('branch') == 'main' and
                     source_metadata(base).get('commit_dirty') is False,
                     'recovery_production_baseline_not_proven')
    return sha, config, config_hash, review, project, items

def prepare(env, root, file, client):
    external_path(root, file)
    gate.require(not file.exists(), 'existing_attempt_inspect_no_replay')
    sha, _, config_hash, review, project, items = preflight(env, root, client)
    gate.require(not any(source_metadata(item).get('commit_hash') == sha and item.get('environment') == 'production' for item in items), 'source_has_prior_attempt_inspect_only')
    rows = manifest(root, sha)
    baseline = canonical(project)
    data = {'schema': 1, 'run_id': env['GITHUB_RUN_ID'], 'source_sha': sha, 'configuration_sha256': config_hash,
            'package_sha256': digest(rows), 'project_sha256': project_digest(project), 'baseline_id': baseline['id'],
            'baseline_sha': source_metadata(baseline)['commit_hash'], 'initial_ids': sorted(item['id'] for item in items),
            'review': review, 'state': 'prepared', 'events': [{'at': now(), 'state': 'prepared'}]}
    validate_journal(data, env)
    return Journal.create(file, data)

def same_baseline(data, project, items):
    inventory_valid(items)
    gate.require(project_digest(project) == data['project_sha256'] and canonical(project)['id'] == data['baseline_id'] and
                 sorted(item['id'] for item in items) == data['initial_ids'], 'state_changed_since_saved_plan')

def upload_package(root, destination, sha, expected):
    destination = external_path(root, destination)
    for directory in destination.parents:
        gate.require(not any((directory / name).exists() for name in ('.env', '.dev.vars', 'wrangler.json', 'wrangler.jsonc', 'wrangler.toml')), 'ancestor_upload_configuration_rejected')
    rows = manifest(root, sha)
    gate.require(digest(rows) == expected and not destination.exists(), 'package_changed_or_already_exists')
    destination.mkdir()
    for row in rows:
        target = destination / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / row['path'], target)
    shutil.copyfile(root / 'wrangler.jsonc', destination / 'wrangler.jsonc')
    return destination

def verify_package(destination, expected):
    rows = []
    for file in sorted(destination.rglob('*')):
        gate.require(not file.is_symlink(), 'upload_symlink_rejected')
        if file.is_file():
            name = file.relative_to(destination).as_posix()
            payload = file.read_bytes()
            if name == 'wrangler.jsonc':
                gate.require(digest(payload) == APPROVED_CONFIG_HASH, 'upload_config_changed')
            else:
                gate.require(name.startswith('site/'), 'extra_upload_file')
                rows.append({'path': name, 'bytes': len(payload), 'sha256': digest(payload)})
    gate.require((destination / 'wrangler.jsonc').is_file() and digest(sorted(rows, key=lambda row: row['path'])) == expected, 'upload_bytes_changed')

def tool(env, root):
    binary = Path(env.get('OUTPOST_WRANGLER_JS', '')).resolve()
    gate.require(binary.is_file() and not binary.is_relative_to(root.resolve()), 'pinned_tool_missing')
    # Never use an interactive OAuth profile in CI; explicitly pass only dedicated API auth.
    version = subprocess.run(['node', str(binary), '--version'], capture_output=True, timeout=30, check=False,
                             env={'PATH': env.get('PATH', ''), 'WRANGLER_SEND_METRICS': 'false'})
    gate.require(version.returncode == 0 and re.search(rb'(?<![0-9])4\.142\.0(?![0-9])', version.stdout) is not None, 'pinned_tool_version_mismatch')
    return binary

def run_upload(env, binary, package, sha):
    child_env = {name: env[name] for name in ('PATH', 'HOME', 'TMPDIR', 'CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_API_TOKEN') if name in env}
    child_env.update({'WRANGLER_SEND_METRICS': 'false', 'CI': 'true', 'XDG_CONFIG_HOME': str(package.parent / 'outpost-isolated-tool-profile')})
    return subprocess.run(['node', str(binary), 'pages', 'deploy', 'site', '--project-name', gate.PROJECT,
                           '--branch', 'main', '--commit-hash', sha, '--commit-dirty=false', '--commit-message', 'Reviewed source ' + sha],
                          cwd=package, env=child_env, capture_output=True, timeout=240, check=False).returncode

def resolve(data, project, items):
    inventory_valid(items)
    fresh = [item for item in items if item['id'] not in data['initial_ids'] and item.get('environment') == 'production']
    gate.require(len(fresh) == 1, 'ambiguous_or_intervening_deployment_inspect_only')
    item = fresh[0]
    gate.require(source_metadata(item).get('commit_hash') == data['source_sha'] and
                 source_metadata(item).get('branch') == 'main' and source_metadata(item).get('commit_dirty') is False,
                 'unrelated_rollout_do_not_overwrite')
    gate.require(project_digest(project) == data['project_sha256'], 'configuration_drift_inspect_only')
    identity = gate.validate_deployment(project, data['source_sha'], item['id'])
    return identity

def wait_for_publication(data, client, seconds):
    gate.require(0 <= seconds <= 240, 'invalid_publication_wait')
    deadline = time.monotonic() + seconds
    while True:
        project, items = client.pages(), client.inventory()
        gate.require(project_digest(project) == data['project_sha256'], 'configuration_drift_inspect_only')
        fresh = [item for item in items if item['id'] not in data['initial_ids'] and item.get('environment') == 'production']
        gate.require(len(fresh) <= 1, 'intervening_deployment_inspect_only')
        if fresh:
            item = fresh[0]
            gate.require(source_metadata(item).get('commit_hash') == data['source_sha'] and source_metadata(item).get('branch') == 'main' and
                         source_metadata(item).get('commit_dirty') is False, 'unrelated_rollout_do_not_overwrite')
            if item.get('latest_stage', {}).get('status') in TERMINAL:
                return resolve(data, project, items)
        gate.require(time.monotonic() < deadline, 'publication_not_resolved_inspect_only')
        gate.require(client.github('/git/ref/heads/main')['object']['sha'] == data['source_sha'], 'main_advanced_during_upload_wait')
        gate.validate_notification_mode(client.health())
        time.sleep(5)

def execute(env, root, journal, package, client, uploader=run_upload, wait_seconds=0):
    data = validate_journal(journal.data, env)
    gate.require(data['state'] == 'prepared' and not any(item['state'] == 'upload_intent' for item in data['events']), 'upload_already_requested_inspect_only')
    receipt = env.get('OUTPOST_SAVED_PLAN_URL', '')
    gate.require(re.fullmatch(r'https://github\.com/' + gate.REPOSITORY + '/actions/runs/' + env['GITHUB_RUN_ID'] + r'/artifacts/[1-9][0-9]*', receipt) is not None, 'durable_plan_artifact_required')
    sha, _, _, review, project, items = preflight(env, root, client)
    gate.require(review == data['review'], 'review_changed_since_plan')
    same_baseline(data, project, items)
    binary = tool(env, root)
    upload_package(root, package, sha, data['package_sha256'])
    verify_package(package, data['package_sha256'])
    history_clear(client, env, root)
    # Last read immediately before recording intent and mutating. Provider offers no CAS.
    same_baseline(data, client.pages(), client.inventory())
    gate.require(client.github('/git/ref/heads/main')['object']['sha'] == sha, 'main_advanced_before_upload')
    gate.validate_notification_mode(client.health())
    journal.event('upload_intent')
    try:
        uploader(env, binary, package, sha)
        journal.event('upload_returned', command_returned=True)
    except Exception:
        journal.event('upload_unknown')
        raise gate.GateError('upload_response_unknown_inspect_only') from None
    # Never infer publication from exit status or text printed by Wrangler.
    try:
        identity = wait_for_publication(data, client, wait_seconds)
    except Exception:
        journal.event('upload_unknown')
        raise gate.GateError('deployment_not_confirmed_inspect_only') from None
    # This records provider deployment identity, NOT live acceptance. Health/main
    # are rechecked before any canonical GET in the next phase; a broken new
    # health handler must still leave an identified code-only rollback target.
    journal.event('deployment_success', deployment_id=identity)
    return identity

def deployment_id(data):
    identities = {event['deployment_id'] for event in data['events'] if event['state'] == 'deployment_success'}
    gate.require(len(identities) == 1, 'verified_own_deployment_missing')
    return identities.pop()

def live_environment(env):
    # Allowlist, not a secret-name denylist: unknown/private/proxy/profile vars
    # must not leak into a verifier. This does not sandbox filesystem access.
    allowed = LIVE_RUNTIME_ENV | LIVE_TUNING_ENV
    return {name: value for name, value in env.items() if name.upper() in allowed}

def run_live(root, command):
    import sys
    gate.require(command in LIVE_COMMANDS, 'unexpected_live_verifier')
    result = subprocess.run([sys.executable, str(root / 'scripts' / command)], cwd=root,
                            env=live_environment(os.environ), capture_output=True, timeout=240, check=False)
    if result.returncode != 0:
        # Only the reviewed verifier basename and integer status are logged.
        # stdout/stderr are intentionally discarded: live HTTP responses may
        # carry sensitive context and must never leak into GitHub Actions logs.
        print(f'Live verifier: FAIL — {command} (exit {result.returncode})', flush=True)
        return False
    print(f'Live verifier: PASS — {command}', flush=True)
    return True

def verify_live(env, root, journal, client, runner=run_live):
    data = validate_journal(journal.data, env)
    gate.require(data['state'] == 'deployment_success', 'live_verification_not_ready')
    own = deployment_id(data)
    journal.event('live_intent')
    try:
        history_clear(client, env, root)
        gate.verify_current(env, root, client)
        gate.require(resolve(data, client.pages(), client.inventory()) == own, 'canonical_changed_before_live')
        for command in LIVE_COMMANDS:
            # No canonical GET if mode/source/deployment changed between validators.
            gate.verify_current(env, root, client)
            gate.require(resolve(data, client.pages(), client.inventory()) == own, 'canonical_changed_during_live')
            # A single transient public-GET failure must not force a rollback
            # after an otherwise verified upload. Retry ONLY this same
            # credential-free verifier; never repeat the Cloudflare upload.
            if not runner(root, command):
                gate.verify_current(env, root, client)
                gate.require(resolve(data, client.pages(), client.inventory()) == own,
                             'canonical_changed_before_live_retry')
                print('Live verifier: one read-only retry — ' + command, flush=True)
                if runner is run_live:
                    time.sleep(3)
                gate.verify_current(env, root, client)
                gate.require(resolve(data, client.pages(), client.inventory()) == own,
                             'canonical_changed_during_live_retry')
                gate.require(runner(root, command), 'critical_live_verification_failed')
        gate.verify_current(env, root, client)
        journal.event('live_pass', deployment_id=own)
    except Exception:
        journal.event('live_failed', deployment_id=own)
        raise gate.GateError('live_verification_failed_or_unknown') from None

def rollback(env, root, journal, client):
    data = validate_journal(journal.data, env)
    gate.require(env.get('OUTPOST_PRODUCTION_ROLLBACK_ENABLED') == '1', 'rollback_activation_missing')
    gate.require(data['state'] == 'live_failed' and not any(event['state'] == 'rollback_intent' for event in data['events']), 'rollback_not_ready_or_already_requested')
    own = deployment_id(data)
    # Broken current health is itself a possible rollback reason; do not require
    # a successful live endpoint to restore the known-good saved code.
    sha, _, _, _, project, items = preflight(env, root, client, notification_mode=False,
                                             rollback_own_deployment=own)
    gate.require(sha == data['source_sha'] and resolve(data, project, items) == own, 'rollback_would_overwrite_other_rollout')
    history_clear(client, env, root)
    target = client.pages('/deployments/' + data['baseline_id'])
    gate.require(target.get('id') == data['baseline_id'] and target.get('environment') == 'production' and
                 target.get('latest_stage', {}).get('status') == 'success' and source_metadata(target).get('commit_hash') == data['baseline_sha'] and
                 gate.sanitized(target.get('env_vars', {})) == gate.sanitized(project['deployment_configs']['production'].get('env_vars', {})), 'rollback_target_changed')
    gate.require(resolve(data, client.pages(), client.inventory()) == own, 'rollout_changed_before_rollback')
    journal.event('rollback_intent')
    try:
        client.rollback(data['baseline_id'])
        after = client.pages()
        after_items = client.inventory()
        inventory_valid(after_items)
        gate.require(sorted(item['id'] for item in after_items) == sorted(item['id'] for item in items) and
                     project_digest(after) == data['project_sha256'] and canonical(after)['id'] == data['baseline_id'] and
                     source_metadata(canonical(after))['commit_hash'] == data['baseline_sha'], 'rollback_readback_mismatch')
        journal.event('rolled_back')
    except Exception:
        journal.event('rollback_unknown')
        raise gate.GateError('rollback_unknown_inspect_only') from None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', nargs='?', choices=['plan', 'execute', 'verify-live', 'rollback'])
    parser.add_argument('--journal', type=Path)
    parser.add_argument('--package', type=Path)
    args = parser.parse_args()
    if args.operation is None:
        from verify_cloudflare_config import main as config_check
        gate.require(config_check() == 0, 'offline_configuration_failed')
        print('Publisher: OFFLINE ONLY; upload, live checks, rollback and activation NOT performed')
        return 0
    context(os.environ)  # Before obtaining any operational credential or network client.
    gate.require(args.journal is not None and args.journal.parent.is_dir(), 'journal_directory_missing')
    external_path(gate.ROOT, args.journal)
    client = Clients(os.environ)
    if args.operation == 'plan':
        journal = prepare(os.environ, gate.ROOT, args.journal, client)
    else:
        journal = Journal(args.journal, validate_journal(json.loads(args.journal.read_text()), os.environ))
        if args.operation == 'execute':
            gate.require(args.package is not None, 'package_directory_missing')
            execute(os.environ, gate.ROOT, journal, args.package, client, wait_seconds=240)
        elif args.operation == 'verify-live':
            verify_live(os.environ, gate.ROOT, journal, client)
        else:
            rollback(os.environ, gate.ROOT, journal, client)
    print(json.dumps({'state': journal.data['state'], 'source_sha': journal.data['source_sha'], 'release_announced': False}))
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        code = str(error) if isinstance(error, gate.GateError) and re.fullmatch(r'[a-z_]+', str(error)) else 'publisher_failed_inspect_state'
        print('Publisher: BLOCKED — ' + code)
        raise SystemExit(1)
