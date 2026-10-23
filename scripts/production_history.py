"""Read-only cross-source publication interlock; no repair, replay, or writes.

Only the existing writer's run metadata, skipped-job proof, exact failed-before-
intent step proof and two immutable journal artifacts are read. CI conclusions
are not substitutes for live proof. Missing evidence blocks mutation unless a
complete provider proof establishes that upload never started. Unknown attempts
remain blocked.
"""
from io import BytesIO
import hashlib
import json
import re
from urllib.error import HTTPError, URLError
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
import production_deployment_gate as gate

WORKFLOW = 'deploy-public-production.yml'
WORKFLOW_PATH = '.github/workflows/' + WORKFLOW
# Read-only provider identity recorded before any activation. Replacing/deleting
# this workflow or its first run requires a separate reviewed recovery decision.
WORKFLOW_ID = 382921011
REPOSITORY_ID = 1415330072
FIRST_RUN_ID = 38360609329
FIRST_SOURCE = '3f319aa5ff18b42b69c44da4b3cabcde429679b7'
MAX_RUNS = 1000
MAX_ARCHIVE = 256 * 1024
MAX_JOURNAL = 128 * 1024
JOURNAL_NAME = 'outpost-production-journal.json'


def positive(value):
    gate.require(type(value) is int and value > 0, 'invalid_history_identity')
    return value


def artifact_name(kind, run):
    gate.require(kind in ('intent', 'result'), 'invalid_history_artifact_kind')
    return 'outpost-production-' + kind + '-' + run['head_sha'] + '-' + str(run['id'])


def unique_json_pairs(pairs):
    result = {}
    for name, value in pairs:
        gate.require(name not in result, 'duplicate_journal_json_key')
        result[name] = value
    return result


def archive_journal(payload, artifact):
    gate.require(isinstance(payload, bytes) and 0 < len(payload) <= MAX_ARCHIVE,
                 'history_archive_size_rejected')
    gate.require(artifact.get('digest') == 'sha256:' + hashlib.sha256(payload).hexdigest(),
                 'history_archive_digest_mismatch')
    try:
        with ZipFile(BytesIO(payload)) as archive:
            entries = archive.infolist()
            gate.require(len(entries) == 1, 'history_archive_extra_entries')
            file = entries[0]
            gate.require(file.filename == JOURNAL_NAME and not file.is_dir() and
                         0 < file.file_size <= MAX_JOURNAL and not file.flag_bits & 1 and
                         file.compress_type in (ZIP_STORED, ZIP_DEFLATED) and
                         (file.external_attr >> 16) & 0o170000 in (0, 0o100000),
                         'history_archive_entry_rejected')
            raw = archive.read(file)
            gate.require(len(raw) <= MAX_JOURNAL, 'history_journal_too_large')
            value = json.loads(raw, object_pairs_hook=unique_json_pairs)
            gate.require(isinstance(value, dict), 'history_journal_not_object')
            return value
    except gate.GateError:
        raise
    except Exception:
        raise gate.GateError('history_archive_unreadable') from None


def download_location(value):
    gate.require(isinstance(value, str) and len(value) < 8192, 'history_download_location_rejected')
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError:
        raise gate.GateError('history_download_location_rejected') from None
    host = url.hostname or ''
    gate.require(url.scheme == 'https' and not url.username and not url.password and
                 port in (None, 443) and not url.fragment and
                 (host.endswith('.blob.core.windows.net') or host.endswith('.actions.githubusercontent.com')),
                 'history_download_location_rejected')
    return value


class HistoryReads:
    """Mixin for the publisher's existing read-only Actions credential."""
    def history_json(self, suffix):
        gate.require(suffix == '/actions/workflows/' + WORKFLOW or
                     re.fullmatch(r'/actions/workflows/' + re.escape(WORKFLOW) + r'/runs\?per_page=100&page=[1-9][0-9]*', suffix) or
                     re.fullmatch(r'/actions/runs/[1-9][0-9]*/artifacts\?per_page=100', suffix) or
                     re.fullmatch(r'/actions/runs/[1-9][0-9]*/attempts/1/jobs\?per_page=100', suffix),
                     'unapproved_history_read')
        return self._json('https://api.github.com/repos/' + gate.REPOSITORY + suffix,
                          {'Authorization': 'Bearer ' + self.github_token,
                           'Accept': 'application/vnd.github+json', 'User-Agent': 'OutPOSt-Publisher-History-Guard'})

    def publication_runs(self):
        workflow = self.history_json('/actions/workflows/' + WORKFLOW)
        gate.require(workflow.get('id') == WORKFLOW_ID and workflow.get('path') == WORKFLOW_PATH,
                     'publisher_workflow_identity_changed')
        rows, count = [], None
        for page in range(1, MAX_RUNS // 100 + 1):
            value = self.history_json('/actions/workflows/' + WORKFLOW + '/runs?per_page=100&page=' + str(page))
            total, chunk = value.get('total_count'), value.get('workflow_runs')
            gate.require(type(total) is int and 0 < total <= MAX_RUNS and isinstance(chunk, list) and
                         len(chunk) <= 100 and (count is None or count == total), 'publication_history_incomplete')
            count = total
            rows.extend(chunk)
            if len(chunk) < 100 or len(rows) == count:
                gate.require(len(rows) == count, 'publication_history_incomplete')
                return rows
        raise gate.GateError('publication_history_requires_manual_review')

    def publication_artifacts(self, run):
        identity = positive(run['id'])
        value = self.history_json('/actions/runs/' + str(identity) + '/artifacts?per_page=100')
        items = value.get('artifacts')
        gate.require(type(value.get('total_count')) is int and isinstance(items, list) and
                     value['total_count'] == len(items) and len(items) <= 2, 'publication_artifact_history_incomplete')
        return items

    def skipped_publication_jobs(self, run):
        identity = positive(run['id'])
        value = self.history_json('/actions/runs/' + str(identity) + '/attempts/1/jobs?per_page=100')
        jobs = value.get('jobs')
        gate.require(type(value.get('total_count')) is int and isinstance(jobs, list) and
                     value['total_count'] == len(jobs) and len(jobs) == 3, 'skipped_publication_proof_incomplete')
        return jobs

    def publication_journal(self, artifact):
        identity = positive(artifact['id'])
        endpoint = 'https://api.github.com/repos/' + gate.REPOSITORY + '/actions/artifacts/' + str(identity) + '/zip'
        request = Request(endpoint, headers={'Authorization': 'Bearer ' + self.github_token,
                          'Accept': 'application/vnd.github+json', 'User-Agent': 'OutPOSt-Publisher-History-Guard'}, method='GET')
        # Retry only transient read failures. Every attempt re-requests a fresh
        # short-lived signed URL; no credentials go to storage, and an ambiguous
        # response never authorizes any deployment.
        payload = None
        for attempt in range(3):
            try:
                try:
                    with build_opener(gate.NoRedirect).open(request, timeout=20):
                        raise gate.GateError('history_download_redirect_required')
                except HTTPError as error:
                    if error.code != 302:
                        if error.code in (429, 500, 502, 503, 504):
                            raise URLError('transient_git_archive_redirect')
                        raise gate.GateError('history_download_unavailable') from None
                    location = download_location(error.headers.get('Location'))
                # Never forward GitHub Authorization to signed storage; no
                # implicit second redirect or unbounded extraction.
                with build_opener(gate.NoRedirect).open(Request(location, method='GET'), timeout=20) as response:
                    gate.require(response.status == 200, 'history_download_unavailable')
                    payload = response.read(MAX_ARCHIVE + 1)
                break
            except HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504):
                    raise gate.GateError('history_download_unavailable') from None
            except (URLError, TimeoutError, OSError):
                pass
            except gate.GateError:
                raise
            except Exception:
                raise gate.GateError('history_download_unavailable') from None
            if attempt < 2:
                time.sleep(attempt + 1)
        gate.require(payload is not None, 'history_download_unavailable')
        return archive_journal(payload, artifact)


RUN_FIELDS = ('id', 'run_number', 'head_sha', 'head_branch', 'run_attempt', 'workflow_id',
              'path', 'event', 'status', 'conclusion')
JOB_FIELDS = ('id', 'name', 'run_id', 'run_attempt', 'head_sha', 'status', 'conclusion',
              'steps', 'runner_id', 'runner_name')
ARTIFACT_FIELDS = ('id', 'name', 'digest', 'size_in_bytes', 'workflow_run')
IDENTITY_FIELDS = ('id', 'head_sha', 'head_branch', 'repository_id', 'head_repository_id')


def run_projection(run):
    return {**{key: run.get(key) for key in RUN_FIELDS},
            'repository': {key: run.get('repository', {}).get(key) for key in ('id', 'full_name')},
            'head_repository': {'id': run.get('head_repository', {}).get('id')}}


def validate_inventory(runs):
    gate.require(isinstance(runs, list) and 0 < len(runs) <= MAX_RUNS, 'publication_history_incomplete')
    for run in runs:
        gate.require(isinstance(run, dict), 'invalid_history_run')
        positive(run.get('id'))
        positive(run.get('run_number'))
        gate.require(run.get('workflow_id') == WORKFLOW_ID and run.get('path') == WORKFLOW_PATH and
                     run.get('repository', {}).get('id') == REPOSITORY_ID and
                     run.get('repository', {}).get('full_name') == gate.REPOSITORY and
                     run.get('head_repository', {}).get('id') == REPOSITORY_ID and
                     run.get('head_branch') == 'main' and
                     run.get('run_attempt') == 1 and type(run.get('run_attempt')) is int and
                     run.get('event') in ('push', 'workflow_dispatch') and
                     isinstance(run.get('head_sha'), str) and re.fullmatch(r'[a-f0-9]{40}', run['head_sha']),
                     'foreign_or_replayed_publication_history')
    gate.require(len({run['id'] for run in runs}) == len(runs) and
                 sorted(run['run_number'] for run in runs) == list(range(1, len(runs) + 1)),
                 'deleted_or_duplicate_publication_history')
    first = next(run for run in runs if run['run_number'] == 1)
    gate.require(first['id'] == FIRST_RUN_ID and first['head_sha'] == FIRST_SOURCE, 'publication_history_anchor_missing')


def merge_runs(live, records):
    gate.require(isinstance(live, list) and live and len(live) <= MAX_RUNS and
                 all(isinstance(run, dict) for run in live), 'publication_history_incomplete')
    gate.require(len({positive(run.get('id')) for run in live}) == len(live), 'deleted_or_duplicate_publication_history')
    archived = {record['run']['id']: record['run'] for record in records}
    combined = dict(archived)
    for run in live:
        if run['id'] in archived:
            gate.require(run_projection(run) == archived[run['id']], 'checkpoint_live_run_mismatch')
        combined[run['id']] = run
    runs = list(combined.values())
    validate_inventory(runs)
    return runs


def validate_runs(runs, env):
    validate_inventory(runs)
    current = [run for run in runs if str(run['id']) == env['GITHUB_RUN_ID']]
    gate.require(len(current) == 1 and str(current[0]['run_number']) == env.get('GITHUB_RUN_NUMBER') and
                 current[0]['head_sha'] == env['GITHUB_SHA'] and current[0].get('head_branch') == 'main' and
                 current[0].get('status') == 'in_progress' and current[0].get('conclusion') is None,
                 'current_publication_run_not_proven')
    gate.require(sum(run['head_sha'] == env['GITHUB_SHA'] for run in runs) == 1,
                 'prior_run_for_source_inspect_only')
    return current[0]


def validate_artifact(artifact, run, kind):
    gate.require(isinstance(artifact, dict), 'invalid_history_artifact')
    positive(artifact.get('id'))
    gate.require(artifact.get('name') == artifact_name(kind, run) and artifact.get('expired') is False and
                 type(artifact.get('size_in_bytes')) is int and 0 < artifact['size_in_bytes'] <= MAX_ARCHIVE and
                 isinstance(artifact.get('digest'), str) and re.fullmatch(r'sha256:[a-f0-9]{64}', artifact['digest']),
                 'missing_expired_or_malformed_publication_artifact')
    identity = artifact.get('workflow_run') or {}
    gate.require(identity.get('id') == run['id'] and identity.get('head_sha') == run['head_sha'] and
                 identity.get('head_branch') == 'main' and identity.get('repository_id') == REPOSITORY_ID and
                 identity.get('head_repository_id') == REPOSITORY_ID, 'publication_artifact_from_wrong_run')


def skipped_without_intent(client, run, jobs=None):
    if jobs is None:
        jobs = client.skipped_publication_jobs(run)
    gate.require(isinstance(jobs, list) and len(jobs) == 3 and all(isinstance(job, dict) for job in jobs) and
                 len({positive(job.get('id')) for job in jobs}) == 3 and sorted(job.get('name', '') for job in jobs) ==
                 ['browser-quality', 'publish', 'static-quality'], 'skipped_publication_proof_incomplete')
    for job in jobs:
        gate.require(job.get('run_id') == run['id'] and job.get('run_attempt') == 1 and
                     job.get('head_sha') == run['head_sha'] and job.get('status') == 'completed',
                     'skipped_publication_proof_incomplete')
    job = next(job for job in jobs if job['name'] == 'publish')
    # Cancelling an environment wait yields a cancelled job, not a skipped job.
    # Admit it only with the same provider proof that no runner ever started.
    gate.require((job.get('conclusion') == 'skipped' or
                  job.get('conclusion') == 'cancelled' and run.get('conclusion') == 'cancelled') and job.get('steps') == [] and
                 (job.get('runner_id') is None or type(job.get('runner_id')) is int and job['runner_id'] == 0) and
                 not job.get('runner_name'),
                 'missing_publication_journal_inspect_only')
    return {**{key: job.get(key) for key in JOB_FIELDS}, 'runner_name': None}


# A historical writer may fail at the READ-ONLY plan step before it can save
# either artifact. Exact provider step evidence, not the run conclusion alone,
# proves no upload or rollback action started. Every other failed run blocks.
PREFLIGHT_STEPS = {
    6: ('Verify Telegram transport in the actual offline edge runtime', 'success'),
    7: ('Prepare read-only deployment plan', 'failure'),
    8: ('Persist intent before any upload', 'skipped'),
    9: ('Upload once and require actual matching canonical deployment', 'skipped'),
    10: ('Verify all live contracts only after exact deployment proof', 'skipped'),
    11: ('Restore only our saved code after a critical live failure', 'skipped'),
    12: ('Save final journal even on failure; never upload credentials or raw logs', 'skipped'),
    13: ('Confirm future releases only after accepted live publication', 'skipped'),
}
PREFLIGHT_PROOF_FIELDS = ('id', 'name', 'run_id', 'run_attempt', 'head_sha', 'status', 'conclusion', 'steps')
PREFLIGHT_STEP_FIELDS = ('number', 'name', 'status', 'conclusion')


def validate_preflight_proof(run, proof):
    gate.require(isinstance(proof, dict) and set(proof) == set(PREFLIGHT_PROOF_FIELDS) and
                 type(proof['id']) is int and proof['id'] > 0 and
                 proof['name'] == 'publish' and proof['run_id'] == run['id'] and
                 type(proof['run_attempt']) is int and proof['run_attempt'] == 1 and
                 proof['head_sha'] == run['head_sha'] and
                 proof['status'] == 'completed' and proof['conclusion'] == 'failure' and
                 run['status'] == 'completed' and run['conclusion'] == 'failure' and
                 isinstance(proof['steps'], list) and len(proof['steps']) == 13,
                 'unproven_preflight_failure')
    for number, step in enumerate(proof['steps'], 1):
        gate.require(isinstance(step, dict) and set(step) == set(PREFLIGHT_STEP_FIELDS) and
                     type(step['number']) is int and step['number'] == number and
                     step['status'] == 'completed', 'unproven_preflight_failure')
        if number < 6:
            gate.require(step['conclusion'] == 'success', 'unproven_preflight_failure')
        else:
            required_name, required_conclusion = PREFLIGHT_STEPS[number]
            gate.require(step['name'] == required_name and step['conclusion'] == required_conclusion,
                         'unproven_preflight_failure')
    return proof


def preflight_failed_without_intent(client, run, jobs=None):
    if jobs is None:
        jobs = client.skipped_publication_jobs(run)
    gate.require(isinstance(jobs, list) and len(jobs) == 3 and
                 sorted(job.get('name') for job in jobs if isinstance(job, dict)) ==
                 ['browser-quality', 'publish', 'static-quality'], 'unproven_preflight_failure')
    for job in jobs:
        gate.require(job.get('run_id') == run['id'] and job.get('run_attempt') == 1 and
                     job.get('head_sha') == run['head_sha'] and job.get('status') == 'completed' and
                     (job.get('conclusion') == 'failure' if job['name'] == 'publish'
                      else job.get('conclusion') == 'success'), 'unproven_preflight_failure')
    publisher = next(job for job in jobs if job['name'] == 'publish')
    steps = publisher.get('steps')
    gate.require(isinstance(steps, list) and len(steps) >= 13, 'unproven_preflight_failure')
    # Steps 1..13 are the guarded publishing sequence. The provider may include
    # later post-job cleanup, which does not change an unexecuted upload.
    first = steps[:13]
    proof = {key: publisher.get(key) for key in PREFLIGHT_PROOF_FIELDS if key != 'steps'}
    proof['steps'] = [{field: step.get(field) for field in PREFLIGHT_STEP_FIELDS} for step in first]
    return validate_preflight_proof(run, proof)


def resolved_journals(intent, result, run, env, validator):
    previous_env = {**env, 'GITHUB_SHA': run['head_sha'], 'GITHUB_RUN_ID': str(run['id']),
                    'GITHUB_RUN_NUMBER': str(run['run_number'])}
    validator(intent, previous_env)
    validator(result, previous_env)
    gate.require(intent['state'] == 'prepared' and len(intent['events']) == 1 and
                 result['events'][:1] == intent['events'] and
                 {key: value for key, value in intent.items() if key not in ('state', 'events')} ==
                 {key: value for key, value in result.items() if key not in ('state', 'events')},
                 'publication_journal_link_mismatch')
    gate.require(result['state'] in ('prepared', 'live_pass', 'rolled_back'),
                 'unresolved_prior_publication_inspect_only')
    if result['state'] == 'live_pass':
        gate.require(run['conclusion'] == 'success', 'publication_result_conclusion_mismatch')
    if result['state'] == 'rolled_back':
        gate.require(run['conclusion'] == 'failure', 'publication_result_conclusion_mismatch')


def read_resolved_record(client, run, env, validator):
    """Provider-verified safe projection, shared by runtime and read-only capture."""
    gate.require(run.get('status') == 'completed' and run.get('conclusion') in
                     ('success', 'failure', 'cancelled', 'timed_out', 'skipped', 'action_required', 'neutral'),
                     'unfinished_prior_publication_inspect_only')
    artifacts = client.publication_artifacts(run)
    if not artifacts:
        jobs = client.skipped_publication_jobs(run)
        publishers = [job for job in jobs if isinstance(job, dict) and job.get('name') == 'publish']
        gate.require(len(publishers) == 1, 'missing_publication_journal_inspect_only')
        if publishers[0].get('conclusion') == 'failure':
            return {'run': run_projection(run), 'kind': 'preflight_failed',
                    'proof': preflight_failed_without_intent(client, run, jobs)}
        return {'run': run_projection(run), 'kind': 'skipped',
                'proof': skipped_without_intent(client, run, jobs)}
    gate.require(len(artifacts) == 2 and len({item.get('id') for item in artifacts}) == 2,
                     'missing_or_duplicate_publication_journal')
    proof = []
    for kind in ('intent', 'result'):
        matches = [item for item in artifacts if item.get('name') == artifact_name(kind, run)]
        gate.require(len(matches) == 1, 'missing_or_duplicate_publication_journal')
        artifact = matches[0]
        validate_artifact(artifact, run, kind)
        journal = client.publication_journal(artifact)
        safe = {key: artifact[key] for key in ARTIFACT_FIELDS}
        safe['workflow_run'] = {key: artifact['workflow_run'][key] for key in IDENTITY_FIELDS}
        proof.append({**safe, 'journal': journal})
    resolved_journals(*(item['journal'] for item in proof), run, env, validator)
    return {'run': run_projection(run), 'kind': 'journal', 'proof': proof}


# Incident 2026-10-23: GitHub removed run #18 journal ZIPs before the
# owner-reviewed checkpoint could capture them. Never invent a run #18 journal.
# A later, independently successful *live* deployment is the reconciled new
# frontier; the historical gap remains explicitly recorded as unknown.
# This whitelist is deliberately not user-configurable or a catch-all bypass.
RECOVERY_FRONTIER = {
    'run_number': 42,
    'id': 39732581172,
    'head_sha': 'ddd41915cb845c1448a519959f671d8b616b4065',
    'deployment_id': '3d034a08-be56-4ef9-8a73-f1275a936607',
    'intent_id': 12405542870,
    'intent_digest': 'sha256:4b41a6366986ab372544cd6f953c0d2219eb7634cbcea105e9d7688b998ead48',
    'result_id': 12406083047,
    'result_digest': 'sha256:60447a2bdcb6f7686c08a137ddcc75a36be6bee2b9828e7466a757a371325ebc',
}
RECOVERY_MARKER = 'release/production-history-reconciliation.json'


def recovery_marker(root):
    """Owner-reviewed explicit one-time reconciliation, never an env toggle."""
    from pathlib import Path
    import subprocess
    root = Path(root)
    path = root / RECOVERY_MARKER
    if not path.exists():
        return False
    gate.require(path.is_file() and not any(item.is_symlink() for item in [path, *path.parents]),
                 'recovery_witness_not_regular_file')
    try:
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, timeout=10,
                                      stderr=subprocess.DEVNULL).decode().strip()
        tracked = subprocess.check_output(['git', 'show', sha + ':' + RECOVERY_MARKER], cwd=root,
                                          timeout=10, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        raise gate.GateError('recovery_witness_not_reviewed') from None
    gate.require(path.read_bytes() == tracked, 'recovery_witness_not_reviewed')
    try:
        value = json.loads(tracked, object_pairs_hook=unique_json_pairs)
    except Exception:
        raise gate.GateError('recovery_witness_invalid') from None
    required = {
        'schema': 1,
        'incident': 'expired_production_journal_run_18_not_reconstructed',
        'first_unarchived_run_number': 17,
        'last_reconciled_run_number': 42,
        'frontier': RECOVERY_FRONTIER,
        'resolution': 'last_successful_live_deployment_is_new_frontier_only',
    }
    gate.require(value == required, 'recovery_witness_changed')
    return True


def verified_recovery_frontier(client, run, env, validator):
    """Require exact trusted run + provider evidence; never treat CI green as a journal."""
    anchor = RECOVERY_FRONTIER
    gate.require(run['run_number'] == anchor['run_number'] and
                 run['id'] == anchor['id'] and
                 run['head_sha'] == anchor['head_sha'] and
                 run['status'] == 'completed' and run['conclusion'] == 'success',
                 'recovery_anchor_identity_mismatch')
    artifacts = client.publication_artifacts(run)
    if artifacts:
        record = read_resolved_record(client, run, env, validator)
        gate.require(record['kind'] == 'journal', 'recovery_anchor_journal_missing')
        intent, result = record['proof']
        gate.require(intent['id'] == anchor['intent_id'] and
                     intent['digest'] == anchor['intent_digest'] and
                     result['id'] == anchor['result_id'] and
                     result['digest'] == anchor['result_digest'] and
                     result['journal']['state'] == 'live_pass' and
                     result['journal']['events'][-1].get('deployment_id') == anchor['deployment_id'],
                     'recovery_anchor_journal_mismatch')
    else:
        # After the original 7-day retention, GitHub job steps remain a
        # corroborating witness, not a replacement copy of expired journals.
        jobs = client.skipped_publication_jobs(run)
        gate.require(isinstance(jobs, list) and len(jobs) == 3 and
                     sorted(x.get('name') for x in jobs) ==
                     ['browser-quality', 'publish', 'static-quality'] and
                     all(x.get('status') == 'completed' and x.get('conclusion') == 'success'
                         and x.get('run_id') == run['id'] and x.get('head_sha') == run['head_sha'] for x in jobs),
                     'recovery_anchor_job_proof_missing')
        writer = next(x for x in jobs if x['name'] == 'publish')
        steps = {x.get('name'): x.get('conclusion') for x in writer.get('steps', [])}
        for step in ('Prepare read-only deployment plan',
                     'Persist intent before any upload',
                     'Upload once and require actual matching canonical deployment',
                     'Verify all live contracts only after exact deployment proof',
                     'Save final journal even on failure; never upload credentials or raw logs'):
            gate.require(steps.get(step) == 'success', 'recovery_anchor_job_proof_missing')
        # A mandatory Cloudflare *current canonical SHA* check is performed by
        # publisher.preflight even in this fallback. This does not prove missing
        # historical ZIP bytes and must never authorize arbitrary older gaps.
    return anchor['head_sha']


def verified_successful_frontier(client, run, env, validator):
    """Future clean successful runs may replace an older reviewed frontier.

    Expired GitHub ZIPs alone must not deadlock all future publishing. A new
    frontier requires immutable GitHub successful writer-step evidence AND
    Cloudflare canonical matching its exact SHA (checked in preflight).
    Ambiguous, failed and rolled-back attempts never qualify.
    """
    gate.require(run.get('run_number', 0) > RECOVERY_FRONTIER['run_number'] and
                 run.get('status') == 'completed' and run.get('conclusion') == 'success',
                 'future_frontier_not_successful')
    artifacts = client.publication_artifacts(run)
    if artifacts:
        proof = read_resolved_record(client, run, env, validator)
        gate.require(proof['kind'] == 'journal' and
                     proof['proof'][1]['journal']['state'] == 'live_pass' and
                     proof['proof'][1]['journal']['events'][-1].get('state') == 'live_pass',
                     'future_frontier_not_live')
    else:
        jobs = client.skipped_publication_jobs(run)
        gate.require(isinstance(jobs, list) and len(jobs) == 3 and
                     sorted(x.get('name') for x in jobs) ==
                     ['browser-quality', 'publish', 'static-quality'] and
                     all(x.get('status') == 'completed' and x.get('conclusion') == 'success' and
                         x.get('run_id') == run['id'] and x.get('head_sha') == run['head_sha'] and
                         x.get('run_attempt') == 1 for x in jobs),
                     'future_frontier_provenance_missing')
        writer = next(x for x in jobs if x['name'] == 'publish')
        steps = {x.get('name'): x.get('conclusion') for x in writer.get('steps', [])}
        required = ('Prepare read-only deployment plan',
                    'Persist intent before any upload',
                    'Upload once and require actual matching canonical deployment',
                    'Verify all live contracts only after exact deployment proof',
                    'Save final journal even on failure; never upload credentials or raw logs')
        gate.require(len(steps) == len(writer.get('steps', [])) and
                     all(steps.get(name) == 'success' for name in required),
                     'future_frontier_provenance_missing')
        # This is not a claim that expired ZIP contents are known. The
        # subsequent canonical exact-SHA match is non-optional.
    return run['head_sha']


def assert_clear(client, env, validator, records=(), recovery=False):
    runs = merge_runs(client.publication_runs(), records)
    current = validate_runs(runs, env)
    archived = {record['run']['id'] for record in records}
    ordered = sorted(runs, key=lambda item: item['run_number'])
    if recovery:
        gate.require(current['run_number'] > RECOVERY_FRONTIER['run_number'],
                     'recovery_frontier_current_run_invalid')
        anchor = next((run for run in ordered if run['run_number'] == RECOVERY_FRONTIER['run_number']), None)
        gate.require(anchor is not None and anchor['head_sha'] == RECOVERY_FRONTIER['head_sha'] and
                     anchor['conclusion'] == 'success', 'recovery_anchor_deleted')
        # Explicitly verify the pinned original witness on every preflight,
        # even after a later clean successful run has superseded it.
        verified_recovery_frontier(client, anchor, env, validator)
        candidates = [run for run in ordered if RECOVERY_FRONTIER['run_number'] <=
                      run['run_number'] < current['run_number'] and
                      run['status'] == 'completed' and run['conclusion'] == 'success']
        gate.require(bool(candidates), 'no_proven_successful_frontier')
        frontier = candidates[-1]
        last_live_sha = (RECOVERY_FRONTIER['head_sha'] if frontier['run_number'] ==
                         RECOVERY_FRONTIER['run_number'] else
                         verified_successful_frontier(client, frontier, env, validator))
    else:
        frontier = None
        last_live_sha = None
    for run in ordered:
        if run['run_number'] >= current['run_number'] or run['id'] in archived:
            continue
        if recovery and run['run_number'] <= frontier['run_number']:
            continue  # Superseded earlier attempts remain in immutable GitHub history.
        proof = read_resolved_record(client, run, env, validator)
        if recovery and proof['kind'] == 'journal' and proof['proof'][1]['journal']['state'] == 'live_pass':
            last_live_sha = run['head_sha']
    return last_live_sha
