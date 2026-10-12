"""Test-only synthetic PE headers/receipts; never real Windows acceptance."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
from release_integrity import digest


def synthetic_pe(size: int = 4096) -> bytes:
    data = bytearray(b"X" * max(size, 128))
    data[:2] = b"MZ"
    data[60:64] = (64).to_bytes(4, "little")
    data[64:68] = b"PE\0\0"
    return bytes(data)


def synthetic_receipt(installer: Path, product: str, version: str) -> dict:
    # Dummy digests and PASS exercise validation only, in isolated test directories.
    def fake_hash(label):
        return hashlib.sha256(("SYNTHETIC-NOT-WINDOWS-EVIDENCE-" + label).encode()).hexdigest().upper()
    return {"schema_version": 1, "kind": "owner-reviewed-windows-release", "product": product,
            "version": version, "installer": installer.name, "size_bytes": installer.stat().st_size,
            "sha256": digest(installer), "payload_manifest_sha256": fake_hash("payload"),
            "release_report_sha256": fake_hash("build"), "windows_report_sha256": fake_hash("windows"),
            "windows_acceptance": "PASS", "runtime": "net48", "architecture": "x86",
            "app_authenticode": "NotSigned", "setup_authenticode": "NotSigned",
            "published_date": datetime.now(ZoneInfo("Europe/Kyiv")).date().isoformat(),
            "approved_for_publication": True}


def write_synthetic_receipt(root: Path, installer: Path, product: str, version: str) -> Path:
    path = root / f"release/evidence/{product}-v{version}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(synthetic_receipt(installer, product, version), indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def fixture_row(installer: Path, product: str, version: str) -> dict:
    checksum = installer.with_suffix(".sha256.txt")
    return {"product": product, "version": version, "installer": installer.name, "checksum": checksum.name,
            "size_bytes": installer.stat().st_size, "sha256": digest(installer), "checksum_sha256": digest(checksum)}
