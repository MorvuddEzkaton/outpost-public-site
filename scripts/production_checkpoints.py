"""Readable, bounded, owner-reviewed evidence; never an unknown-attempt reset.

An empty genesis is followed only by immutable, contiguous resolved run records.
New records need provider verification in PR CI before their artifacts expire.
This is a reviewed witness, not a cryptographic GitHub attestation or authority
to publish. No raw archives, tokens, logs, actors, URLs or free text are stored.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import production_deployment_gate as gate
import production_history as history

PATH = 'release/production-history-checkpoint.json'
MAX_BYTES = 8 * 1024 * 1024
MAX_COMMITS = 256
ZERO = '0' * 64


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def genesis():
    return {'schema': 1, 'repository': gate.REPOSITORY, 'workflow_id': history.WORKFLOW_ID,
            'first_run_id': history.FIRST_RUN_ID, 'records': []}


def parse(raw):
    gate.require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BYTES, 'checkpoint_size_rejected')
    try:
        return json.loads(raw, object_pairs_hook=history.unique_json_pairs)
    except gate.GateError:
        raise
    except Exception:
        raise gate.GateError('checkpoint_unreadable') from None


def seal(record, previous=ZERO):
    result = {**deepcopy(record), 'previous_sha256': previous}
    return {**result, 'record_sha256': digest(result)}


def body(record):
    return {key: value for key, value in record.items() if key not in ('previous_sha256', 'record_sha256')}


def validate(value, journal_validator):
    try:
        gate.require(isinstance(value, dict) and set(value) == set(genesis()) and
                     type(value['schema']) is int and value['schema'] == 1 and
                     {key: value[key] for key in value if key != 'records'} ==
                     {key: val for key, val in genesis().items() if key != 'records'} and
                     isinstance(value['records'], list) and len(value['records']) < history.MAX_RUNS,
                     'invalid_checkpoint_header')
        records = value['records']
        previous = ZERO
        for number, record in enumerate(records, 1):
            gate.require(isinstance(record, dict) and set(record) ==
                         {'run', 'kind', 'proof', 'previous_sha256', 'record_sha256'}, 'invalid_checkpoint_record')
            gate.require(record['previous_sha256'] == previous and
                         record['record_sha256'] == digest({key: val for key, val in record.items() if key != 'record_sha256'}),
                         'checkpoint_chain_mismatch')
            previous = record['record_sha256']
            run = record['run']
            gate.require(run == history.run_projection(run) and run['run_number'] == number and
                         type(run['run_number']) is int and type(run['id']) is int and
                         run['status'] == 'completed' and run['conclusion'] in
                         ('success', 'failure', 'cancelled', 'timed_out', 'skipped', 'action_required', 'neutral'),
                         'invalid_checkpoint_run')
            proof = record['proof']
            if record['kind'] == 'skipped':
                gate.require(isinstance(proof, dict) and set(proof) == set(history.JOB_FIELDS) and
                             proof['name'] == 'publish' and proof['run_id'] == run['id'] and
                             type(proof['run_id']) is int and type(proof['run_attempt']) is int and
                             proof['run_attempt'] == 1 and proof['head_sha'] == run['head_sha'] and
                             proof['status'] == 'completed' and (proof['conclusion'] == 'skipped' or
                             proof['conclusion'] == 'cancelled' and run['conclusion'] == 'cancelled') and
                             proof['steps'] == [] and proof['runner_id'] in (None, 0) and
                             (proof['runner_id'] is None or type(proof['runner_id']) is int) and
                             proof['runner_name'] is None, 'invalid_checkpoint_skipped_proof')
                history.positive(proof['id'])
            else:
                gate.require(record['kind'] == 'journal' and isinstance(proof, list) and len(proof) == 2,
                             'invalid_checkpoint_journal_pair')
                for kind, item in zip(('intent', 'result'), proof):
                    gate.require(isinstance(item, dict) and set(item) == set(history.ARTIFACT_FIELDS) | {'journal'} and
                                 set(item['workflow_run']) == set(history.IDENTITY_FIELDS), 'unexpected_checkpoint_artifact_data')
                    history.validate_artifact({**item, 'expired': False}, run, kind)
                gate.require(proof[0]['id'] != proof[1]['id'], 'duplicate_checkpoint_artifact')
                history.resolved_journals(*(item['journal'] for item in proof), run, {},
                                         lambda data, env: journal_validator(data, env['GITHUB_SHA'], env['GITHUB_RUN_ID']))
        if records:
            history.validate_inventory([record['run'] for record in records])
        return value
    except gate.GateError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError):
        raise gate.GateError('invalid_checkpoint_data') from None


def append_only(before, after):
    gate.require({key: value for key, value in before.items() if key != 'records'} ==
                 {key: value for key, value in after.items() if key != 'records'} and
                 after['records'][:len(before['records'])] == before['records'], 'checkpoint_history_rewritten')
    return after['records'][len(before['records']):]


def git(root, *args):
    try:
        return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.SubprocessError):
        raise gate.GateError('checkpoint_git_history_unavailable') from None


def blob(root, sha):
    gate.require(re.fullmatch(r'[a-f0-9]{40}', sha or '') is not None, 'checkpoint_revision_rejected')
    listing = git(root, 'ls-tree', sha, '--', PATH).decode().split()
    gate.require(len(listing) == 4 and listing[0] == '100644' and listing[1] == 'blob' and listing[3] == PATH,
                 'checkpoint_tracked_regular_file_required')
    return git(root, 'show', sha + ':' + PATH)


def load_checked(root, sha, journal_validator):
    """Exact checked-out bytes plus ALL ledger revisions; requires full history."""
    root = Path(root)
    gate.require(git(root, 'rev-parse', '--is-shallow-repository').strip() == b'false', 'checkpoint_full_history_required')
    file = root / PATH
    gate.require(file.is_file() and not any(path.is_symlink() for path in [file, *file.parents]), 'checkpoint_file_rejected')
    raw = blob(root, sha)
    gate.require(file.read_bytes() == raw, 'checkpoint_not_reviewed_bytes')
    commits = git(root, 'log', '--full-history', '--topo-order', '--reverse', '--format=%H', sha, '--', PATH).decode().splitlines()
    gate.require(0 < len(commits) <= MAX_COMMITS, 'checkpoint_history_requires_manual_review')
    previous = genesis()
    for index, commit in enumerate(commits):
        value = validate(parse(blob(root, commit)), journal_validator)
        if index == 0:
            gate.require(value == genesis(), 'checkpoint_empty_genesis_required')
        append_only(previous, value)
        previous = value
    current = validate(parse(raw), journal_validator)
    append_only(previous, current)
    gate.require(current == previous, 'checkpoint_ancestry_mismatch')
    return current['records']


def verify_new(client, before, after, journal_validator):
    """Only new rows need live artifacts. Existing reviewed proof may expire."""
    new = append_only(validate(before, journal_validator), validate(after, journal_validator))
    if not new:
        return 0
    runs = history.merge_runs(client.publication_runs(), before['records'])
    indexed = {run['id']: run for run in runs}
    for record in new:
        run = indexed.get(record['run']['id'])
        gate.require(run is not None and history.run_projection(run) == record['run'], 'new_checkpoint_run_not_live')
        evidence = history.read_resolved_record(client, run, {},
                         lambda data, env: journal_validator(data, env['GITHUB_SHA'], env['GITHUB_RUN_ID']))
        gate.require(body(record) == evidence, 'new_checkpoint_provider_mismatch')
    return len(new)
