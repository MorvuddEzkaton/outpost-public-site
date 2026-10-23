#!/usr/bin/env python3
"""Fail-closed Dropbox importer: only a reviewed Windows installer is accepted.

The caller must check the trusted main->staging diff before executing this file.
Requires Python 3.12+, stdlib only, and the three Dropbox secrets in environment.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from release_integrity import IntegrityError, load_receipt

ROOT = Path(__file__).resolve().parents[1]
DROPBOX_DIR = "/OutPOSt/git-work/outpost-02410-redesign/dist"
MAX_BYTES = 25 * 1024 * 1024
VERSION = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z")
CHECKSUM = re.compile(r"([A-Fa-f0-9]{64}) \*?(OutPOSt-Setup-v[0-9.]+\.exe)\Z")


def validated_inputs(version: str) -> tuple[Path, int, str]:
    if not VERSION.fullmatch(version):
        raise ValueError("version must be X.Y.Z")
    basename = f"OutPOSt-Setup-v{version}.exe"
    target = ROOT / "site" / "downloads" / basename
    sha_file = target.with_suffix(".sha256.txt")
    receipt_file = ROOT / "release" / "evidence" / f"outpost-v{version}.json"
    if target.exists() or target.is_symlink():
        raise ValueError("installer already exists; importer never overwrites artifacts")
    if not sha_file.is_file() or sha_file.is_symlink() or not receipt_file.is_file() or receipt_file.is_symlink():
        raise ValueError("checksum and Windows owner-reviewed receipt must already be staged")
    match = CHECKSUM.fullmatch(sha_file.read_text(encoding="utf-8").strip())
    if match is None or match.group(2) != basename:
        raise ValueError("invalid target checksum text or filename")
    expected_sha = match.group(1).upper()
    with receipt_file.open(encoding="utf-8") as stream:
        receipt = json.load(stream)
    if not isinstance(receipt, dict) or receipt.get("windows_acceptance") != "PASS" or receipt.get("approved_for_publication") is not True:
        raise ValueError("specific Windows acceptance and owner approval are required")
    if receipt.get("sha256") != expected_sha or receipt.get("installer") != basename or receipt.get("version") != version:
        raise ValueError("Windows receipt must match the exact installer and checksum")
    size = receipt.get("size_bytes")
    if type(size) is not int or not 64 <= size <= MAX_BYTES:
        raise ValueError("invalid reviewed installer size")
    return target, size, expected_sha


def access_token(opener=urlopen) -> str:
    key = os.environ.get("OUTPOST_DROPBOX_APP_KEY", "")
    secret = os.environ.get("OUTPOST_DROPBOX_APP_SECRET", "")
    refresh = os.environ.get("OUTPOST_DROPBOX_REFRESH_TOKEN", "")
    if not key or not secret or not refresh:
        raise ValueError("Dropbox OAuth secrets are not configured")
    payload = urlencode({"grant_type": "refresh_token", "refresh_token": refresh, "client_id": key,
                         "client_secret": secret}).encode("ascii")
    request = Request("https://api.dropboxapi.com/oauth2/token", data=payload,
                      headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with opener(request, timeout=30) as response:
        data = json.load(response)
    token = data.get("access_token") if isinstance(data, dict) else None
    if not isinstance(token, str) or not token:
        raise ValueError("Dropbox did not return an access token")
    return token


def download(version: str, target: Path, expected_size: int, expected_sha: str, token: str, opener=urlopen) -> None:
    name = target.name
    path = f"{DROPBOX_DIR}/{name}"
    request = Request("https://content.dropboxapi.com/2/files/download", data=b"",
                      headers={"Authorization": f"Bearer {token}", "Dropbox-API-Arg": json.dumps({"path": path}, ensure_ascii=True)},
                      method="POST")
    digest = hashlib.sha256()
    length = 0
    temporary = None
    try:
        with opener(request, timeout=120) as response:
            metadata = json.loads(response.headers.get("Dropbox-API-Result", "{}"))
            if metadata.get("name") != name or metadata.get("size") != expected_size:
                raise ValueError("Dropbox metadata differs from owner-reviewed installer")
            with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{name}.", suffix=".tmp", dir=target.parent, delete=False) as output:
                temporary = Path(output.name)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    length += len(chunk)
                    if length > MAX_BYTES or length > expected_size:
                        raise ValueError("Dropbox download exceeds reviewed size limit")
                    digest.update(chunk)
                    output.write(chunk)
        if length != expected_size or digest.hexdigest().upper() != expected_sha:
            raise ValueError("Dropbox installer byte count or SHA-256 mismatch")
        # The receipt schema and PE32 checks are shared with the public-release gate.
        temporary.replace(target)
        try:
            load_receipt(ROOT, "outpost", version)
        except Exception:
            target.unlink(missing_ok=True)
            raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise ValueError("usage: import_dropbox_installer.py X.Y.Z")
        version = sys.argv[1]
        target, size, sha = validated_inputs(version)
        token = access_token()
        download(version, target, size, sha, token)
        print(f"Verified Dropbox installer staged: {target.name} ({size} bytes, SHA-256 {sha})")
        return 0
    except (ValueError, IntegrityError, HTTPError, URLError, OSError, json.JSONDecodeError) as error:
        # Never include response bodies/URLs, request arguments or OAuth tokens in logs.
        kind = "HTTP error" if isinstance(error, HTTPError) else type(error).__name__
        print(f"Dropbox installer import BLOCKED ({kind}); no unverified artifact accepted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
