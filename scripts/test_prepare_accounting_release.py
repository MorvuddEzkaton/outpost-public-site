#!/usr/bin/env python3
"""Synthetic regression test for the reusable Accounting pre-release updater."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from release_test_fixtures import synthetic_pe, write_synthetic_receipt

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = (
    "site/_worker.js",
    "site/_telegram-support.js",
    "site/_telegram-faq.js",
    "site/_headers",
    "wrangler.jsonc",
    "site/changelog.html",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(repo: Path, *args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "scripts/prepare_accounting_release.py", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != expect:
        raise AssertionError(
            f"command returned {result.returncode}, expected {expect}: {' '.join(args)}\n{result.stdout}"
        )
    return result


def next_version(current: str) -> str:
    parts = [int(part) for part in current.split(".")]
    parts[-1] += 1
    return ".".join(str(part) for part in parts)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="outpost-accounting-release-") as temp:
        repo = Path(temp) / "repo"
        shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__", "*.pyc"))

        manifest_path = repo / "release" / "accounting-release.json"
        before_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        current = str(before_manifest["version"])
        target = next_version(current)
        old_installer = repo / "site" / "downloads" / str(before_manifest["installer"])
        old_checksum = repo / "site" / "downloads" / str(before_manifest["checksum"])
        target_installer = repo / "site" / "downloads" / f"OutPOSt-Accounting-Setup-v{target}.exe"
        target_checksum = repo / "site" / "downloads" / f"OutPOSt-Accounting-Setup-v{target}.sha256.txt"

        # Synthetic PE headers exercise integrity, NOT real Windows acceptance.
        target_installer.write_bytes(synthetic_pe(128 * 1024))
        missing_evidence = run(repo, target, expect=1)
        assert "required release evidence" in missing_evidence.stdout
        evidence = write_synthetic_receipt(repo, target_installer, "accounting", target)
        evidence_original = evidence.read_text(encoding="utf-8")
        for field, value in (("windows_acceptance", "NOT_VERIFIED"), ("approved_for_publication", False), ("product", "outpost")):
            evidence.write_text(json.dumps(dict(json.loads(evidence_original), **{field: value})), encoding="utf-8")
            rejected_evidence = run(repo, target, "--apply", expect=1)
            assert "Accounting release preparation: FAIL" in rejected_evidence.stdout
            assert json.loads(manifest_path.read_text(encoding="utf-8")) == before_manifest
            assert not target_checksum.exists()
        evidence.write_text(evidence_original, encoding="utf-8")
        changelog_path = repo / "site/changelog.html"
        changelog_path.write_text(changelog_path.read_text(encoding="utf-8").replace(
            "</main>", f'<section id="accounting-{target.replace(".", "")}"><h2>Бухгалтерія {target}</h2><p>Синтетичний приклад тільки для тесту.</p></section></main>', 1), encoding="utf-8", newline="\n")

        protected_before = {name: digest(repo / name) for name in PROTECTED}
        stable_installers = sorted((repo / "site" / "downloads").glob("OutPOSt-Setup-v*.exe"))
        stable_checksums = sorted((repo / "site" / "downloads").glob("OutPOSt-Setup-v*.sha256.txt"))
        stable_before = {str(path.relative_to(repo)): digest(path) for path in stable_installers + stable_checksums}
        download_before = (repo / "site" / "download.html").read_text(encoding="utf-8")
        stable_download_half = download_before.split('data-download-product="accounting"', 1)[0]

        rejected = run(repo, target, "--rc-acceptance", "NOT_VERIFIED", expect=1)
        assert "RC assertion does not match" in rejected.stdout
        rejected_signature = run(repo, target, "--authenticode", "signed", expect=1)
        assert "Authenticode assertion does not match" in rejected_signature.stdout
        dry = run(repo, target, "--authenticode", "unsigned")
        assert "PLAN PASS" in dry.stdout
        assert not target_checksum.exists(), "dry-run must not create checksum"
        assert old_installer.exists() and old_checksum.exists(), "dry-run must not remove current artifacts"
        assert json.loads(manifest_path.read_text(encoding="utf-8")) == before_manifest, "dry-run changed manifest"

        # Compatibility flag is harmless; retention is mandatory, including default apply.
        with tempfile.TemporaryDirectory(prefix="outpost-accounting-retained-") as retained_temp:
            retained = Path(retained_temp) / "repo"
            shutil.copytree(repo, retained)
            historical = {
                p.name: digest(p)
                for p in (old_installer, old_checksum)
            }
            kept = run(retained, target, "--keep-previous", "--apply")
            assert "retain previous artifacts" in kept.stdout
            for name, expected in historical.items():
                kept_path = retained / "site" / "downloads" / name
                assert kept_path.exists() and digest(kept_path) == expected
            assert (retained / "site" / "downloads" / target_checksum.name).exists()

        applied = run(
            repo,
            target,
            "--rc-acceptance",
            "PASS",
            "--authenticode",
            "unsigned",
            "--apply",
        )
        assert "APPLIED" in applied.stdout

        after = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert after["version"] == target
        assert after["installer"] == target_installer.name
        assert after["checksum"] == target_checksum.name
        assert after["windows_rc_acceptance"] == "PASS"
        assert after["authenticode_signed"] is False
        assert after["size_bytes"] == target_installer.stat().st_size
        assert len(after["sha256"]) == 64
        assert target_checksum.is_file()
        assert old_installer.exists() and old_checksum.exists(), "historical Accounting URLs must remain available"
        for name, expected in historical.items():
            assert digest(repo / "site/downloads" / name) == expected
        assert f"Бухгалтерія v{target}" in (repo / "site/features.html").read_text(encoding="utf-8")

        checksum_line = target_checksum.read_text(encoding="utf-8").strip()
        assert checksum_line == f"{after['sha256']} *{target_installer.name}"

        accounting_page = (repo / "site" / "buhgalteriya.html").read_text(encoding="utf-8")
        download_after = (repo / "site" / "download.html").read_text(encoding="utf-8")
        assert f"v{target}" in accounting_page and f"v{current}" not in accounting_page
        assert target_installer.name in accounting_page and target_checksum.name in accounting_page
        assert f"Бухгалтерію v{target}" in download_after
        assert stable_download_half == download_after.split('data-download-product="accounting"', 1)[0]

        for name, expected in protected_before.items():
            assert digest(repo / name) == expected, f"protected file changed: {name}"
        for name, expected in stable_before.items():
            assert digest(repo / name) == expected, f"stable OutPOSt artifact changed: {name}"

        verify = subprocess.run(
            [sys.executable, "scripts/verify_accounting_release.py"],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if verify.returncode != 0:
            raise AssertionError(f"generated Accounting release failed its source guard:\n{verify.stdout}")

        missing = next_version(target)
        failed = run(repo, missing, expect=1)
        assert "required release evidence" in failed.stdout

        same = run(repo, target, expect=1)
        assert "must be newer" in same.stdout

        print("Accounting release synthetic regression: PASS")
        print(f"  simulated v{current} -> v{target}")
        print("  dry-run was read-only; apply generated checksum/manifest/pages and preserved all historical artifacts")
        print("  stable OutPOSt installer/checksum/changelog and protected Worker/Cloudflare files stayed byte-identical")
        print("  missing/non-new versions, missing evidence and unsupported RC/signature assertions fail closed")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
