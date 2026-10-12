"""Offline negative tests; synthetic attestations never publish installers."""
from pathlib import Path
import copy
import json
import tempfile
import unittest
from release_integrity import (IntegrityError, append_target, assert_append_only, digest, parse_json,
                               validate_receipt, validate_registry, verify_registry)
from release_test_fixtures import fixture_row, synthetic_pe, synthetic_receipt


class ReleaseIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="outpost-integrity-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        downloads = self.root / "site/downloads"
        downloads.mkdir(parents=True)
        self.installer = downloads / "OutPOSt-Setup-v1.2.3.exe"
        self.installer.write_bytes(synthetic_pe())
        self.receipt = synthetic_receipt(self.installer, "outpost", "1.2.3")
        self.checksum = self.installer.with_suffix(".sha256.txt")
        self.checksum.write_text(f"{digest(self.installer)} *{self.installer.name}\n", encoding="utf-8", newline="\n")
        self.row = fixture_row(self.installer, "outpost", "1.2.3")
        (self.root / "release").mkdir()
        self.registry = self.root / "release/artifact-registry.json"
        self.registry.write_text(json.dumps({"schema_version": 1, "artifacts": [self.row]}), encoding="utf-8")

    def check_receipt(self, receipt):
        return validate_receipt(receipt, self.installer, "outpost", "1.2.3")

    def test_exact_receipt_and_inventory_pass(self):
        self.assertEqual(self.check_receipt(self.receipt), self.receipt)
        self.assertEqual(verify_registry(self.root), [self.row])

    def test_required_binding_failures(self):
        changes = {"product": "accounting", "version": "1.2.4", "installer": "other.exe", "size_bytes": 1,
                   "sha256": "A" * 64, "windows_acceptance": "NOT_VERIFIED", "approved_for_publication": False,
                   "architecture": "x64", "runtime": "net8", "setup_authenticode": "UnknownError",
                   "app_authenticode": "HashMismatch", "kind": "web-smoke-pass", "schema_version": True,
                   "published_date": "2026-99-99", "payload_manifest_sha256": "", "release_report_sha256": "0" * 64,
                   "windows_report_sha256": "arbitrary-PASS"}
        for field, value in changes.items():
            with self.subTest(field=field), self.assertRaises(IntegrityError):
                altered = dict(self.receipt, **{field: value})
                self.check_receipt(altered)

    def test_raw_report_fields_not_public(self):
        with self.assertRaises(IntegrityError):
            self.check_receipt(dict(self.receipt, raw_report="private local path"))

    def test_missing_report_binding(self):
        receipt = dict(self.receipt)
        del receipt["windows_report_sha256"]
        with self.assertRaises(IntegrityError):
            self.check_receipt(receipt)

    def test_duplicate_json_rejected(self):
        with self.assertRaises(IntegrityError):
            parse_json('{"version":"1.2.3","version":"1.2.4"}')

    def test_binary_tampering_even_with_new_checksum(self):
        self.installer.write_bytes(synthetic_pe() + b"tampered")
        self.checksum.write_text(f"{digest(self.installer)} *{self.installer.name}\n", encoding="utf-8")
        with self.assertRaises(IntegrityError):
            verify_registry(self.root)
        with self.assertRaises(IntegrityError):
            self.check_receipt(self.receipt)

    def test_fake_pe_rejected_even_when_hash_matches(self):
        self.installer.write_bytes(b"MZ" + bytes(126))
        with self.assertRaises(IntegrityError):
            self.check_receipt(synthetic_receipt(self.installer, "outpost", "1.2.3"))

    def test_deleted_historical_installer_rejected(self):
        self.installer.unlink()
        with self.assertRaises(IntegrityError):
            verify_registry(self.root)

    def test_deleted_checksum_rejected(self):
        self.checksum.unlink()
        with self.assertRaises(IntegrityError):
            verify_registry(self.root)

    def test_extra_unregistered_artifact_rejected(self):
        (self.installer.parent / "other.exe").write_bytes(synthetic_pe())
        with self.assertRaises(IntegrityError):
            verify_registry(self.root)

    def test_append_only_binds_old_row(self):
        for replacement in ([], [dict(self.row, sha256="B" * 64)], [dict(self.row, product="accounting")]):
            with self.subTest(value=replacement), self.assertRaises(IntegrityError):
                assert_append_only([self.row], replacement)

    def test_duplicate_and_path_traversal_blocked(self):
        for rows in ([self.row, self.row], [dict(self.row, installer="../private.exe")]):
            with self.assertRaises(IntegrityError):
                validate_registry({"schema_version": 1, "artifacts": rows})

    def test_same_url_cannot_be_reused(self):
        with self.assertRaises(IntegrityError):
            append_target([self.row], self.receipt, self.checksum.read_text())

    def test_other_product_append_preserves_history(self):
        other = self.installer.parent / "OutPOSt-Accounting-Setup-v2.3.4.exe"
        other.write_bytes(synthetic_pe(8192))
        receipt = synthetic_receipt(other, "accounting", "2.3.4")
        checksum_text = f"{digest(other)} *{other.name}\n"
        result = append_target([self.row], receipt, checksum_text)
        self.assertEqual(result["artifacts"][0], self.row)
        self.assertEqual(result["artifacts"][1]["product"], "accounting")


if __name__ == "__main__":
    unittest.main()
