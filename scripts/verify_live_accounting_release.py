#!/usr/bin/env python3
"""Read-only post-deploy checks for the published OutPOSt Accounting pre-release and navigation."""

from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import re
import sys
import time
import xml.etree.ElementTree as ET

from accounting_release_meta import (
    authenticode_phrase,
    load_accounting_release,
    rc_card_label,
    rc_sentence,
    spaced_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
SITEMAP = ROOT / "site" / "sitemap.xml"
LOCAL_DOWNLOAD = ROOT / "site" / "download.html"
ORIGIN = "https://outpost.com.ua"
SCRIPT_SRC = "/script.js?v=20260908-accounting-nav1"
USER_AGENT = "OutPOSt-Accounting-Live-Verify/1.1"
RELEASE = load_accounting_release()
VERSION = RELEASE.version
INSTALLER = RELEASE.installer
CHECKSUM = RELEASE.checksum
EXPECTED_SIZE = RELEASE.size_bytes
EXPECTED_SHA256 = RELEASE.sha256
ATTEMPTS = 6
DELAY_SECONDS = 5
NAV_RE = re.compile(r'<nav\b(?=[^>]*\bclass="[^"]*\bsite-nav\b[^"]*")[^>]*>.*?</nav>', re.DOTALL)
ACCOUNTING_NAV_RE = re.compile(r'<a\b(?=[^>]*\bhref="/buhgalteriya")[^>]*>\s*Бухгалтерія\s*</a>')
CURRENT_ACCOUNTING_NAV_RE = re.compile(
    r'<a\b(?=[^>]*\bhref="/buhgalteriya")(?=[^>]*\baria-current="page")[^>]*>\s*Бухгалтерія\s*</a>'
)
PRIMARY_PRRO_RE = re.compile(r'<a\b(?=[^>]*\bhref="/prro")[^>]*>\s*ПРРО\s*</a>')
STABLE_PANEL_RE = re.compile(
    r'<section\b(?=[^>]*\bdata-download-product="outpost")[^>]*>.*?OutPOSt v([0-9]+(?:\.[0-9]+){2}).*?</section>',
    re.DOTALL,
)


class VerifyError(RuntimeError):
    pass


def stable_outpost_version() -> str:
    try:
        text = LOCAL_DOWNLOAD.read_text(encoding="utf-8")
    except OSError as exc:
        raise VerifyError(f"cannot read local /download source for stable release context: {exc}") from exc
    match = STABLE_PANEL_RE.search(text)
    if not match:
        raise VerifyError("cannot determine stable OutPOSt version from local /download panel")
    return match.group(1)


def request(path: str, *, range_request: bool = False, timeout: int = 30) -> tuple[int, dict[str, str], bytes]:
    suffix = "&" if "?" in path else "?"
    url = f"{ORIGIN}{path}{suffix}{urlencode({'accounting_verify': int(time.time() * 1000)})}"
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


def sitemap_paths() -> list[str]:
    try:
        root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        raise VerifyError(f"cannot parse local sitemap for live Accounting navigation check: {exc}") from exc
    paths: list[str] = []
    for node in root:
        loc = next(
            (child.text.strip() for child in node if child.tag.rsplit("}", 1)[-1] == "loc" and child.text),
            None,
        )
        if loc and loc.startswith(ORIGIN):
            paths.append(loc[len(ORIGIN):] or "/")
    if not paths:
        raise VerifyError("local sitemap contains no OutPOSt public paths for Accounting navigation check")
    if len(paths) != len(set(paths)):
        raise VerifyError("local sitemap contains duplicate public paths for Accounting navigation check")
    return paths


def verify_primary_accounting_navigation() -> int:
    checked = 0
    for pathname in sitemap_paths():
        status, _, payload = request(pathname, timeout=25)
        if status != 200:
            raise VerifyError(f"{pathname}: expected HTTP 200 for Accounting navigation check, got {status}")
        text = payload.decode("utf-8", errors="replace")
        if f'src="{SCRIPT_SRC}"' not in text:
            raise VerifyError(f"{pathname}: live page does not load cache-busted Accounting-safe runtime {SCRIPT_SRC}")
        nav_match = NAV_RE.search(text)
        if not nav_match:
            raise VerifyError(f"{pathname}: live primary site-nav not found")
        nav = nav_match.group(0)
        accounting = list(ACCOUNTING_NAV_RE.finditer(nav))
        prro = list(PRIMARY_PRRO_RE.finditer(nav))
        if len(accounting) != 1:
            raise VerifyError(f"{pathname}: expected exactly one live primary Бухгалтерія link, got {len(accounting)}")
        if len(prro) != 1:
            raise VerifyError(f"{pathname}: expected exactly one live primary ПРРО link, got {len(prro)}")
        if accounting[0].start() <= prro[0].start():
            raise VerifyError(f"{pathname}: live Бухгалтерія must appear after primary ПРРО")
        more_pos = nav.find('class="nav-more')
        if more_pos >= 0 and accounting[0].start() > more_pos:
            raise VerifyError(f"{pathname}: live Бухгалтерія is hidden inside/after Ще")
        has_current = bool(CURRENT_ACCOUNTING_NAV_RE.search(nav))
        if has_current != (pathname == "/buhgalteriya"):
            raise VerifyError(f"{pathname}: live Бухгалтерія aria-current='page' state is incorrect")
        checked += 1
    return checked


def verify_live_accounting_runtime() -> None:
    status, _, payload = request(SCRIPT_SRC, timeout=25)
    if status != 200:
        raise VerifyError(f"{SCRIPT_SRC}: expected HTTP 200, got {status}")
    text = payload.decode("utf-8", errors="replace")
    required = (
        'const nestedLinks = Array.from(nav.querySelectorAll(`.nav-more a[href="${href}"]`));',
        'nestedLinks.forEach((link) => link.remove());',
        'primaryPrro.insertAdjacentElement("afterend", directLink);',
        'directLink.removeAttribute("aria-current");',
    )
    for marker in required:
        if marker not in text:
            raise VerifyError(f"live script.js: missing Accounting primary-nav runtime marker {marker!r}")
    if 'if (directLink) directLink.remove();' in text:
        raise VerifyError("live script.js: forbidden legacy runtime still removes primary Бухгалтерія link")


def verify_once() -> int:
    verify_live_accounting_runtime()
    nav_checked = verify_primary_accounting_navigation()
    stable_version = stable_outpost_version()

    status, _, payload = request("/buhgalteriya", timeout=25)
    if status != 200:
        raise VerifyError(f"/buhgalteriya: expected HTTP 200, got {status}")
    text = payload.decode("utf-8", errors="replace")
    required = (
        f'href="/downloads/{INSTALLER}"',
        f'href="/downloads/{CHECKSUM}"',
        f"v{VERSION}",
        EXPECTED_SHA256,
        rc_sentence(RELEASE.windows_rc_acceptance),
        "без окремої ліцензії",
        authenticode_phrase(RELEASE.authenticode_signed),
    )
    for marker in required:
        if marker not in text:
            raise VerifyError(f"/buhgalteriya: missing live Accounting manifest marker {marker!r}")

    status, _, payload = request("/download", timeout=25)
    if status != 200:
        raise VerifyError(f"/download: expected HTTP 200, got {status}")
    download_text = payload.decode("utf-8", errors="replace")
    download_required = (
        'data-download-split-hero',
        'data-download-product="outpost"',
        'data-download-product="accounting"',
        f'href="/downloads/{INSTALLER}"',
        f'href="/downloads/{CHECKSUM}"',
        f"Завантажити <em>Бухгалтерію v{VERSION}</em>",
        f"Завантажити Setup · {RELEASE.display_size_mb} МБ",
        f"{spaced_bytes(EXPECTED_SIZE)} байт",
        f"не замінює основний OutPOSt v{stable_version}",
        rc_card_label(RELEASE.windows_rc_acceptance),
        rc_sentence(RELEASE.windows_rc_acceptance),
        authenticode_phrase(RELEASE.authenticode_signed),
        'href="/buhgalteriya"',
        'src="/assets/outpost-accounting-icon.png"',
    )
    for marker in download_required:
        if marker not in download_text:
            raise VerifyError(f"/download: missing live Accounting manifest marker {marker!r}")

    status, headers, payload = request(f"/downloads/{INSTALLER}", range_request=True, timeout=40)
    if status != 206:
        raise VerifyError(f"Accounting installer: one-byte Range request must return 206, got {status}")
    if len(payload) != 1:
        raise VerifyError(f"Accounting installer: expected one Range byte, got {len(payload)}")
    content_range = headers.get("content-range", "")
    if content_range != f"bytes 0-0/{EXPECTED_SIZE}":
        raise VerifyError(
            f"Accounting installer: unexpected Content-Range {content_range!r}; expected bytes 0-0/{EXPECTED_SIZE}"
        )

    status, headers, payload = request(f"/downloads/{CHECKSUM}", timeout=20)
    if status != 200:
        raise VerifyError(f"Accounting checksum: expected HTTP 200, got {status}")
    content_type = headers.get("content-type", "").lower()
    if "text/" not in content_type and "octet-stream" not in content_type:
        raise VerifyError(f"Accounting checksum: unexpected Content-Type {content_type!r}")
    checksum_text = payload.decode("utf-8", errors="replace").strip()
    expected_text = f"{EXPECTED_SHA256} *{INSTALLER}"
    if checksum_text != expected_text:
        raise VerifyError(f"Accounting checksum body mismatch; expected {expected_text!r}, got {checksum_text!r}")

    return nav_checked


def main() -> int:
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            nav_checked = verify_once()
            print("Live Accounting release verification: PASS")
            print(f"  manifest-driven Accounting release: v{VERSION}")
            print(f"  {INSTALLER}: one-byte HTTP 206 Range confirms {EXPECTED_SIZE} bytes")
            print(f"  {CHECKSUM}: exact SHA-256/name match")
            print(f"  Бухгалтерія is primary navigation on all {nav_checked} live sitemap pages")
            print("  sitemap page count is derived dynamically from the validated local sitemap")
            print("  deployed shared runtime preserves/promotes primary Бухгалтерія after JavaScript executes")
            print("  no Cabinet, Director, Sync, D1, PRRO or other protected endpoint was called")
            return 0
        except Exception as exc:
            last_error = exc
            if attempt < ATTEMPTS:
                print(f"Live Accounting release verification attempt {attempt}/{ATTEMPTS} failed: {exc}; retrying...")
                time.sleep(DELAY_SECONDS)

    print(f"Live Accounting release verification: FAIL\n  - {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
