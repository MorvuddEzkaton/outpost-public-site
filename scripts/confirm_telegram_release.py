"""Confirm a new, owner-reviewed Windows release; dry-run unless explicitly applied.

Secrets are read from the trusted production environment, never argv or files.
This is not deployment or Windows acceptance, and never invokes a broadcast.
"""
from pathlib import Path
import argparse
import json
import os
import re
import sys
import urllib.request
from release_integrity import IntegrityError, load_receipt, verify_registry

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://outpost.com.ua/api/telegram/releases/dispatch"
PILOT_ENDPOINT = "https://outpost.com.ua/api/telegram/releases/pilot"


def confirmation_payload(root: Path, product: str, source_sha: str) -> dict:
    if product not in ("outpost", "accounting") or not re.fullmatch(r"[a-f0-9]{40}", source_sha):
        raise IntegrityError("invalid confirmation provenance")
    prefix = "OutPOSt-Accounting-Setup-v" if product == "accounting" else "OutPOSt-Setup-v"
    text = (root / "site/download.html").read_text(encoding="utf-8")
    versions = set(re.findall(re.escape(prefix) + r"(\d+\.\d+\.\d+)\.exe", text))
    if len(versions) != 1:
        raise IntegrityError("ambiguous current release")
    version = versions.pop()
    receipt = load_receipt(root, product, version)
    rows = verify_registry(root)
    matching = [r for r in rows if r["product"] == product and r["version"] == version]
    if len(matching) != 1 or any(receipt[k] != matching[0][k] for k in ("installer", "sha256", "size_bytes")):
        raise IntegrityError("current release/registry/Windows receipt mismatch")
    return {"action": "confirm", "product": product, "version": version,
            "sha256": receipt["sha256"], "size_bytes": receipt["size_bytes"], "source_sha": source_sha}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def trusted_apply_environment(source_sha: str, operation: str = "confirm") -> str:
    expected = {"GITHUB_REPOSITORY": "MorvuddEzkaton/outpost-public-site",
                "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_SHA": source_sha, "OUTPOST_CONFIRMED_RELEASE_PUBLICATION_ENABLED": "1",
                "OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED": "1"}
    if any(os.environ.get(k) != v for k, v in expected.items()):
        raise IntegrityError("trusted protected-main production confirmation gate not satisfied")
    mode = os.environ.get("OUTPOST_RELEASE_DELIVERY_MODE", "off")
    if operation not in ("confirm", "pilot", "tick", "status") or mode not in ("pilot", "subscribers") or (operation == "pilot" and mode != "pilot"):
        raise IntegrityError("explicit delivery audience gate not satisfied")
    if mode == "pilot":
        chat = os.environ.get("OUTPOST_RELEASE_PILOT_EXPECTED_CHAT_ID", "")
        if not re.fullmatch(r"[1-9]\d{0,15}",chat) or int(chat) > 9007199254740991:
            raise IntegrityError("private expected administrator assertion required")
    name = "OUTPOST_RELEASE_CONFIRM_KEY" if operation in ("confirm", "pilot") else "OUTPOST_RELEASE_PUMP_KEY"
    key = os.environ.get(name, "")
    if len(key) < 32:
        raise IntegrityError("release confirmation credential unavailable")
    return key


def request_dispatch(payload: dict, key: str) -> dict:
    pilot = os.environ.get("OUTPOST_RELEASE_DELIVERY_MODE") == "pilot"
    body = {**payload,"expected_admin_chat_id":os.environ["OUTPOST_RELEASE_PILOT_EXPECTED_CHAT_ID"]} if pilot else payload
    request = urllib.request.Request(PILOT_ENDPOINT if pilot else ENDPOINT, method="POST", data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "X-OutPost-Release-Key": key})
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=60) as response:
        raw = response.read(8193)
        if response.status != 200 or len(raw) > 8192:
            raise IntegrityError("bounded dispatch response required")
        data = json.loads(raw)
    if not isinstance(data, dict) or data.get("ok") is not True or data.get("audience") != os.environ["OUTPOST_RELEASE_DELIVERY_MODE"]:
        raise IntegrityError("dispatch audience was not acknowledged")
    if pilot and data.get("recipient_verified") is not True:
        raise IntegrityError("private recipient was not acknowledged")
    return data


def aggregate_deliveries(data: dict) -> list:
    deliveries = data.get("deliveries")
    if not isinstance(deliveries, list) or len(deliveries) > 200:
        raise IntegrityError("invalid aggregate status")
    allowed_states = {"pending", "sending", "retry", "sent", "cancelled", "failed", "unknown"}
    for row in deliveries:
        if not isinstance(row, dict) or set(row) != {"product", "version", "state", "count"} or row["product"] not in ("outpost", "accounting") or not isinstance(row["version"], str) or not re.fullmatch(r"\d+\.\d+\.\d+", row["version"]) or row["state"] not in allowed_states or type(row["count"]) is not int or row["count"] < 0:
            raise IntegrityError("nonaggregate status rejected")
    return deliveries


def apply_dispatch(payload: dict, operation: str, source_sha: str) -> dict:
    key = trusted_apply_environment(source_sha, operation)
    pump_key = trusted_apply_environment(source_sha, "tick") if operation == "pilot" else None
    if pump_key is not None and pump_key == key:
        raise IntegrityError("distinct confirmation and pump credentials required")
    summary = {"audience": os.environ["OUTPOST_RELEASE_DELIVERY_MODE"], "operation": operation,
               "product": payload["product"], "version": payload["version"]}
    if operation in ("confirm", "pilot"):
        data = request_dispatch(payload, key)
        if data.get("confirmed") is not True or data.get("product") != payload["product"] or data.get("version") != payload["version"] or data.get("notification_sent") is not False:
            raise IntegrityError("confirmation was not acknowledged")
        summary.update(confirmed=True, notification_sent=False)
        if operation == "confirm":
            return summary
    action = "tick" if operation == "pilot" else operation
    data = request_dispatch({"action": action}, pump_key if operation == "pilot" else key)
    if action == "tick":
        for name in ("sent", "retry", "unknown", "failed", "blocked", "cancelled"):
            value = data.get(name, 0)
            if type(value) is not int or value < 0 or value > 3:
                raise IntegrityError("invalid delivery counters")
            summary[name] = value
        summary["notification_sent"] = summary["sent"] > 0
        summary["cooldown"] = data.get("cooldown") is True
        if operation == "pilot":
            deliveries = aggregate_deliveries(request_dispatch({"action":"status"}, pump_key))
            current = [row for row in deliveries if row["product"] == payload["product"] and row["version"] == payload["version"]]
            summary["pilot_acknowledged"] = len(current) == 1 and current[0]["state"] == "sent" and current[0]["count"] == 1
            summary["reconciliation_required"] = any(row["state"] == "unknown" for row in current)
    else:
        deliveries = aggregate_deliveries(data)
        summary["deliveries"] = deliveries
        summary["reconciliation_required"] = any(row["state"] == "unknown" for row in deliveries)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", choices=("outpost", "accounting"))
    parser.add_argument("--source-sha", required=True, help="public protected-main provenance, not a secret")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--operation", choices=("confirm", "pilot", "tick", "status"), default="confirm")
    args = parser.parse_args()
    try:
        payload = confirmation_payload(ROOT, args.product, args.source_sha)
        if not args.apply:
            print(json.dumps({"dry_run": True, "operation": args.operation, "payload": payload, "network_requests": 0, "notification_sent": False}))
            return 0
        result = apply_dispatch(payload, args.operation, args.source_sha)
        print(json.dumps(result))
        if args.operation == "pilot" and result.get("pilot_acknowledged") is not True:
            print("Pilot delivery not acknowledged; inspect status, do not blindly replay", file=sys.stderr)
            return 1
        return 0
    except Exception:
        # Never print auth values, raw API errors or private exception payloads.
        print("Release confirmation: FAIL; inspect approval, receipt and live verification gates", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
