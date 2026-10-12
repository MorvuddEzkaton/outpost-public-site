#!/usr/bin/env python3
"""Guard the currently published OutPOSt Accounting pre-release artifact, page and navigation."""

from __future__ import annotations

from pathlib import Path
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from release_integrity import IntegrityError, verify_registry

from accounting_release_meta import (
    authenticode_phrase,
    load_accounting_release,
    rc_card_label,
    rc_sentence,
    spaced_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DOWNLOADS = SITE / "downloads"
PAGE = SITE / "buhgalteriya.html"
DOWNLOAD_PAGE = SITE / "download.html"
SITEMAP = SITE / "sitemap.xml"
ORIGIN = "https://outpost.com.ua"
SCRIPT = SITE / "script.js"
SCRIPT_SRC = "/script.js?v=20260908-accounting-nav1"
RELEASE = load_accounting_release()
VERSION = RELEASE.version
INSTALLER = RELEASE.installer
CHECKSUM = RELEASE.checksum
EXPECTED_SIZE = RELEASE.size_bytes
EXPECTED_SHA256 = RELEASE.sha256
CHECKSUM_RE = re.compile(r"^([0-9A-Fa-f]{64})\s+\*?(.+)$")
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def stable_outpost_version(download_text: str, errors: list[str]) -> str | None:
    match = STABLE_PANEL_RE.search(download_text)
    if not match:
        errors.append("site/download.html: cannot determine stable OutPOSt version from stable download panel")
        return None
    return match.group(1)


def sitemap_pages(errors: list[str]) -> list[tuple[str, Path]]:
    try:
        root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError) as exc:
        errors.append(f"site/sitemap.xml: cannot parse sitemap for Accounting navigation guard: {exc}")
        return []

    rows: list[tuple[str, Path]] = []
    for node in root:
        loc = next(
            (child.text.strip() for child in node if child.tag.rsplit("}", 1)[-1] == "loc" and child.text),
            None,
        )
        if not loc or not loc.startswith(ORIGIN):
            continue
        pathname = loc[len(ORIGIN):] or "/"
        target = SITE / ("index.html" if pathname == "/" else pathname.strip("/") + ".html")
        rows.append((pathname, target))

    if not rows:
        errors.append("Accounting navigation guard: sitemap contains no OutPOSt public pages")
        return []

    pathnames = [pathname for pathname, _ in rows]
    if len(pathnames) != len(set(pathnames)):
        errors.append("Accounting navigation guard: sitemap contains duplicate public paths")
    return rows


def guard_primary_accounting_navigation(errors: list[str]) -> int:
    pages = sitemap_pages(errors)

    checked = 0
    for pathname, target in pages:
        if not target.is_file():
            errors.append(f"{pathname}: missing static HTML target {target.relative_to(ROOT)}")
            continue
        page_text = target.read_text(encoding="utf-8")
        if f'src="{SCRIPT_SRC}"' not in page_text:
            errors.append(f"{pathname}: primary page does not load cache-busted Accounting-safe shared runtime {SCRIPT_SRC}")
        nav_match = NAV_RE.search(page_text)
        if not nav_match:
            errors.append(f"{pathname}: primary site-nav not found")
            continue
        nav = nav_match.group(0)
        accounting = list(ACCOUNTING_NAV_RE.finditer(nav))
        prro = list(PRIMARY_PRRO_RE.finditer(nav))
        if len(accounting) != 1:
            errors.append(f"{pathname}: expected exactly one primary Бухгалтерія link, got {len(accounting)}")
            continue
        if len(prro) != 1:
            errors.append(f"{pathname}: expected exactly one primary ПРРО link, got {len(prro)}")
            continue
        if accounting[0].start() <= prro[0].start():
            errors.append(f"{pathname}: Бухгалтерія must appear after primary ПРРО")
        more_pos = nav.find('class="nav-more')
        if more_pos >= 0 and accounting[0].start() > more_pos:
            errors.append(f"{pathname}: Бухгалтерія is hidden inside/after Ще instead of primary navigation")
        has_current = bool(CURRENT_ACCOUNTING_NAV_RE.search(nav))
        if has_current != (pathname == "/buhgalteriya"):
            errors.append(f"{pathname}: Бухгалтерія aria-current='page' state is incorrect")
        checked += 1
    return checked


def guard_accounting_runtime(errors: list[str]) -> None:
    if not SCRIPT.is_file():
        errors.append("missing site/script.js for Accounting runtime navigation guard")
        return
    text = SCRIPT.read_text(encoding="utf-8")
    required = (
        'const nestedLinks = Array.from(nav.querySelectorAll(`.nav-more a[href="${href}"]`));',
        'nestedLinks.forEach((link) => link.remove());',
        'primaryPrro.insertAdjacentElement("afterend", directLink);',
        'directLink.removeAttribute("aria-current");',
    )
    for marker in required:
        if marker not in text:
            errors.append(f"site/script.js: missing Accounting primary-nav runtime marker {marker!r}")
    if 'if (directLink) directLink.remove();' in text:
        errors.append("site/script.js: forbidden legacy runtime still removes primary Бухгалтерія link")


def main() -> int:
    errors: list[str] = []
    installer_path = DOWNLOADS / INSTALLER
    checksum_path = DOWNLOADS / CHECKSUM

    accounting_installers = sorted(path.name for path in DOWNLOADS.glob("OutPOSt-Accounting-Setup-v*.exe"))
    accounting_checksums = sorted(path.name for path in DOWNLOADS.glob("OutPOSt-Accounting-Setup-v*.sha256.txt"))
    # Keep historical release URLs for existing users and rollback, but only
    # the manifest-designated installer can be marketed as current.
    try:
        registry = verify_registry(ROOT)
    except (IntegrityError, OSError) as exc:
        errors.append(str(exc))
        registry = []
    accounting_rows = [row for row in registry if row["product"] == "accounting"]
    expected_exes = sorted(row["installer"] for row in accounting_rows)
    expected_sums = sorted(row["checksum"] for row in accounting_rows)
    if INSTALLER not in expected_exes:
        errors.append("current Accounting installer must be registered immutably")
    if accounting_installers != expected_exes:
        errors.append(f"unexpected Accounting installer set; expected {expected_exes!r}, got {accounting_installers!r}")
    if accounting_checksums != expected_sums:
        errors.append(f"unexpected Accounting checksum set; expected {expected_sums!r}, got {accounting_checksums!r}")

    if installer_path.is_file():
        if installer_path.stat().st_size != EXPECTED_SIZE:
            errors.append(
                f"{INSTALLER}: size mismatch; expected {EXPECTED_SIZE}, got {installer_path.stat().st_size}"
            )
        actual_hash = sha256(installer_path)
        if actual_hash != EXPECTED_SHA256:
            errors.append(f"{INSTALLER}: SHA-256 mismatch; expected {EXPECTED_SHA256}, got {actual_hash}")
    else:
        errors.append(f"missing site/downloads/{INSTALLER}")

    if checksum_path.is_file():
        raw = checksum_path.read_text(encoding="utf-8").strip()
        match = CHECKSUM_RE.fullmatch(raw)
        if not match:
            errors.append(f"{CHECKSUM}: invalid checksum format")
        else:
            if match.group(1).upper() != EXPECTED_SHA256:
                errors.append(f"{CHECKSUM}: published SHA-256 does not match manifest")
            if match.group(2).strip() != INSTALLER:
                errors.append(f"{CHECKSUM}: filename does not match {INSTALLER}")
    else:
        errors.append(f"missing site/downloads/{CHECKSUM}")

    required_release_markers = (
        f'href="/downloads/{INSTALLER}"',
        f'href="/downloads/{CHECKSUM}"',
        f"v{VERSION}",
        EXPECTED_SHA256,
        rc_sentence(RELEASE.windows_rc_acceptance),
        "без окремої ліцензії",
        authenticode_phrase(RELEASE.authenticode_signed),
    )
    if not PAGE.is_file():
        errors.append("missing site/buhgalteriya.html")
    else:
        text = PAGE.read_text(encoding="utf-8")
        for marker in required_release_markers:
            if marker not in text:
                errors.append(f"site/buhgalteriya.html: missing Accounting manifest marker {marker!r}")

    if not DOWNLOAD_PAGE.is_file():
        errors.append("missing site/download.html")
    else:
        download_text = DOWNLOAD_PAGE.read_text(encoding="utf-8")
        stable_version = stable_outpost_version(download_text, errors)
        download_markers = [
            'data-download-split-hero',
            'data-download-product="outpost"',
            'data-download-product="accounting"',
            f'href="/downloads/{INSTALLER}"',
            f'href="/downloads/{CHECKSUM}"',
            f"Завантажити <em>Бухгалтерію v{VERSION}</em>",
            f"Завантажити Setup · {RELEASE.display_size_mb} МБ",
            f"{spaced_bytes(EXPECTED_SIZE)} байт",
            rc_card_label(RELEASE.windows_rc_acceptance),
            rc_sentence(RELEASE.windows_rc_acceptance),
            authenticode_phrase(RELEASE.authenticode_signed),
            'href="/buhgalteriya"',
            'src="/assets/outpost-accounting-icon.png"',
        ]
        if stable_version:
            download_markers.append(f"не замінює основний OutPOSt v{stable_version}")
        for marker in download_markers:
            if marker not in download_text:
                errors.append(f"site/download.html: missing Accounting manifest marker {marker!r}")

    guard_accounting_runtime(errors)
    nav_checked = guard_primary_accounting_navigation(errors)

    if errors:
        print(f"Accounting release guard: FAIL ({len(errors)} issue(s))")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("Accounting release guard: PASS")
    print(f"  canonical manifest: release/accounting-release.json -> v{VERSION}")
    print(f"  installer: {INSTALLER} ({EXPECTED_SIZE} bytes)")
    print(f"  SHA-256: {EXPECTED_SHA256}")
    print("  /buhgalteriya and /download expose manifest-aligned release facts and caveats")
    print(f"  Бухгалтерія is primary navigation on all {nav_checked} sitemap pages")
    print("  sitemap page count is derived dynamically from the validated source sitemap")
    print("  shared runtime preserves/promotes primary Бухгалтерія and removes legacy nested duplicates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
