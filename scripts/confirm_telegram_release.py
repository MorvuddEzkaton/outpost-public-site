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


def trusted_apply_environment(source_sha: str) -> str:
    expected = {"GITHUB_REPOSITORY": "MorvuddEzkaton/outpost-public-site",
                "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_SHA": source_sha, "OUTPOST_CONFIRMED_RELEASE_PUBLICATION_ENABLED": "1",
                "OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED": "1"}
    if any(os.environ.get(k) != v for k, v in expected.items()):
        raise IntegrityError("trusted protected-main production confirmation gate not satisfied")
    key = os.environ.get("OUTPOST_RELEASE_CONFIRM_KEY", "")
    if len(key) < 32:
        raise IntegrityError("release confirmation credential unavailable")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", choices=("outpost", "accounting"))
    parser.add_argument("--source-sha", required=True, help="public protected-main provenance, not a secret")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        payload = confirmation_payload(ROOT, args.product, args.source_sha)
        if not args.apply:
            print(json.dumps({"dry_run": True, "payload": payload, "network_requests": 0, "notification_sent": False}))
            return 0
        key = trusted_apply_environment(args.source_sha)
        request = urllib.request.Request(ENDPOINT, method="POST", data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json", "X-OutPost-Release-Key": key})
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=60) as response:
            data = json.loads(response.read(8193))
        if data.get("ok") is not True or data.get("confirmed") is not True or data.get("product") != payload["product"] or data.get("version") != payload["version"] or data.get("notification_sent") is not False:
            raise IntegrityError("confirmation was not acknowledged")
        print(json.dumps({"confirmed": True, "product": args.product, "version": payload["version"], "notification_sent": False}))
        return 0
    except Exception:
        # Never print auth values, raw API errors or private exception payloads.
        print("Release confirmation: FAIL; inspect approval, receipt and live verification gates", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
