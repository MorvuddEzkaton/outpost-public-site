"""Default OFFLINE. Explicit PR verification only reads GitHub evidence.

Capture is an opt-in read-only local preparation step, not a publication/repair.
It receives an existing credential on stdin, never argv, disk or console. Its
allowlisted output must be outside Git and needs a separate owner-reviewed PR.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import production_checkpoints as checkpoints
import production_deployment_gate as gate
import production_history as history
from production_publisher import validate_journal_evidence


class EvidenceReads(history.HistoryReads):
    _json = staticmethod(gate.ReadOnlyClients._json)

    def __init__(self, token):
        gate.require(isinstance(token, str) and 0 < len(token) < 4096 and
                     not any(char.isspace() for char in token), 'checkpoint_read_credential_missing')
        self.github_token = token


def baseline(root, base, sha):
    gate.require(checkpoints.git(root, 'merge-base', base, sha).strip().decode() == base,
                 'checkpoint_base_not_ancestor')
    if not checkpoints.git(root, 'ls-tree', base, '--', checkpoints.PATH).strip():
        return checkpoints.genesis()
    return checkpoints.validate(checkpoints.parse(checkpoints.blob(root, base)), validate_journal_evidence)


def capture(client, before):
    runs = history.merge_runs(client.publication_runs(), before['records'])
    value = json.loads(json.dumps(before))
    count = len(value['records'])
    for run in sorted(runs, key=lambda item: item['run_number'])[count:]:
        proof = history.read_resolved_record(client, run, {},
                        lambda data, env: validate_journal_evidence(data, env['GITHUB_SHA'], env['GITHUB_RUN_ID']))
        previous = value['records'][-1]['record_sha256'] if value['records'] else checkpoints.ZERO
        value['records'].append(checkpoints.seal(proof, previous))
    return checkpoints.validate(value, validate_journal_evidence)


def main(argv=None, env=None, root=gate.ROOT, client_factory=EvidenceReads):
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check-new', action='store_true')
    modes.add_argument('--capture', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    try:
        sha = checkpoints.git(root, 'rev-parse', 'HEAD').strip().decode()
        records = checkpoints.load_checked(root, sha, validate_journal_evidence)
        current = {**checkpoints.genesis(), 'records': records}
        gate.require(args.capture == (args.output is not None), 'checkpoint_output_only_for_capture')
        if args.check_new:
            base = env.get('CHECKPOINT_BASE_SHA', '')
            gate.require(len(base) == 40 and all(char in 'abcdef0123456789' for char in base), 'checkpoint_exact_base_required')
            before = baseline(root, base, sha)
            new = checkpoints.append_only(before, current)
            if new:
                gate.require(env.get('GITHUB_ACTIONS') == 'true' and env.get('RUNNER_OS') == 'Linux' and
                             env.get('GITHUB_REPOSITORY') == gate.REPOSITORY and
                             env.get('GITHUB_EVENT_NAME') in ('pull_request', 'workflow_dispatch'), 'checkpoint_readonly_ci_required')
                checkpoints.verify_new(client_factory(env.get('GITHUB_TOKEN', '')), before, current, validate_journal_evidence)
            print(f'Production checkpoint: PASS; {len(new)} new records checked; no publication or Cloudflare access')
        elif args.capture:
            output = args.output
            gate.require(not output.resolve().is_relative_to(Path(root).resolve()) and not output.exists() and
                         not any(path.is_symlink() for path in [output, *output.parents]) and output.parent.is_dir(),
                         'checkpoint_capture_external_new_file_required')
            token = sys.stdin.read(4097).strip()
            result = capture(client_factory(token), current)
            payload = json.dumps(result, indent=2, sort_keys=True).encode() + b'\n'
            gate.require(len(payload) <= checkpoints.MAX_BYTES, 'checkpoint_size_rejected')
            with output.open('xb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            print(f'Production checkpoint candidate: {len(result["records"])} resolved records; separate review required; nothing published')
        else:
            print(f'Production checkpoint: PASS (OFFLINE); {len(records)} immutable records; no credentials or network used')
        return 0
    except gate.GateError as error:
        print('Production checkpoint: BLOCKED; ' + str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
