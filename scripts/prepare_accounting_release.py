#!/usr/bin/env python3
"""Prepare a future OutPOSt Accounting pre-release safely.

Safety model:
- dry-run by default;
- the target Accounting EXE must already exist in site/downloads;
- SHA-256, byte size and checksum file are generated from the EXE;
- only the Accounting release manifest, /buhgalteriya, the Accounting half of /download,
  /buhgalteriya sitemap lastmod, and Accounting installer/checksum artifacts are changed;
- the stable OutPOSt installer/release metadata are never rewritten;
- the previous Accounting installer/checksum are removed only with --apply;
- no Worker, Cabinet, Director, Sync, D1 or Cloudflare runtime file is touched.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys

from accounting_release_meta import (
    AccountingRelease,
    AccountingReleaseError,
    MANIFEST,
    authenticode_phrase,
    decimal_mb_comma,
    load_accounting_release,
    manifest_dict,
    rc_card_label,
    rc_sentence,
    spaced_bytes,
    version_key,
)

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DOWNLOADS = SITE / "downloads"
PAGE = SITE / "buhgalteriya.html"
DOWNLOAD_PAGE = SITE / "download.html"
SITEMAP = SITE / "sitemap.xml"
ACCOUNTING_PANEL_RE = re.compile(
    r'(<section\b(?=[^>]*\bdata-download-product="accounting")[^>]*>)(.*?)(</section>)',
    re.DOTALL,
)
CHECKSUM_RE = re.compile(r"^([A-Fa-f0-9]{64})\s+\*?([^\s]+)\s*$")
SITEMAP_ACCOUNTING_RE = re.compile(
    r'(<loc>https://outpost\.com\.ua/buhgalteriya</loc>\s*<lastmod>)(\d{4}-\d{2}-\d{2})(</lastmod>)'
)


class PrepareError(AccountingReleaseError):
    pass


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def checksum_text(release: AccountingRelease) -> str:
    return f"{release.sha256} *{release.installer}\n"


def verify_artifact(release: AccountingRelease, *, require_checksum: bool = True) -> None:
    installer = DOWNLOADS / release.installer
    checksum = DOWNLOADS / release.checksum
    if not installer.is_file():
        raise PrepareError(f"missing Accounting installer: site/downloads/{release.installer}")
    actual_size = installer.stat().st_size
    if actual_size != release.size_bytes:
        raise PrepareError(
            f"Accounting installer size mismatch for {release.installer}: manifest={release.size_bytes}, actual={actual_size}"
        )
    actual_sha = sha256(installer)
    if actual_sha != release.sha256:
        raise PrepareError(
            f"Accounting installer SHA-256 mismatch for {release.installer}: manifest={release.sha256}, actual={actual_sha}"
        )
    if not require_checksum:
        return
    if not checksum.is_file():
        raise PrepareError(f"missing Accounting checksum: site/downloads/{release.checksum}")
    match = CHECKSUM_RE.fullmatch(read(checksum).strip())
    if not match:
        raise PrepareError(f"invalid Accounting checksum format: site/downloads/{release.checksum}")
    if match.group(1).upper() != release.sha256 or match.group(2) != release.installer:
        raise PrepareError(f"Accounting checksum does not match manifest: site/downloads/{release.checksum}")


def build_target(current: AccountingRelease, version: str, rc: str, signed: bool) -> AccountingRelease:
    if version_key(version) <= version_key(current.version):
        raise PrepareError(f"target Accounting v{version} must be newer than current v{current.version}")
    installer_name = f"OutPOSt-Accounting-Setup-v{version}.exe"
    installer = DOWNLOADS / installer_name
    if not installer.is_file():
        raise PrepareError(f"target Accounting installer is missing: site/downloads/{installer_name}")
    size = installer.stat().st_size
    digest = sha256(installer)
    return AccountingRelease(
        version=version,
        status="Pre-release",
        installer=installer_name,
        checksum=f"OutPOSt-Accounting-Setup-v{version}.sha256.txt",
        size_bytes=size,
        sha256=digest,
        display_size_mb=decimal_mb_comma(size),
        platform=current.platform,
        runtime=current.runtime,
        architecture=current.architecture,
        windows_rc_acceptance=rc,
        authenticode_signed=signed,
        published_date=date.today().isoformat(),
    )


def replace_release_facts(text: str, current: AccountingRelease, target: AccountingRelease) -> str:
    replacements = [
        (current.installer, target.installer),
        (current.checksum, target.checksum),
        (current.sha256, target.sha256),
        (f"v{current.version}", f"v{target.version}"),
        (f"{current.display_size_mb} МБ", f"{target.display_size_mb} МБ"),
        (f"{spaced_bytes(current.size_bytes)} байт", f"{spaced_bytes(target.size_bytes)} байт"),
        (f"{spaced_bytes(current.size_bytes)} байти", f"{spaced_bytes(target.size_bytes)} байти"),
        (rc_sentence(current.windows_rc_acceptance), rc_sentence(target.windows_rc_acceptance)),
        (rc_card_label(current.windows_rc_acceptance), rc_card_label(target.windows_rc_acceptance)),
        (authenticode_phrase(current.authenticode_signed), authenticode_phrase(target.authenticode_signed)),
    ]
    result = text
    for old, new in replacements:
        if old != new:
            result = result.replace(old, new)

    old_short = "RC PASS" if current.windows_rc_acceptance == "PASS" else "RC не підтверджено"
    new_short = "RC PASS" if target.windows_rc_acceptance == "PASS" else "RC не підтверджено"
    result = result.replace(old_short, new_short)

    old_narrative = (
        "Windows RC acceptance пройдено"
        if current.windows_rc_acceptance == "PASS"
        else "Windows RC acceptance ще не підтверджено"
    )
    new_narrative = (
        "Windows RC acceptance пройдено"
        if target.windows_rc_acceptance == "PASS"
        else "Windows RC acceptance ще не підтверджено"
    )
    result = result.replace(old_narrative, new_narrative)
    return result


def transform_pages(current: AccountingRelease, target: AccountingRelease) -> tuple[str, str, str]:
    if not PAGE.is_file() or not DOWNLOAD_PAGE.is_file() or not SITEMAP.is_file():
        raise PrepareError("Accounting release pages or sitemap are missing")

    page_original = read(PAGE)
    page_new = replace_release_facts(page_original, current, target)
    if page_new == page_original:
        raise PrepareError("/buhgalteriya transformation produced no changes")

    download_original = read(DOWNLOAD_PAGE)
    panel_match = ACCOUNTING_PANEL_RE.search(download_original)
    if not panel_match:
        raise PrepareError("/download Accounting product panel was not found")
    panel_old = panel_match.group(0)
    panel_new = replace_release_facts(panel_old, current, target)
    if panel_new == panel_old:
        raise PrepareError("/download Accounting panel transformation produced no changes")
    download_new = download_original[: panel_match.start()] + panel_new + download_original[panel_match.end() :]

    # Stable OutPOSt half of /download must remain byte-for-byte identical.
    stable_before = download_original.split('data-download-product="accounting"', 1)[0]
    stable_after = download_new.split('data-download-product="accounting"', 1)[0]
    if stable_before != stable_after:
        raise PrepareError("Accounting updater changed the stable OutPOSt half of /download")

    sitemap_original = read(SITEMAP)
    matches = list(SITEMAP_ACCOUNTING_RE.finditer(sitemap_original))
    if len(matches) != 1:
        raise PrepareError(f"expected exactly one /buhgalteriya sitemap lastmod, got {len(matches)}")
    sitemap_new = SITEMAP_ACCOUNTING_RE.sub(
        lambda match: f"{match.group(1)}{target.published_date}{match.group(3)}",
        sitemap_original,
        count=1,
    )

    required_page = (
        f"v{target.version}",
        target.installer,
        target.checksum,
        target.sha256,
        rc_sentence(target.windows_rc_acceptance),
        authenticode_phrase(target.authenticode_signed),
    )
    for marker in required_page:
        if marker not in page_new:
            raise PrepareError(f"transformed /buhgalteriya is missing target marker {marker!r}")

    required_panel = (
        f"Бухгалтерію v{target.version}",
        target.installer,
        target.checksum,
        f"Setup · {target.display_size_mb} МБ",
        f"{spaced_bytes(target.size_bytes)} байт",
        rc_card_label(target.windows_rc_acceptance),
        rc_sentence(target.windows_rc_acceptance),
        authenticode_phrase(target.authenticode_signed),
    )
    for marker in required_panel:
        if marker not in panel_new:
            raise PrepareError(f"transformed /download Accounting panel is missing target marker {marker!r}")

    forbidden_old = (current.installer, current.checksum, current.sha256, f"v{current.version}")
    for marker in forbidden_old:
        if marker in page_new:
            raise PrepareError(f"old current Accounting marker remains on /buhgalteriya: {marker}")
        if marker in panel_new:
            raise PrepareError(f"old current Accounting marker remains in /download Accounting panel: {marker}")

    return page_new, download_new, sitemap_new


def check_current() -> int:
    current = load_accounting_release()
    verify_artifact(current)
    page = read(PAGE)
    download = read(DOWNLOAD_PAGE)
    for marker in (current.installer, current.checksum, f"v{current.version}", current.sha256):
        if marker not in page:
            raise PrepareError(f"/buhgalteriya is missing current Accounting marker {marker!r}")
    panel_match = ACCOUNTING_PANEL_RE.search(download)
    if not panel_match:
        raise PrepareError("/download Accounting panel was not found")
    panel = panel_match.group(0)
    for marker in (
        current.installer,
        current.checksum,
        f"Бухгалтерію v{current.version}",
        f"Setup · {current.display_size_mb} МБ",
        f"{spaced_bytes(current.size_bytes)} байт",
    ):
        if marker not in panel:
            raise PrepareError(f"/download Accounting panel is missing current marker {marker!r}")
    print("Accounting release tooling: CURRENT PASS")
    print(f"  current pre-release: v{current.version}")
    print(f"  installer: {current.installer} ({current.size_bytes} bytes)")
    print(f"  SHA-256: {current.sha256}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare an OutPOSt Accounting pre-release PR safely")
    parser.add_argument("version", nargs="?", help="target Accounting version, for example 0.403 or 0.403.1")
    parser.add_argument("--apply", action="store_true", help="write generated Accounting release changes")
    parser.add_argument("--keep-previous", action="store_true", help="retain the previous installer and checksum for rollback")
    parser.add_argument("--check-current", action="store_true", help="validate the current Accounting manifest/artifact/pages")
    parser.add_argument(
        "--rc-acceptance",
        choices=("PASS", "NOT_VERIFIED"),
        default="PASS",
        help="Windows RC acceptance state for the target Accounting pre-release",
    )
    parser.add_argument(
        "--authenticode",
        choices=("signed", "unsigned"),
        default="unsigned",
        help="whether the target Accounting installer has an Authenticode signature",
    )
    args = parser.parse_args()

    try:
        if args.check_current:
            if args.version or args.apply:
                raise PrepareError("--check-current cannot be combined with target version or --apply")
            return check_current()
        if not args.version:
            parser.error("target version is required unless --check-current is used")

        current = load_accounting_release()
        verify_artifact(current)
        target = build_target(current, args.version, args.rc_acceptance, args.authenticode == "signed")
        target_checksum_path = DOWNLOADS / target.checksum
        expected_checksum = checksum_text(target)
        if target_checksum_path.exists() and read(target_checksum_path) != expected_checksum:
            raise PrepareError(f"pre-existing target checksum does not match target EXE: {target.checksum}")

        page_new, download_new, sitemap_new = transform_pages(current, target)
        manifest_text = json.dumps(manifest_dict(target), ensure_ascii=False, indent=2) + "\n"

        print("Accounting release preparation: PLAN PASS")
        print(f"  current: v{current.version}")
        print(f"  target: v{target.version}")
        print(f"  installer: {target.installer} ({target.size_bytes} bytes)")
        print(f"  SHA-256: {target.sha256}")
        print(f"  RC: {target.windows_rc_acceptance}; Authenticode: {'signed' if target.authenticode_signed else 'unsigned'}")
        print(f"  /buhgalteriya sitemap lastmod: {target.published_date}")
        print(f"  {'retain' if args.keep_previous else 'remove'} previous artifacts: {current.installer}, {current.checksum}")

        if not args.apply:
            print("  dry-run only; rerun with --apply after reviewing the plan")
            return 0

        PAGE.write_text(page_new, encoding="utf-8", newline="\n")
        DOWNLOAD_PAGE.write_text(download_new, encoding="utf-8", newline="\n")
        SITEMAP.write_text(sitemap_new, encoding="utf-8", newline="\n")
        MANIFEST.write_text(manifest_text, encoding="utf-8", newline="\n")
        target_checksum_path.write_text(expected_checksum, encoding="utf-8", newline="\n")

        old_installer = DOWNLOADS / current.installer
        old_checksum = DOWNLOADS / current.checksum
        if not args.keep_previous and old_installer != DOWNLOADS / target.installer:
            old_installer.unlink()
        if not args.keep_previous and old_checksum != target_checksum_path:
            old_checksum.unlink()

        print("Accounting release preparation: APPLIED")
        print("  stable OutPOSt installer/changelog/release metadata were not modified")
        print("  run the full site smoke gate before opening or merging any PR")
        return 0
    except (AccountingReleaseError, OSError) as exc:
        print(f"Accounting release preparation: FAIL\n  - {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
