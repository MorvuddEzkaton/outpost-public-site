#!/usr/bin/env python3
"""Verify published OutPOSt installer artifacts against their SHA-256 files."""

from __future__ import annotations

from pathlib import Path
import hashlib
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "site" / "downloads"
PATTERN = re.compile(r"^([0-9A-Fa-f]{64})\s+\*?(.+)$")
INSTALLER_GLOBS = (
    "OutPOSt-Setup-v*.exe",
    "OutPOSt-Accounting-Setup-v*.exe",
)
CHECKSUM_GLOBS = (
    "OutPOSt-Setup-v*.sha256.txt",
    "OutPOSt-Accounting-Setup-v*.sha256.txt",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def collect(patterns: tuple[str, ...]) -> list[Path]:
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(DOWNLOADS.glob(pattern))
    return sorted(paths)


def main() -> int:
    errors: list[str] = []
    installers = collect(INSTALLER_GLOBS)
    checksum_files = collect(CHECKSUM_GLOBS)
    main_installers = sorted(DOWNLOADS.glob("OutPOSt-Setup-v*.exe"))

    if not main_installers:
        print("Installer checksum guard: FAIL\n  - no main OutPOSt installer artifact found")
        return 1

    installer_names = {path.name for path in installers}
    expected_checksum_names = {f"{path.stem}.sha256.txt" for path in installers}
    actual_checksum_names = {path.name for path in checksum_files}

    missing_checksums = sorted(expected_checksum_names - actual_checksum_names)
    extra_checksums = sorted(actual_checksum_names - expected_checksum_names)
    for name in missing_checksums:
        errors.append(f"missing checksum file: site/downloads/{name}")
    for name in extra_checksums:
        errors.append(f"checksum exists without matching installer: site/downloads/{name}")

    checked = 0
    for installer in installers:
        checksum_path = DOWNLOADS / f"{installer.stem}.sha256.txt"
        if not checksum_path.is_file():
            continue

        raw = checksum_path.read_text(encoding="utf-8").strip()
        match = PATTERN.fullmatch(raw)
        if not match:
            errors.append(f"invalid checksum format: site/downloads/{checksum_path.name}")
            continue

        expected_hash = match.group(1).upper()
        expected_filename = match.group(2).strip()
        if expected_filename != installer.name:
            errors.append(
                f"{checksum_path.name}: filename mismatch; expected {installer.name!r}, got {expected_filename!r}"
            )
            continue

        actual_hash = sha256(installer)
        if actual_hash != expected_hash:
            errors.append(
                f"{installer.name}: SHA-256 mismatch; published {expected_hash}, actual {actual_hash}"
            )
            continue

        checked += 1

    # Every public executable must match one of the explicitly supported product names.
    unpaired_exes = [path.name for path in DOWNLOADS.glob("*.exe") if path.name not in installer_names]
    for name in sorted(unpaired_exes):
        errors.append(f"unrecognized executable in public downloads: site/downloads/{name}")

    if errors:
        print(f"Installer checksum guard: FAIL ({len(errors)} issue(s))")
        for error in errors:
            print(f"  - {error}")
        return 1

    accounting_count = len(list(DOWNLOADS.glob("OutPOSt-Accounting-Setup-v*.exe")))
    print("Installer checksum guard: PASS")
    print(f"  verified {checked} installer/checksum pair(s)")
    print(f"  recognized {len(main_installers)} main OutPOSt installer(s) and {accounting_count} Accounting installer(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
