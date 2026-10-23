"""Offline tests for the secret-backed, staging-only Dropbox importer."""
from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import import_dropbox_installer as imp


class Response(BytesIO):
    def __init__(self, value, metadata=None):
        super().__init__(value)
        self.headers = {"Dropbox-API-Result": json.dumps(metadata or {})}


class DropboxInstallerImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "site/downloads").mkdir(parents=True)
        (self.root / "release/evidence").mkdir(parents=True)
        self.patched = patch.object(imp, "ROOT", self.root)
        self.patched.start()
        self.addCleanup(self.patched.stop)
        self.version = "0.24.44"
        self.name = "OutPOSt-Setup-v0.24.44.exe"
        self.data = b"MZ" + b"abc" * 70
        self.sha = hashlib.sha256(self.data).hexdigest().upper()
        self.target = self.root / "site/downloads" / self.name
        self.checksum = self.root / "site/downloads/OutPOSt-Setup-v0.24.44.sha256.txt"
        self.receipt = self.root / "release/evidence/outpost-v0.24.44.json"
        self.checksum.write_text(f"{self.sha} *{self.name}\n", encoding="utf-8")
        self.acceptance = {"windows_acceptance": "PASS", "approved_for_publication": True,
                           "sha256": self.sha, "installer": self.name, "version": self.version,
                           "size_bytes": len(self.data)}
        self.save_receipt()

    def save_receipt(self):
        self.receipt.write_text(json.dumps(self.acceptance), encoding="utf-8")

    def response(self, data=None, name=None, size=None):
        return Response(self.data if data is None else data,
                        {"name": self.name if name is None else name, "size": len(self.data) if size is None else size})

    def test_validated_inputs_exact(self):
        self.assertEqual(imp.validated_inputs(self.version), (self.target, len(self.data), self.sha))

    def test_missing_or_forged_windows_acceptance_rejected(self):
        for field, value in (("windows_acceptance", "FAIL"), ("approved_for_publication", False),
                             ("sha256", "0" * 64), ("version", "0.24.43"), ("size_bytes", 0)):
            with self.subTest(field=field):
                old = self.acceptance[field]
                self.acceptance[field] = value
                self.save_receipt()
                with self.assertRaises(ValueError):
                    imp.validated_inputs(self.version)
                self.acceptance[field] = old
        self.receipt.unlink()
        with self.assertRaises(ValueError):
            imp.validated_inputs(self.version)

    def test_path_injection_rejected(self):
        for version in ("../secret", "0.24.44/other", "0.24.44\n", "00.24.44"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                imp.validated_inputs(version)

    def test_valid_download_and_shared_receipt_verifier(self):
        with patch.object(imp, "load_receipt") as verifier:
            imp.download(self.version, self.target, len(self.data), self.sha, "fake",
                         opener=lambda request, timeout: self.response())
            verifier.assert_called_once_with(self.root, "outpost", self.version)
        self.assertEqual(self.target.read_bytes(), self.data)

    def test_bad_download_or_metadata_cannot_write_exe(self):
        samples = ((b"tampered", self.name, len(self.data)),
                   (self.data + b"x", self.name, len(self.data)),
                   (self.data, "wrong.exe", len(self.data)),
                   (self.data, self.name, len(self.data) + 1))
        for data, name, size in samples:
            with self.subTest(name=name, size=size), self.assertRaises(ValueError):
                imp.download(self.version, self.target, len(self.data), self.sha, "fake",
                             opener=lambda request, timeout: self.response(data, name, size))
            self.assertFalse(self.target.exists())
            self.assertEqual(list(self.target.parent.glob(".*.tmp")), [])

    def test_receipt_validation_failure_unlinks_exe(self):
        with patch.object(imp, "load_receipt", side_effect=ValueError("invalid PE")):
            with self.assertRaises(ValueError):
                imp.download(self.version, self.target, len(self.data), self.sha, "fake",
                             opener=lambda request, timeout: self.response())
        self.assertFalse(self.target.exists())

    def test_refresh_token_only_in_post_body(self):
        env = {"OUTPOST_DROPBOX_APP_KEY": "key", "OUTPOST_DROPBOX_APP_SECRET": "secret",
               "OUTPOST_DROPBOX_REFRESH_TOKEN": "refresh"}
        seen = []
        def opener(request, timeout):
            seen.append(request)
            return Response(b'{"access_token":"test"}')
        with patch.dict(imp.os.environ, env):
            self.assertEqual(imp.access_token(opener), "test")
        self.assertEqual(seen[0].full_url, "https://api.dropboxapi.com/oauth2/token")
        self.assertNotIn("refresh", seen[0].full_url)
        self.assertIn(b"refresh_token=refresh", seen[0].data)

    def test_privileged_workflow_stays_manual_and_staging_only(self):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/import-outpost-installer.yml"
        raw = path.read_text(encoding="utf-8")
        for required in ("workflow_dispatch:", "github.actor == 'MorvuddEzkaton'",
                         "github.ref == 'refs/heads/staging'", "vars.OUTPOST_DROPBOX_IMPORT_ENABLED == '1'",
                         "permissions:\n  contents: read", "git merge-base --is-ancestor",
                         "git switch --detach", "python scripts/import_dropbox_installer.py",
                         "git push origin HEAD:refs/heads/staging"):
            self.assertIn(required, raw)
        self.assertNotIn("gh pr merge", raw)
        self.assertNotIn("wrangler", raw.lower())
        self.assertIn("  push:\n", raw)
        self.assertIn("    branches:\n      - staging", raw)
        self.assertNotRegex(raw, r"(?m)^  (?:pull_request|schedule|pull_request_target):")


if __name__ == "__main__":
    unittest.main()
