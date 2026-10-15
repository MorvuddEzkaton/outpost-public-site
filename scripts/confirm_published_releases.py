"""Post-live future-release confirmation only; never sends/pumps messages.

Known notification failures are explicit blocked/unconfirmed outcomes, not a failed
code deployment or permission to roll it back. Unexpected local failures still fail.
Default is a credential-free plan; ordinary activation remains separate.
"""
from pathlib import Path
import argparse
import json
import os
import re
import sys
import urllib.error
import confirm_telegram_release as manual
import production_deployment_gate as gate
import production_publisher as publisher
from release_integrity import IntegrityError, read_json

ROOT = Path(__file__).resolve().parents[1]
POLICY = "site/_telegram-release-policy.json"
COUNTERPART = {"outpost": "OutPOSt-Setup-v", "accounting": "OutPOSt-Accounting-Setup-v"}
PINNED_CUTOFF = {"outpost": "0.24.40", "accounting": "1.0.2"}


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value):
        raise IntegrityError("invalid_notification_version")
    result = tuple(map(int, value.split(".")))
    if any(part > 9007199254740991 for part in result):
        raise IntegrityError("invalid_notification_version")
    return result


def policy(root):
    data = read_json(root / POLICY)
    if data != {"schema": 1, "minimum_exclusive": PINNED_CUTOFF} or type(data.get("schema")) is not int:
        raise IntegrityError("owner_approved_notification_cutoff_changed")
    return data["minimum_exclusive"]


def candidates(root, sha):
    floors = policy(root)
    text = (root / "site/download.html").read_text(encoding="utf-8")
    selected = []
    for product, prefix in COUNTERPART.items():
        values = set(re.findall(re.escape(prefix) + r"(\d+\.\d+\.\d+)\.exe", text))
        if len(values) != 1:
            raise IntegrityError("ambiguous_notification_release")
        current = values.pop()
        if version(current) > version(floors[product]):
            selected.append(manual.confirmation_payload(root, product, sha))
    return selected


def publication(env, root, journal):
    sha = publisher.context(env)
    gate.require(env.get("GITHUB_EVENT_NAME") == "push", "automatic_confirmation_push_only")
    data = publisher.validate_journal(journal, env)
    gate.require(data["state"] == "live_pass", "accepted_live_publication_required")
    saved = env.get("OUTPOST_SAVED_RESULT_URL", "")
    gate.require(re.fullmatch(r"https://github\.com/" + gate.REPOSITORY + "/actions/runs/" +
                             env["GITHUB_RUN_ID"] + r"/artifacts/[1-9][0-9]*", saved) is not None,
                 "durable_live_result_required")
    gate.require(publisher.digest(publisher.manifest(root, sha)) == data["package_sha256"],
                 "published_package_changed")
    return sha, publisher.deployment_id(data)


def confirm_future(env, root, journal, apply=False, verifier=gate.verify_current, request=manual.request_dispatch):
    sha, deployment = publication(env, root, journal)
    payloads = candidates(root, sha)
    result = {"schema": 1, "source_sha": sha, "deployment_id": deployment, "future_only": True,
              "notification_sent": False, "confirmed": 0, "ok": True, "products": []}
    if not apply:
        return {**result, "state": "plan_only", "eligible": [{"product": p["product"], "version": p["version"]} for p in payloads]}
    gate.require(env.get("OUTPOST_AUTOMATIC_RELEASE_CONFIRMATION_ENABLED") == "1" and
                 env.get("OUTPOST_RELEASE_DELIVERY_MODE") == "subscribers", "automatic_confirmation_not_activated")
    if not payloads:
        return {**result, "state": "no_future_releases"}  # No key, network or SQL needed.
    # Obtain no confirmation credential or network client until context, live
    # journal, saved artifact, immutable package and reviewed Windows receipts pass.
    proof = verifier(env, root)
    gate.require(proof["source_sha"] == sha and proof["deployment_id"] == deployment and
                 proof["review"] == journal["review"], "current_publication_proof_changed")
    key = env.get("OUTPOST_RELEASE_CONFIRM_KEY", "")
    gate.require(isinstance(key, str) and len(key) >= 32, "automatic_confirmation_key_missing")
    for payload in payloads:
        item = {"product": payload["product"], "version": payload["version"], "state": "confirmation_unconfirmed"}
        try:
            # Only confirm. No pump key, tick/status action, recipient selector or
            # local retry. The server independently enforces cutoff/live bytes.
            reply = request(payload, key)
            if (reply.get("ok") is True and reply.get("audience") == "subscribers" and
                reply.get("confirmed") is True and reply.get("product") == payload["product"] and
                reply.get("version") == payload["version"] and reply.get("notification_sent") is False):
                item["state"] = "confirmed_not_sent"
                result["confirmed"] += 1
            else:
                result["ok"] = False
        except (IntegrityError, urllib.error.URLError, TimeoutError, OSError, ValueError):
            result["ok"] = False
        result["products"].append(item)
    return {**result, "state": "confirmed_not_sent" if result["ok"] else "operator_attention_required"}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        publisher.external_path(ROOT, args.journal)
        gate.require(args.journal.is_file() and args.journal.stat().st_size <= 128 * 1024, "bounded_publication_journal_required")
        result = confirm_future(os.environ, ROOT, read_json(args.journal), args.apply)
    except (IntegrityError, gate.GateError):
        # Explicitly separate messaging acceptance from publication success. Never
        # print raw provider errors/keys or claim that a blocked confirmation sent.
        result = {"schema": 1, "ok": False, "state": "confirmation_blocked", "notification_sent": False}
    print(json.dumps(result, sort_keys=True))
    if not result["ok"]:
        print("::warning::Release confirmation needs operator attention; code publication is not rolled back. No delivery success is claimed.")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("\n## Future-release confirmation (not delivery acceptance)\n\n```json\n" + json.dumps(result, sort_keys=True) + "\n```\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
