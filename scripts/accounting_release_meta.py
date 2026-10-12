#!/usr/bin/env python3
"""Canonical metadata helpers for the published OutPOSt Accounting pre-release."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release" / "accounting-release.json"
VERSION_RE = re.compile(r"^\d+(?:\.\d+){1,3}$")
SHA256_RE = re.compile(r"^[A-F0-9]{64}$")


class AccountingReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class AccountingRelease:
    version: str
    status: str
    installer: str
    checksum: str
    size_bytes: int
    sha256: str
    display_size_mb: str
    platform: str
    runtime: str
    architecture: str
    windows_rc_acceptance: str
    authenticode_signed: bool
    published_date: str


def decimal_mb_comma(size_bytes: int) -> str:
    return f"{size_bytes / 1_000_000:.1f}".replace(".", ",")


def spaced_bytes(size_bytes: int) -> str:
    return f"{size_bytes:,}".replace(",", " ")


def version_key(value: str) -> tuple[int, int, int, int]:
    if not VERSION_RE.fullmatch(value):
        raise AccountingReleaseError(f"invalid Accounting version {value!r}; expected numeric dotted version")
    parts = [int(part) for part in value.split(".")]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])  # type: ignore[return-value]


def rc_sentence(value: str) -> str:
    if value == "PASS":
        return "Windows RC acceptance: PASS"
    if value == "NOT_VERIFIED":
        return "Windows RC acceptance: ще не підтверджено"
    raise AccountingReleaseError(f"unsupported windows_rc_acceptance: {value!r}")


def rc_card_label(value: str) -> str:
    if value == "PASS":
        return "Windows RC 406/406 PASS"
    if value == "NOT_VERIFIED":
        return "Windows RC не підтверджено"
    raise AccountingReleaseError(f"unsupported windows_rc_acceptance: {value!r}")


def authenticode_phrase(signed: bool) -> str:
    return "має Authenticode-підпис" if signed else "не має Authenticode-підпису"


def validate_manifest(data: dict) -> AccountingRelease:
    required = {
        "version",
        "status",
        "installer",
        "checksum",
        "size_bytes",
        "sha256",
        "display_size_mb",
        "platform",
        "runtime",
        "architecture",
        "windows_rc_acceptance",
        "authenticode_signed",
        "published_date",
    }
    missing = sorted(required - data.keys())
    extra = sorted(data.keys() - required)
    if missing or extra:
        raise AccountingReleaseError(f"Accounting manifest keys mismatch; missing={missing}, extra={extra}")

    version = str(data["version"])
    version_key(version)
    installer = str(data["installer"])
    checksum = str(data["checksum"])
    expected_installer = f"OutPOSt-Accounting-Setup-v{version}.exe"
    expected_checksum = f"OutPOSt-Accounting-Setup-v{version}.sha256.txt"
    if installer != expected_installer:
        raise AccountingReleaseError(f"manifest installer must be {expected_installer!r}, got {installer!r}")
    if checksum != expected_checksum:
        raise AccountingReleaseError(f"manifest checksum must be {expected_checksum!r}, got {checksum!r}")

    size_bytes = data["size_bytes"]
    if not isinstance(size_bytes, int) or size_bytes <= 0:
        raise AccountingReleaseError("manifest size_bytes must be a positive integer")
    display_size_mb = str(data["display_size_mb"])
    expected_display = decimal_mb_comma(size_bytes)
    if display_size_mb != expected_display:
        raise AccountingReleaseError(
            f"manifest display_size_mb must be {expected_display!r} for {size_bytes} bytes, got {display_size_mb!r}"
        )

    sha256 = str(data["sha256"]).upper()
    if not SHA256_RE.fullmatch(sha256):
        raise AccountingReleaseError("manifest sha256 must be exactly 64 hexadecimal characters")

    status = str(data["status"])
    if status != "Pre-release":
        raise AccountingReleaseError("Accounting site automation currently supports status='Pre-release' only")

    rc = str(data["windows_rc_acceptance"])
    rc_sentence(rc)
    signed = data["authenticode_signed"]
    if not isinstance(signed, bool):
        raise AccountingReleaseError("manifest authenticode_signed must be boolean")

    published = str(data["published_date"])
    try:
        date.fromisoformat(published)
    except ValueError as exc:
        raise AccountingReleaseError(f"invalid published_date {published!r}; expected YYYY-MM-DD") from exc

    text_fields = {
        "platform": data["platform"],
        "runtime": data["runtime"],
        "architecture": data["architecture"],
    }
    for name, value in text_fields.items():
        if not isinstance(value, str) or not value.strip():
            raise AccountingReleaseError(f"manifest {name} must be a non-empty string")

    return AccountingRelease(
        version=version,
        status=status,
        installer=installer,
        checksum=checksum,
        size_bytes=size_bytes,
        sha256=sha256,
        display_size_mb=display_size_mb,
        platform=str(data["platform"]),
        runtime=str(data["runtime"]),
        architecture=str(data["architecture"]),
        windows_rc_acceptance=rc,
        authenticode_signed=signed,
        published_date=published,
    )


def load_accounting_release(path: Path = MANIFEST) -> AccountingRelease:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AccountingReleaseError(f"cannot read Accounting release manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise AccountingReleaseError("Accounting release manifest root must be an object")
    return validate_manifest(raw)


def manifest_dict(release: AccountingRelease) -> dict:
    return {
        "version": release.version,
        "status": release.status,
        "installer": release.installer,
        "checksum": release.checksum,
        "size_bytes": release.size_bytes,
        "sha256": release.sha256,
        "display_size_mb": release.display_size_mb,
        "platform": release.platform,
        "runtime": release.runtime,
        "architecture": release.architecture,
        "windows_rc_acceptance": release.windows_rc_acceptance,
        "authenticode_signed": release.authenticode_signed,
        "published_date": release.published_date,
    }
