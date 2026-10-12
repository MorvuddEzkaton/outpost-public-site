"""Immutable artifact inventory and hash-bound, owner-reviewed Windows receipts.

Receipts are attestations, NOT signatures or a substitute for Windows testing.
The owner must compare their report digests with private build/acceptance reports
before approving the protected release PR. This module never reads private data,
deploys, signs an installer, or sends a notification.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "release/artifact-registry.json"
INITIAL_PUBLIC_SNAPSHOT = "b3fde0215700028a29b82cd6928a7517bf26d304"
PRODUCTS = {"outpost": "OutPOSt-Setup-v", "accounting": "OutPOSt-Accounting-Setup-v"}
SHA = re.compile(r"[A-F0-9]{64}")
SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
ROW_KEYS = {"product", "version", "installer", "checksum", "size_bytes", "sha256", "checksum_sha256"}
RECEIPT_KEYS = {"schema_version", "kind", "product", "version", "installer", "size_bytes", "sha256",
                "payload_manifest_sha256", "release_report_sha256", "windows_report_sha256", "windows_acceptance",
                "runtime", "architecture", "app_authenticode", "setup_authenticode", "published_date",
                "approved_for_publication"}


class IntegrityError(RuntimeError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def parse_json(text: str):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise IntegrityError("duplicate JSON key")
            value[key] = item
        return value
    try:
        return json.loads(text, object_pairs_hook=unique)
    except (ValueError, TypeError) as exc:
        raise IntegrityError("invalid release JSON") from exc


def read_json(path: Path):
    try:
        return parse_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise IntegrityError(f"required release evidence/registry missing: {path.name}") from exc


def validate_registry(value: dict) -> list[dict]:
    if not isinstance(value, dict) or set(value) != {"schema_version", "artifacts"} or type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise IntegrityError("invalid artifact registry schema")
    rows = value["artifacts"]
    if not isinstance(rows, list) or not rows:
        raise IntegrityError("artifact registry must not be empty")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_KEYS:
            raise IntegrityError("invalid artifact registry row")
        product, version = row["product"], row["version"]
        if product not in PRODUCTS or not isinstance(version, str):
            raise IntegrityError("unknown artifact product/version")
        # Sole legacy URL, preserved without extending new version rules.
        if not SEMVER.fullmatch(version) and (product, version) != ("outpost", "0.24"):
            raise IntegrityError("invalid artifact version")
        expected = PRODUCTS[product] + version
        if row["installer"] != expected + ".exe" or row["checksum"] != expected + ".sha256.txt":
            raise IntegrityError("artifact product/version/filename mismatch")
        if type(row["size_bytes"]) is not int or not 0 < row["size_bytes"] <= 25 * 1024 * 1024:
            raise IntegrityError("invalid artifact size")
        for field in ("sha256", "checksum_sha256"):
            if not isinstance(row[field], str) or not SHA.fullmatch(row[field]):
                raise IntegrityError("invalid artifact digest")
        if row["installer"] in seen:
            raise IntegrityError("duplicate artifact URL")
        seen.add(row["installer"])
    return rows


def assert_append_only(before: list[dict], after: list[dict]) -> None:
    if after[:len(before)] != before:
        raise IntegrityError("historical artifact registry must be append-only; old URLs/bytes/order cannot change")


def base_registry(root: Path, base: str) -> list[dict]:
    result = subprocess.run(["git", "show", f"{base}:{REGISTRY}"], cwd=root, capture_output=True, text=True, encoding="utf-8")
    if result.returncode == 0:
        return validate_registry(parse_json(result.stdout))
    revision = subprocess.run(["git", "rev-parse", "--verify", base + "^{commit}"], cwd=root, capture_output=True, text=True)
    if revision.returncode or revision.stdout.strip() != INITIAL_PUBLIC_SNAPSHOT:
        raise IntegrityError("cannot load trusted base registry")
    # One-time bootstrapping from the independently audited initial public commit.
    # Compare the actual Git blobs, not a mutable copy of the new JSON inventory.
    listing = subprocess.run(["git", "ls-tree", "-r", "--name-only", base, "--", "site/downloads"], cwd=root, capture_output=True, text=True)
    if listing.returncode:
        raise IntegrityError("cannot inspect initial public artifacts")
    names = {Path(p).name for p in listing.stdout.splitlines()}
    rows = []
    for name in sorted(n for n in names if n.endswith(".exe")):
        product = "accounting" if name.startswith(PRODUCTS["accounting"]) else "outpost"
        version = name.removeprefix(PRODUCTS[product]).removesuffix(".exe")
        checksum = name.removesuffix(".exe") + ".sha256.txt"
        def blob(filename):
            value = subprocess.run(["git", "show", f"{base}:site/downloads/{filename}"], cwd=root, capture_output=True)
            if value.returncode:
                raise IntegrityError("initial artifact pair missing")
            return value.stdout
        exe, sha_file = blob(name), blob(checksum)
        rows.append({"product": product, "version": version, "installer": name, "checksum": checksum,
                     "size_bytes": len(exe), "sha256": hashlib.sha256(exe).hexdigest().upper(),
                     "checksum_sha256": hashlib.sha256(sha_file).hexdigest().upper()})
    validate_registry({"schema_version": 1, "artifacts": rows})
    if len(rows) != 22 or names != {name for row in rows for name in (row["installer"], row["checksum"])}:
        raise IntegrityError("initial public snapshot inventory mismatch")
    return rows


def verify_registry(root: Path = ROOT, *, allow_new: set[str] | None = None, base: str | None = None) -> list[dict]:
    rows = validate_registry(read_json(root / REGISTRY))
    allowed = allow_new or set()
    expected = set()
    for row in rows:
        installer = root / "site/downloads" / row["installer"]
        checksum = root / "site/downloads" / row["checksum"]
        if not installer.is_file() or not checksum.is_file() or installer.is_symlink() or checksum.is_symlink():
            raise IntegrityError(f"historical artifact missing/unsafe: {row['installer']}")
        if installer.stat().st_size != row["size_bytes"] or digest(installer) != row["sha256"] or digest(checksum) != row["checksum_sha256"]:
            raise IntegrityError(f"immutable artifact bytes changed: {row['installer']}")
        parts = checksum.read_text(encoding="utf-8").strip().split()
        if len(parts) != 2 or parts[0].upper() != row["sha256"] or parts[1].lstrip("*") != row["installer"]:
            raise IntegrityError(f"artifact checksum/name mismatch: {row['installer']}")
        expected.update((row["installer"], row["checksum"]))
    actual = {p.name for p in (root / "site/downloads").iterdir() if p.is_file()}
    if actual != expected | allowed:
        raise IntegrityError("downloads inventory differs from immutable registry and explicit target inputs")
    if base:
        # Literal Git revision, no shell interpolation/options; not a filesystem path.
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", base) or base.startswith("-") or ".." in base:
            raise IntegrityError("invalid registry base revision")
        assert_append_only(base_registry(root, base), rows)
    return rows


def validate_receipt(value: dict, installer: Path, product: str, version: str) -> dict:
    if not isinstance(value, dict) or set(value) != RECEIPT_KEYS:
        raise IntegrityError("receipt must contain exactly the reviewed public fields (no raw reports/paths/credentials)")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["kind"] != "owner-reviewed-windows-release":
        raise IntegrityError("unsupported Windows receipt schema/kind")
    if product not in PRODUCTS or not SEMVER.fullmatch(version):
        raise IntegrityError("new releases require known product and X.Y.Z version")
    if value["product"] != product or value["version"] != version or value["installer"] != PRODUCTS[product] + version + ".exe" or installer.name != value["installer"]:
        raise IntegrityError("Windows receipt product/version/installer mismatch")
    if value["windows_acceptance"] != "PASS" or value["approved_for_publication"] is not True:
        raise IntegrityError("Windows acceptance and owner publication approval must both be confirmed")
    if value["runtime"] != "net48" or value["architecture"] != "x86":
        raise IntegrityError("Windows runtime/architecture mismatch")
    for field in ("sha256", "payload_manifest_sha256", "release_report_sha256", "windows_report_sha256"):
        if not isinstance(value[field], str) or not SHA.fullmatch(value[field]) or len(set(value[field])) == 1:
            raise IntegrityError(f"missing/invalid evidence digest: {field}")
    for field in ("app_authenticode", "setup_authenticode"):
        if value[field] not in ("Valid", "NotSigned"):
            raise IntegrityError("unverified/invalid Authenticode state cannot be published")
    published = value["published_date"]
    if not isinstance(published, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
        raise IntegrityError("release date must be explicit YYYY-MM-DD")
    try:
        date.fromisoformat(published)
    except ValueError as exc:
        raise IntegrityError("invalid approved release date") from exc
    if not installer.is_file() or installer.is_symlink():
        raise IntegrityError("target installer missing/unsafe")
    size = installer.stat().st_size
    if type(value["size_bytes"]) is not int or not 64 <= size <= 25 * 1024 * 1024 or size != value["size_bytes"] or digest(installer) != value["sha256"]:
        raise IntegrityError("Windows receipt installer size/SHA-256 mismatch")
    with installer.open("rb") as stream:
        header = stream.read(64)
        offset = int.from_bytes(header[60:64], "little")
        if header[:2] != b"MZ" or not 64 <= offset <= size - 4:
            raise IntegrityError("installer is not a structurally valid PE file")
        stream.seek(offset)
        if stream.read(4) != b"PE\0\0":
            raise IntegrityError("installer is not a structurally valid PE file")
    return value


def load_receipt(root: Path, product: str, version: str, evidence: Path | None = None) -> dict:
    return validate_receipt(read_json(evidence or root / f"release/evidence/{product}-v{version}.json"), root / "site/downloads" / (PRODUCTS[product] + version + ".exe"), product, version)


def append_target(rows: list[dict], receipt: dict, checksum_text: str) -> dict:
    if any(row["installer"] == receipt["installer"] for row in rows):
        raise IntegrityError("target URL already published; rebuilding/replacing it is forbidden")
    row = {key: receipt[key] for key in ("product", "version", "installer", "size_bytes", "sha256")}
    row["checksum"] = receipt["installer"].removesuffix(".exe") + ".sha256.txt"
    row["checksum_sha256"] = hashlib.sha256(checksum_text.encode("utf-8")).hexdigest().upper()
    value = {"schema_version": 1, "artifacts": [*rows, row]}
    validate_registry(value)
    assert_append_only(rows, value["artifacts"])
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", help="trusted PR base SHA/ref for append-only comparison")
    args = parser.parse_args()
    try:
        rows = verify_registry(base=args.base_ref)
        print(f"Immutable release registry: PASS; {len(rows)} installer/checksum pairs verified")
        return 0
    except (IntegrityError, OSError) as exc:
        print(f"Immutable release registry: FAIL; {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
