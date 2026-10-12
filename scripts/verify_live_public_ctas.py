#!/usr/bin/env python3
"""Read-only production checks for OutPOSt public conversion paths.

Only public outpost.com.ua pages and an analytics-safe 1-byte installer Range request
are used. The script never calls Customer Portal, Director, Sync, D1, PRRO or RRO
endpoints.
"""

from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import re
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ORIGIN = "https://outpost.com.ua"
USER_AGENT = "OutPOSt-Public-CTA-Verify/1.0"
EMAIL = "roman@outpost.com.ua"
PHONE_HREF = "tel:+380993210872"
TELEGRAM = "https://t.me/OutPOStUA_bot"

VERSION_RE = re.compile(r"OutPOSt-Setup-v(\d+\.\d+\.\d+)\.exe")
CFEMAIL_RE = re.compile(r'data-cfemail=["\']([0-9a-fA-F]+)["\']')
CFHREF_RE = re.compile(
    r'href=["\'](?:https://outpost\.com\.ua)?/cdn-cgi/l/email-protection#([0-9a-fA-F]+)(?:\?[^"\']*)?["\']',
    re.IGNORECASE,
)


class VerifyError(RuntimeError):
    pass


def request(path: str, *, range_request: bool = False, timeout: int = 30) -> tuple[int, dict[str, str], bytes]:
    suffix = "&" if "?" in path else "?"
    url = f"{ORIGIN}{path}{suffix}{urlencode({'cta_verify': int(time.time() * 1000)})}"
    headers = {
        "User-Agent": USER_AGENT,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Accept": "*/*",
    }
    if range_request:
        headers["Range"] = "bytes=0-0"
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return status, response_headers, response.read()
    except HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        raise VerifyError(f"HTTP {exc.code} for {url}; body={body[:160]!r}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise VerifyError(f"request failed for {url}: {exc}") from exc


def decode_cfemail(value: str) -> str | None:
    try:
        raw = bytes.fromhex(value)
    except ValueError:
        return None
    if len(raw) < 2:
        return None
    key = raw[0]
    return bytes(byte ^ key for byte in raw[1:]).decode("utf-8", errors="replace")


def verify_email(text: str, headers: dict[str, str], path: str) -> None:
    if f"mailto:{EMAIL}" in text:
        return

    protected_values = CFEMAIL_RE.findall(text) + CFHREF_RE.findall(text)
    decoded = {decoded for value in protected_values if (decoded := decode_cfemail(value))}
    if EMAIL not in decoded:
        raise VerifyError(
            f"{path}: public email is neither plain mailto nor valid Cloudflare email protection"
        )

    if "email-decode.min.js" not in text:
        raise VerifyError(f"{path}: Cloudflare-obfuscated email lacks decoder script")

    csp = headers.get("content-security-policy", "")
    if csp:
        directives: dict[str, str] = {}
        for part in csp.split(";"):
            tokens = part.strip().split()
            if tokens:
                directives[tokens[0].lower()] = " ".join(tokens[1:])
        script_policy = directives.get("script-src", directives.get("default-src", ""))
        if "'self'" not in script_policy:
            raise VerifyError(f"{path}: CSP would not allow same-origin Cloudflare email decoder")


def get_html(path: str, required: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    status, headers, payload = request(path, timeout=25)
    if status != 200:
        raise VerifyError(f"{path}: expected HTTP 200, got {status}")
    text = payload.decode("utf-8", errors="replace")
    for marker in required:
        if marker not in text:
            raise VerifyError(f"{path}: missing live CTA marker {marker!r}")
    return text, headers


def current_installer() -> tuple[str, int]:
    source = (SITE / "download.html").read_text(encoding="utf-8")
    versions = set(VERSION_RE.findall(source))
    if len(versions) != 1:
        raise VerifyError(f"local download page must reference one current release, got {sorted(versions)!r}")
    version = next(iter(versions))
    name = f"OutPOSt-Setup-v{version}.exe"
    path = SITE / "downloads" / name
    if not path.is_file():
        raise VerifyError(f"local installer missing: {path}")
    return name, path.stat().st_size


def verify_installer_range() -> None:
    name, size = current_installer()
    status, headers, payload = request(f"/downloads/{name}", range_request=True, timeout=40)
    if status != 206:
        raise VerifyError(f"installer CTA: analytics-safe Range request must return 206, got {status}")
    if len(payload) != 1:
        raise VerifyError(f"installer CTA: expected one Range byte, got {len(payload)}")
    content_range = headers.get("content-range", "")
    if not content_range.startswith("bytes 0-0/") or not content_range.endswith(f"/{size}"):
        raise VerifyError(f"installer CTA: unexpected Content-Range {content_range!r}; expected total {size}")


def main() -> int:
    try:
        home, home_headers = get_html("/", ("/download", "data-outpost-open-question", PHONE_HREF))
        verify_email(home, home_headers, "/")

        download, download_headers = get_html(
            "/download",
            ("/support", "/license", TELEGRAM, PHONE_HREF),
        )
        verify_email(download, download_headers, "/download")

        license_page, license_headers = get_html(
            "/license",
            ("/download", "/support", PHONE_HREF),
        )
        verify_email(license_page, license_headers, "/license")

        support, support_headers = get_html(
            "/support",
            ("/download", TELEGRAM, PHONE_HREF),
        )
        verify_email(support, support_headers, "/support")

        verify_installer_range()
    except Exception as exc:
        print(f"Live public CTA verification: FAIL\n  - {exc}", file=sys.stderr)
        return 1

    print("Live public CTA verification: PASS")
    print("  /, /download, /license and /support return usable public CTA markers")
    print("  official email survives either as mailto or valid Cloudflare email protection")
    print("  Telegram and phone support routes are visible where expected")
    print("  current installer responds to a one-byte HTTP 206 Range request")
    print("  no protected cabinet/service endpoint was called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
