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


def assert_clear(client, env, validator, records=()):
    runs = merge_runs(client.publication_runs(), records)
    current = validate_runs(runs, env)
    archived = {record['run']['id'] for record in records}
    for run in sorted(runs, key=lambda item: item['run_number']):
        if run['run_number'] >= current['run_number'] or run['id'] in archived:
            continue
        read_resolved_record(client, run, env, validator)
