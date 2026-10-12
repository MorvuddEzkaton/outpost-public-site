#!/usr/bin/env python3
"""Read-only post-deploy verification for the live OutPOSt public site.

The verifier derives the expected current release from the checked-out repository,
waits for Cloudflare Pages propagation, then validates the production HTML,
checksum file and installer bytes.

Important: the installer is fetched with an HTTP Range request and a 206 response is
required. The public Pages Worker intentionally excludes range/resume requests from
download analytics, so this verification must not inflate the download counter.
"""

from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import hashlib
import os
import re
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DOWNLOAD_PAGE = SITE / "download.html"
DOWNLOADS = SITE / "downloads"
ORIGIN = "https://outpost.com.ua"
USER_AGENT = "OutPOSt-Production-Verify/1.0"

VERSION_RE = re.compile(r"OutPOSt-Setup-v(\d+\.\d+\.\d+)\.exe")
CHECKSUM_RE = re.compile(r"^([A-Fa-f0-9]{64})\s+\*?([^\s]+)\s*$")
HOMEPAGE_HASH_RE = re.compile(
    r'<code[^>]*id=["\']setup-hash["\'][^>]*>\s*([A-Fa-f0-9]{64})\s*</code>',
    re.IGNORECASE,
)


class VerifyError(RuntimeError):
    pass


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def expected_release() -> tuple[str, str, str, int, str]:
    html = read_text(DOWNLOAD_PAGE)
    versions = set(VERSION_RE.findall(html))
    if len(versions) != 1:
        raise VerifyError(f"local download page must reference one release; got {sorted(versions)!r}")

    version = next(iter(versions))
    exe_name = f"OutPOSt-Setup-v{version}.exe"
    checksum_name = f"OutPOSt-Setup-v{version}.sha256.txt"
    exe_path = DOWNLOADS / exe_name
    checksum_path = DOWNLOADS / checksum_name

    if not exe_path.is_file():
        raise VerifyError(f"local installer missing: {exe_path}")
    if not checksum_path.is_file():
        raise VerifyError(f"local checksum missing: {checksum_path}")

    match = CHECKSUM_RE.fullmatch(read_text(checksum_path).strip())
    if not match:
        raise VerifyError(f"invalid local checksum format: {checksum_path}")

    expected_sha = match.group(1).upper()
    if match.group(2) != exe_name:
        raise VerifyError("local checksum filename does not match current installer")

    return version, exe_name, checksum_name, exe_path.stat().st_size, expected_sha


def request_bytes(url: str, *, range_request: bool = False, timeout: int = 30) -> tuple[int, dict[str, str], bytes]:
    headers = {
        "User-Agent": USER_AGENT,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Accept": "*/*",
    }
    if range_request:
        # Full representation via a range request. The Worker excludes range/resume
        # requests from the aggregate installer download counter.
        headers["Range"] = "bytes=0-"

    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return status, response_headers, response.read()
    except HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        raise VerifyError(f"HTTP {exc.code} for {url}; body={body[:160]!r}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise VerifyError(f"request failed for {url}: {exc}") from exc


def cache_busted(path: str, attempt: int) -> str:
    query = urlencode({"outpost_verify": f"{int(time.time())}-{attempt}"})
    return f"{ORIGIN}{path}?{query}"


def verify_html(version: str, exe_name: str, expected_sha: str, attempt: int) -> None:
    expected_version_markers = (f"OutPOSt v{version}", f"v{version}")

    for path in ("/", "/download"):
        status, _, payload = request_bytes(cache_busted(path, attempt), timeout=20)
        if status != 200:
            raise VerifyError(f"{path}: expected HTTP 200, got {status}")
        text = payload.decode("utf-8", errors="replace")
        if not any(marker in text for marker in expected_version_markers):
            raise VerifyError(f"{path}: current release v{version} is not visible yet")
        if exe_name not in text:
            raise VerifyError(f"{path}: current installer marker {exe_name!r} is not visible yet")

        if path == "/":
            homepage_hashes = HOMEPAGE_HASH_RE.findall(text)
            if len(homepage_hashes) != 1:
                raise VerifyError(
                    f"/: expected exactly one live #setup-hash value, got {len(homepage_hashes)}"
                )
            if homepage_hashes[0].upper() != expected_sha:
                raise VerifyError(
                    f"/: live #setup-hash mismatch: expected {expected_sha}, got {homepage_hashes[0].upper()}"
                )


def verify_checksum(checksum_name: str, exe_name: str, expected_sha: str, attempt: int) -> None:
    status, _, payload = request_bytes(cache_busted(f"/downloads/{checksum_name}", attempt), timeout=20)
    if status != 200:
        raise VerifyError(f"live checksum: expected HTTP 200, got {status}")
    text = payload.decode("utf-8", errors="strict").strip()
    match = CHECKSUM_RE.fullmatch(text)
    if not match:
        raise VerifyError("live checksum file has invalid format")
    if match.group(1).upper() != expected_sha:
        raise VerifyError("live checksum SHA-256 differs from repository")
    if match.group(2) != exe_name:
        raise VerifyError("live checksum filename differs from current installer")


def verify_installer(exe_name: str, expected_size: int, expected_sha: str) -> None:
    status, headers, payload = request_bytes(f"{ORIGIN}/downloads/{exe_name}", range_request=True, timeout=120)
    if status != 206:
        raise VerifyError(
            f"live installer range verification requires HTTP 206 (analytics-safe), got {status}; refusing a normal GET verification"
        )

    content_range = headers.get("content-range", "")
    if content_range and f"/{expected_size}" not in content_range:
        raise VerifyError(f"live installer Content-Range total does not match {expected_size}: {content_range!r}")

    actual_size = len(payload)
    if actual_size != expected_size:
        raise VerifyError(f"live installer size mismatch: expected {expected_size}, got {actual_size}")

    actual_sha = hashlib.sha256(payload).hexdigest().upper()
    if actual_sha != expected_sha:
        raise VerifyError(f"live installer SHA-256 mismatch: expected {expected_sha}, got {actual_sha}")


def main() -> int:
    try:
        version, exe_name, checksum_name, expected_size, expected_sha = expected_release()
    except Exception as exc:
        print(f"OutPOSt live production verification: FAIL\n  - {exc}", file=sys.stderr)
        return 1

    attempts = max(1, int(os.environ.get("OUTPOST_LIVE_VERIFY_ATTEMPTS", "18")))
    delay = max(0, int(os.environ.get("OUTPOST_LIVE_VERIFY_DELAY_SECONDS", "10")))
    last_error: Exception | None = None

    print(f"Expected production release: v{version}")
    print(f"Expected installer: {exe_name}")
    print(f"Expected bytes: {expected_size}")
    print(f"Expected SHA-256: {expected_sha}")

    for attempt in range(1, attempts + 1):
        try:
            verify_html(version, exe_name, expected_sha, attempt)
            verify_checksum(checksum_name, exe_name, expected_sha, attempt)
            print(f"Cloudflare production metadata converged on attempt {attempt}/{attempts}")
            break
        except Exception as exc:
            last_error = exc
            print(f"Attempt {attempt}/{attempts}: not converged yet: {exc}")
            if attempt < attempts:
                time.sleep(delay)
    else:
        print(f"OutPOSt live production verification: FAIL\n  - {last_error}", file=sys.stderr)
        return 1

    try:
        verify_installer(exe_name, expected_size, expected_sha)
    except Exception as exc:
        print(f"OutPOSt live production verification: FAIL\n  - {exc}", file=sys.stderr)
        return 1

    print("OutPOSt live production verification: PASS")
    print(f"  live / and /download expose v{version} and {exe_name}")
    print("  live homepage #setup-hash matches the repository checksum")
    print("  live checksum file matches the repository")
    print("  live installer returned HTTP 206 and matches repository byte size + SHA-256")
    print("  range verification avoids inflating installer download analytics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
