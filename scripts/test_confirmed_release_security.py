"""Offline trust-boundary negatives; no GitHub/Cloudflare/Telegram calls."""
from pathlib import Path
import os
import json
import tempfile
import unittest
from unittest.mock import patch
from release_integrity import IntegrityError
from verify_confirmed_release_workflow import verify, verify_scheduler_config
import confirm_telegram_release as confirm

ROOT = Path(__file__).resolve().parents[1]


class ConfirmedReleaseSecurity(unittest.TestCase):
    def test_disabled_scheduler_config_cannot_gain_credentials_routes_or_db(self):
        value = json.loads((ROOT / "release/telegram-scheduler.template.json").read_text(encoding="utf-8"))
        self.assertEqual(verify_scheduler_config(value), [])
        for change in ({"triggers": {"crons": ["*/5 * * * *"]}}, {"vars": {"OUTPOST_RELEASE_SCHEDULER_ENABLED": "1"}}, {"d1_databases": []}, {"workers_dev": True}):
            with self.subTest(change=change): self.assertTrue(verify_scheduler_config({**value, **change}))
    def test_workflow_valid(self):
        self.assertEqual(verify((ROOT / ".github/workflows/confirm-telegram-release.yml").read_text(encoding="utf-8")), [])

    def test_each_guard_removal_fails(self):
        text = (ROOT / ".github/workflows/confirm-telegram-release.yml").read_text(encoding="utf-8")
        markers = ["github.repository == 'MorvuddEzkaton/outpost-public-site'", "github.ref == 'refs/heads/main'",
                   "github.event_name == 'workflow_dispatch'", "github.actor == github.repository_owner",
                   "environment: production", "vars.OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED == '1'",
                   "vars.OUTPOST_CONFIRMED_RELEASE_PUBLICATION_ENABLED == '1'", "persist-credentials: false",
                   "ref: ${{ github.sha }}", "python scripts/verify_live_production.py", "python scripts/verify_live_accounting_release.py",
                   "permissions:\n  contents: read", "cancel-in-progress: false"]
        for marker in markers:
            with self.subTest(marker=marker): self.assertTrue(verify(text.replace(marker, "REMOVED", 1)))

    def test_unsafe_events_and_shell_fail(self):
        text = (ROOT / ".github/workflows/confirm-telegram-release.yml").read_text(encoding="utf-8")
        for extra in ("\n  pull_request_target:", "\n  workflow_run:", "\n  schedule:", "\n    contents: write", "\n        run: echo ${{ inputs.product }}", "\n        run: printenv"):
            with self.subTest(extra=extra): self.assertTrue(verify(text + extra))

    def test_apply_environment_does_not_accept_preview_fork_or_unset_activation(self):
        sha = "a" * 40
        env = {"GITHUB_REPOSITORY": "MorvuddEzkaton/outpost-public-site", "GITHUB_REF": "refs/heads/main",
               "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": sha,
               "OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED": "1", "OUTPOST_CONFIRMED_RELEASE_PUBLICATION_ENABLED": "1",
               "OUTPOST_RELEASE_DELIVERY_MODE": "pilot",
               "OUTPOST_RELEASE_CONFIRM_KEY": "demo-confirm-not-a-real-key".ljust(40, "x")}
        with patch.dict(os.environ, env, clear=True): self.assertEqual(confirm.trusted_apply_environment(sha), env["OUTPOST_RELEASE_CONFIRM_KEY"])
        for key in env:
            with self.subTest(key=key), patch.dict(os.environ, {**env, key: "wrong"}, clear=True):
                with self.assertRaises(IntegrityError): confirm.trusted_apply_environment(sha)

    def test_pilot_requires_both_distinct_keys_and_cannot_use_subscriber_mode(self):
        sha = "a" * 40
        env = {"GITHUB_REPOSITORY": "MorvuddEzkaton/outpost-public-site", "GITHUB_REF": "refs/heads/main",
               "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": sha,
               "OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED": "1", "OUTPOST_CONFIRMED_RELEASE_PUBLICATION_ENABLED": "1",
               "OUTPOST_RELEASE_DELIVERY_MODE": "pilot", "OUTPOST_RELEASE_CONFIRM_KEY": "synthetic-confirm".ljust(40,"x"),
               "OUTPOST_RELEASE_PUMP_KEY": "synthetic-pump".ljust(40,"y")}
        payload = {"action":"confirm", "product":"outpost", "version":"0.99.1"}
        for change in ({"OUTPOST_RELEASE_DELIVERY_MODE":"subscribers"}, {"OUTPOST_RELEASE_PUMP_KEY":""},
                       {"OUTPOST_RELEASE_PUMP_KEY":env["OUTPOST_RELEASE_CONFIRM_KEY"]}):
            with self.subTest(change=change), patch.dict(os.environ,{**env,**change},clear=True), patch.object(confirm,"request_dispatch") as request:
                with self.assertRaises(IntegrityError): confirm.apply_dispatch(payload,"pilot",sha)
                request.assert_not_called()
        acknowledgements = [{"ok":True,"audience":"pilot","confirmed":True,"product":"outpost","version":"0.99.1","notification_sent":False},
                            {"ok":True,"audience":"pilot","sent":1},
                            {"deliveries":[{"product":"outpost","version":"0.99.1","state":"sent","count":1}]}]
        with patch.dict(os.environ,env,clear=True), patch.object(confirm,"request_dispatch",side_effect=acknowledgements) as request:
            result = confirm.apply_dispatch(payload,"pilot",sha)
            self.assertEqual(request.call_args_list[1].args[0],{"action":"tick"})
            self.assertEqual(result["sent"],1)
            self.assertTrue(result["notification_sent"])
            self.assertTrue(result["pilot_acknowledged"])
            self.assertEqual(request.call_args_list[2].args[0],{"action":"status"})
        with patch.dict(os.environ,env,clear=True), patch.object(confirm,"request_dispatch",return_value={"ok":True,"confirmed":False}) as request:
            with self.assertRaises(IntegrityError): confirm.apply_dispatch(payload,"pilot",sha)
            self.assertEqual(request.call_count,1)
        for state in ("pending","retry","unknown","failed","sending","cancelled"):
            replies = [acknowledgements[0], {"ok":True,"audience":"pilot","sent":0},
                       {"deliveries":[{"product":"outpost","version":"0.99.1","state":state,"count":1}]}]
            with self.subTest(state=state), patch.dict(os.environ,env,clear=True), patch.object(confirm,"request_dispatch",side_effect=replies):
                result = confirm.apply_dispatch(payload,"pilot",sha)
                self.assertFalse(result["pilot_acknowledged"])
                self.assertEqual(result["reconciliation_required"],state == "unknown")

    def test_status_refuses_identifiers_and_never_requests_tick(self):
        sha = "a" * 40
        payload = {"action":"confirm","product":"outpost","version":"0.99.1"}
        with patch.dict(os.environ,{"OUTPOST_RELEASE_DELIVERY_MODE":"pilot"},clear=True), patch.object(confirm,"trusted_apply_environment",return_value="synthetic"), patch.object(confirm,"request_dispatch",return_value={"deliveries":[{"chat_id":"101"}]}) as request:
            with self.assertRaises(IntegrityError): confirm.apply_dispatch(payload,"status",sha)
            self.assertEqual(request.call_args.args[0],{"action":"status"})

    def test_current_baseline_without_reviewed_receipt_cannot_announce(self):
        # Historical verified binaries are not silently promoted into new
        # approved announcements; a current Windows receipt is still required.
        with tempfile.TemporaryDirectory(prefix="outpost-missing-confirmation-receipt-") as temp:
            root = Path(temp)
            (root / "site").mkdir()
            (root / "site/download.html").write_text('<a href="/downloads/OutPOSt-Setup-v0.99.1.exe">demo</a><a href="/downloads/OutPOSt-Accounting-Setup-v1.99.1.exe">demo</a>', encoding="utf-8")
            for product in ("outpost", "accounting"):
                with self.subTest(product=product), self.assertRaises(IntegrityError):
                    confirm.confirmation_payload(root, product, "a" * 40)


if __name__ == "__main__": unittest.main()
