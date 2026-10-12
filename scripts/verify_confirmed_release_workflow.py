"""Fail-closed contract for a disabled, owner/protected-main-only confirmation job."""
from pathlib import Path
import re
import json
import sys
ROOT = Path(__file__).resolve().parents[1]


def verify(text: str) -> list[str]:
    markers = ["github.repository == 'MorvuddEzkaton/outpost-public-site'",
               "github.ref == 'refs/heads/main'", "github.event_name == 'workflow_dispatch'",
               "github.actor == github.repository_owner", "environment: production",
               "vars.OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED == '1'",
               "vars.OUTPOST_CONFIRMED_RELEASE_PUBLICATION_ENABLED == '1'",
               "permissions:\n  contents: read", "persist-credentials: false", "ref: ${{ github.sha }}",
               "type: choice", "- outpost", "- accounting", "cancel-in-progress: false",
               "python scripts/release_integrity.py", "python scripts/verify_live_production.py",
               "python scripts/verify_live_accounting_release.py",
               'python scripts/confirm_telegram_release.py "$RELEASE_PRODUCT" --source-sha "$GITHUB_SHA"',
               "secrets.OUTPOST_RELEASE_CONFIRM_KEY"]
    markers += ['python scripts/production_deployment_gate.py --check',
                'secrets.OUTPOST_PAGES_DEPLOY_TOKEN']
    errors = [f"missing confirmation guard {m}" for m in markers if m not in text]
    if re.search(r"^  (?:pull_request|pull_request_target|workflow_run|push|schedule):", text, re.M):
        errors.append("confirmation must not be triggered by PR/untrusted/automatic events")
    if any(x in text for x in ("contents: write", "pull-requests: write", "continue-on-error:", "wrangler deploy", "gh pr merge", "printenv", "set -x")):
        errors.append("unexpected privilege/deploy/logging bypass")
    for script in re.findall(r"run:.*", text):
        if "${{" in script:
            errors.append("untrusted expression interpolated directly into shell")
    if not text.find("Validate owner-reviewed Windows receipt") < text.find("Verify actual live installers") < text.find("secrets.OUTPOST_RELEASE_CONFIRM_KEY"):
        errors.append("receipt and full live verification must precede credential-bearing confirmation")
    if not text.find("Validate owner-reviewed Windows receipt") < text.find('python scripts/production_deployment_gate.py --check') < text.find("Verify actual live installers"):
        errors.append("exact reviewed deployment and safe notification mode must precede canonical live GETs")
    return errors


def verify_scheduler_config(config: dict) -> list[str]:
    allowed = {"name", "main", "compatibility_date", "workers_dev", "vars", "triggers"}
    if set(config) != allowed or config.get("vars") != {"OUTPOST_RELEASE_SCHEDULER_ENABLED": "0"} or config.get("triggers") != {"crons": []} or config.get("workers_dev") is not False:
        return ["scheduler template must be disabled with no triggers, routes, secrets or data bindings"]
    if config.get("main") != "../scripts/telegram_release_scheduler.mjs":
        return ["scheduler template points outside reviewed relay"]
    return []


if __name__ == "__main__":
    errors = verify((ROOT / ".github/workflows/confirm-telegram-release.yml").read_text(encoding="utf-8"))
    errors += verify_scheduler_config(json.loads((ROOT / "release/telegram-scheduler.template.json").read_text(encoding="utf-8")))
    if errors:
        print("Confirmed release workflow: FAIL\n" + "\n".join(errors)); sys.exit(1)
    print("Confirmed release workflow: PASS; owner/trusted-main/manual/production approval, receipt and live checks, read-only defaults")
