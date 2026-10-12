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
        shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))

        manifest_path = repo / "release" / "accounting-release.json"
        before_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        current = str(before_manifest["version"])
        target = next_version(current)
        old_installer = repo / "site" / "downloads" / str(before_manifest["installer"])
        old_checksum = repo / "site" / "downloads" / str(before_manifest["checksum"])
        target_installer = repo / "site" / "downloads" / f"OutPOSt-Accounting-Setup-v{target}.exe"
        target_checksum = repo / "site" / "downloads" / f"OutPOSt-Accounting-Setup-v{target}.sha256.txt"

        # A deterministic synthetic binary is enough: the updater treats the EXE as opaque bytes.
        target_installer.write_bytes((b"OUTPOST-ACCOUNTING-SYNTHETIC-RELEASE\n" * 4096) + b"EOF")

        protected_before = {name: digest(repo / name) for name in PROTECTED}
        stable_installers = sorted((repo / "site" / "downloads").glob("OutPOSt-Setup-v*.exe"))
        stable_checksums = sorted((repo / "site" / "downloads").glob("OutPOSt-Setup-v*.sha256.txt"))
        stable_before = {str(path.relative_to(repo)): digest(path) for path in stable_installers + stable_checksums}
        download_before = (repo / "site" / "download.html").read_text(encoding="utf-8")
        stable_download_half = download_before.split('data-download-product="accounting"', 1)[0]

        dry = run(repo, target, "--rc-acceptance", "NOT_VERIFIED", "--authenticode", "unsigned")
        assert "PLAN PASS" in dry.stdout
        assert not target_checksum.exists(), "dry-run must not create checksum"
        assert old_installer.exists() and old_checksum.exists(), "dry-run must not remove current artifacts"
        assert json.loads(manifest_path.read_text(encoding="utf-8")) == before_manifest, "dry-run changed manifest"

        # Retention mode is opt-in and must preserve exact historical bytes.
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
            "NOT_VERIFIED",
            "--authenticode",
            "unsigned",
            "--apply",
        )
        assert "APPLIED" in applied.stdout

        after = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert after["version"] == target
        assert after["installer"] == target_installer.name
        assert after["checksum"] == target_checksum.name
        assert after["windows_rc_acceptance"] == "NOT_VERIFIED"
        assert after["authenticode_signed"] is False
        assert after["size_bytes"] == target_installer.stat().st_size
        assert len(after["sha256"]) == 64
        assert target_checksum.is_file()
        assert not old_installer.exists() and not old_checksum.exists(), "previous Accounting artifacts were not retired"

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
        assert "target Accounting installer is missing" in failed.stdout

        same = run(repo, target, expect=1)
        assert "must be newer" in same.stdout

        print("Accounting release synthetic regression: PASS")
        print(f"  simulated v{current} -> v{target}")
        print("  dry-run was read-only; apply generated checksum/manifest/pages and retired old Accounting artifacts")
        print("  stable OutPOSt installer/checksum/changelog and protected Worker/Cloudflare files stayed byte-identical")
        print("  missing and non-new target versions fail closed")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
