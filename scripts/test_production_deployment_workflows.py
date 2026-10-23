"""Offline mutation tests for deployment-provenance wiring; no live workflow dispatch."""
import unittest
from verify_production_deployment_workflows import ROOT, verify_live, verify_confirmation

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.live=(ROOT/'.github/workflows/live-production-verify.yml').read_text(encoding='utf-8')
        self.confirm=(ROOT/'.github/workflows/confirm-telegram-release.yml').read_text(encoding='utf-8')

    def test_valid_workflows(self):
        self.assertEqual(verify_live(self.live),[])
        self.assertEqual(verify_confirmation(self.confirm),[])

    def test_all_privilege_and_provenance_guards_required(self):
        for marker in ["environment: production", "github.ref == 'refs/heads/main'", "ref: ${{ github.sha }}", "persist-credentials: false",
                       "python scripts/production_deployment_gate.py --check --wait-seconds 2100", "secrets.OUTPOST_PAGES_DEPLOY_TOKEN",
                       "GITHUB_TOKEN: ${{ github.token }}",
                       "github.repository == 'MorvuddEzkaton/outpost-public-site'", "github.actor == github.repository_owner", "OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED: ${{ vars.OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED }}"]:
            with self.subTest(marker=marker): self.assertTrue(verify_live(self.live.replace(marker,'REMOVED',1)))

    def test_source_only_check_cannot_substitute_for_deployment_proof(self):
        self.assertTrue(verify_live(self.live.replace('--check --wait-seconds 2100','',1)))
        self.assertTrue(verify_live(self.live.replace('timeout-minutes: 45', 'timeout-minutes: 8', 1)))

    def test_live_get_before_provenance_fails(self):
        pos=self.live.index('      - name: Require reviewed exact-SHA')
        changed=self.live[:pos]+'      - name: Premature GET\n        run: python scripts/verify_live_production.py\n'+self.live[pos:]
        self.assertTrue(verify_live(changed))

    def test_bypass_triggers_privileges_or_logging_fail(self):
        for extra in ['continue-on-error: true','contents: write','pull-requests: write','pull_request_target:','workflow_run:','printenv','set -x']:
            with self.subTest(extra=extra): self.assertTrue(verify_live(self.live+'\n'+extra))

    def test_confirmation_auto_mode_must_match_writer(self):
        self.assertTrue(verify_confirmation(self.confirm.replace(
            'OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED: ${{ vars.OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED }}', 'REMOVED')))

    def test_confirmation_missing_proof_cannot_use_key(self):
        self.assertTrue(verify_confirmation(self.confirm.replace('python scripts/production_deployment_gate.py --check','echo skipped',1)))
        self.assertTrue(verify_confirmation(self.confirm.replace('secrets.OUTPOST_PAGES_DEPLOY_TOKEN','REMOVED',1)))

if __name__=='__main__':unittest.main()
