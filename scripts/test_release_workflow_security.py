"""Negative workflow-contract tests in a tiny temporary repo; no GitHub calls."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowSecurityTests(unittest.TestCase):
    def run_guard(self, product, rewrite):
        name = "verify_prepare_release_workflow.py" if product == "public" else "verify_prepare_accounting_release_workflow.py"
        with tempfile.TemporaryDirectory(prefix="outpost-workflow-negative-") as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            workflows = root / ".github/workflows"
            workflows.mkdir(parents=True)
            shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)
            text = (ROOT / f".github/workflows/prepare-{product}-release.yml").read_text(encoding="utf-8")
            changed = rewrite(text)
            (workflows / f"prepare-{product}-release.yml").write_text(changed, encoding="utf-8")
            return subprocess.run([sys.executable, str(root / "scripts" / name)], cwd=root, capture_output=True, text=True).returncode

    def test_valid_both_workflows(self):
        for product in ("public", "accounting"):
            self.assertEqual(self.run_guard(product, lambda s: s), 0)

    def test_removed_security_contracts_fail(self):
        markers = ["vars.OUTPOST_RELEASE_PREPARATION_ENABLED == '1'", "github.ref == 'refs/heads/main'",
                   "github.actor == 'MorvuddEzkaton'", "ref: main", 'git switch --detach "${STAGING_SHA}"',
                   "python scripts/release_integrity.py --base-ref origin/main", "python scripts/test_release_integrity.py",
                   "permissions:\n  contents: read"]
        for product in ("public", "accounting"):
            for marker in markers:
                with self.subTest(product=product, marker=marker):
                    self.assertNotEqual(self.run_guard(product, lambda s: s.replace(marker, "REMOVED", 1)), 0)

    def test_unsafe_mutations_fail(self):
        mutations = ['git push origin HEAD:refs/heads/main', 'gh pr merge', 'wrangler deploy', 'git push --force',
                     '[ "${status}" = "D" ]']
        for product in ("public", "accounting"):
            for mutation in mutations:
                with self.subTest(product=product, mutation=mutation):
                    self.assertNotEqual(self.run_guard(product, lambda s: s + '\n          ' + mutation + '\n'), 0)


if __name__ == "__main__":
    unittest.main()
