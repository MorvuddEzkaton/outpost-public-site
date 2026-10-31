#!/usr/bin/env python3
"""Prepare a future OutPOSt public-site release without one-off search/replace scripts.

Safety model:
- dry-run by default;
- installer + checksum must already exist and match byte-for-byte;
- changelog must already contain the target release as the current release;
- only current-release references outside changelog are rewritten;
- no Worker, Cloudflare/D1, cabinet, Director or Sync API files are touched;
- `--apply` is required to write files.

Examples:
    python scripts/prepare_public_release.py --check-current
    python scripts/prepare_public_release.py 0.24.3
    python scripts/prepare_public_release.py 0.24.3 --apply
"""

from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import re
import sys
import json

from release_integrity import IntegrityError, REGISTRY, append_target, load_receipt, verify_registry

from release_sitemap import SITEMAP, prepare_release_sitemap


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DOWNLOAD_PAGE = SITE / "download.html"
CHANGELOG = SITE / "changelog.html"
DOWNLOADS = SITE / "downloads"

VERSION_PATTERN = r"\d+\.\d+\.\d+"
INSTALLER_RE = re.compile(rf"OutPOSt-Setup-v({VERSION_PATTERN})\.exe")
CHECKSUM_RE = re.compile(r"^([A-Fa-f0-9]{64})\s+\*?([^\s]+)\s*$")
STRUCTURED_VERSION_RE = re.compile(r'("softwareVersion"\s*:\s*")([^\"]+)(")')
STRUCTURED_SIZE_RE = re.compile(r'("fileSize"\s*:\s*")([^\"]+)(")')
BYTE_FACT_RE = re.compile(
    r"(<dt>Інсталятор</dt>\s*<dd>)([0-9\s\u00a0]+)(\s*байти</dd>)",
    re.IGNORECASE,
)


class ReleaseError(RuntimeError):
    pass


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def version_tuple(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(VERSION_PATTERN, value):
        raise ReleaseError(f"invalid version {value!r}; expected X.Y.Z")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def current_version() -> str:
    if not DOWNLOAD_PAGE.is_file():
        raise ReleaseError("site/download.html is missing")
    versions = set(INSTALLER_RE.findall(read(DOWNLOAD_PAGE)))
    if len(versions) != 1:
        raise ReleaseError(f"download page must reference exactly one current installer version; got {sorted(versions)!r}")
    return next(iter(versions))


def artifact_info(version: str) -> tuple[str, str, Path, Path, int, str]:
    exe_name = f"OutPOSt-Setup-v{version}.exe"
    checksum_name = f"OutPOSt-Setup-v{version}.sha256.txt"
    exe_path = DOWNLOADS / exe_name
    checksum_path = DOWNLOADS / checksum_name

    if not exe_path.is_file():
        raise ReleaseError(f"target installer is missing: site/downloads/{exe_name}")
    if not checksum_path.is_file():
        raise ReleaseError(f"target checksum is missing: site/downloads/{checksum_name}")

    match = CHECKSUM_RE.fullmatch(read(checksum_path).strip())
    if not match:
        raise ReleaseError(f"invalid checksum format: site/downloads/{checksum_name}")

    expected_sha = match.group(1).upper()
    checksum_filename = match.group(2)
    if checksum_filename != exe_name:
        raise ReleaseError(
            f"checksum filename mismatch: expected {exe_name!r}, found {checksum_filename!r}"
        )

    actual_sha = sha256(exe_path)
    if actual_sha != expected_sha:
        raise ReleaseError(
            f"installer SHA-256 mismatch for {exe_name}: published {expected_sha}, actual {actual_sha}"
        )

    return exe_name, checksum_name, exe_path, checksum_path, exe_path.stat().st_size, expected_sha


def require_changelog_current(version: str) -> None:
    if not CHANGELOG.is_file():
        raise ReleaseError("site/changelog.html is missing")
    text = read(CHANGELOG)
    marker = f'<div class="changelog-version"><span>Поточний реліз</span><strong>{version}</strong></div>'
    if text.count(marker) != 1:
        raise ReleaseError(
            f"changelog must contain exactly one current-release marker for v{version}; update changelog before release preparation"
        )
    if f"Завантажити v{version}" not in text:
        raise ReleaseError(f"changelog hero CTA does not point to v{version}")


def decimal_mb(size: int) -> str:
    return f"{size / 1_000_000:.1f}"


def spaced_bytes(size: int) -> str:
    return f"{size:,}".replace(",", " ")


def prepare_html_changes(current: str, target: str, target_size: int, target_sha: str) -> dict[Path, str]:
    old_exe = f"OutPOSt-Setup-v{current}.exe"
    new_exe = f"OutPOSt-Setup-v{target}.exe"
    old_checksum = f"OutPOSt-Setup-v{current}.sha256.txt"
    new_checksum = f"OutPOSt-Setup-v{target}.sha256.txt"
    old_checksum_path = DOWNLOADS / old_checksum

    if not old_checksum_path.is_file():
        raise ReleaseError(f"current checksum file is missing: site/downloads/{old_checksum}")
    old_match = CHECKSUM_RE.fullmatch(read(old_checksum_path).strip())
    if not old_match:
        raise ReleaseError(f"current checksum has invalid format: site/downloads/{old_checksum}")
    current_sha = old_match.group(1).upper()

    target_mb_dot = f"{decimal_mb(target_size)} MB"
    target_mb_comma = f"{decimal_mb(target_size).replace('.', ',')} МБ"
    target_bytes = spaced_bytes(target_size)

    changes: dict[Path, str] = {}

    for path in sorted(SITE.glob("*.html")):
        if path == CHANGELOG:
            continue

        original = read(path)
        text = original

        # Installer/checksum references outside changelog are always current-release links.
        text = text.replace(old_exe, new_exe)
        text = text.replace(old_checksum, new_checksum)
        # Any visible copy of the current installer digest outside changelog is current-release metadata.
        text = text.replace(current_sha, target_sha)

        # Structured SoftwareApplication metadata is current-release metadata.
        text = STRUCTURED_VERSION_RE.sub(
            lambda match: f"{match.group(1)}{target}{match.group(3)}"
            if match.group(2) == current
            else match.group(0),
            text,
        )
        if re.search(rf'"softwareVersion"\s*:\s*"{re.escape(target)}"', text):
            text = STRUCTURED_SIZE_RE.sub(
                lambda match: f"{match.group(1)}{target_mb_dot}{match.group(3)}",
                text,
            )

        # Shared footer copy is current-release metadata on every public page.
        text = text.replace(
            f"актуальна версія v{current}",
            f"актуальна версія v{target}",
        )
        text = text.replace(
            f"Завантажити OutPOSt v{current}",
            f"Завантажити OutPOSt v{target}",
        )

        if path.name == "download.html":
            # The download page is exclusively about the current release.
            text = text.replace(current, target)
            text = text.replace(current_sha, target_sha)
            # The current installer size appears in exactly three SEO descriptions:
            # search meta, Open Graph and JSON-LD WebPage.description.
            # Scope substitutions to <head> to leave Accounting and body copy alone.
            head, separator, body = text.partition("</head>")
            if not separator:
                raise ReleaseError("download page must contain </head> for SEO size synchronization")
            head, seo_size_updates = re.subn(
                r"(Інсталятор\s+)[0-9]+(?:[,.][0-9]+)?\s*МБ",
                lambda match: f"{match.group(1)}{target_mb_comma}",
                head,
            )
            if seo_size_updates != 3:
                raise ReleaseError(
                    "download page must contain exactly three current installer-size SEO descriptions "
                    "(meta, Open Graph, JSON-LD)"
                )
            text = head + separator + body

            panel_match = re.search(
                r'<section\b[^>]*\bdata-download-product="outpost"[^>]*>.*?</section>',
                text,
                flags=re.DOTALL,
            )
            if not panel_match:
                raise ReleaseError('download page is missing data-download-product="outpost" panel')

            outpost_panel = panel_match.group(0)
            outpost_panel, byte_updates = BYTE_FACT_RE.subn(
                lambda match: f"{match.group(1)}{target_bytes} {match.group(3).lstrip()}",
                outpost_panel,
                count=1,
            )
            if byte_updates != 1:
                raise ReleaseError("OutPOSt download panel must contain exactly one installer byte-size marker")

            outpost_panel, setup_mb_updates = re.subn(
                r"(Setup\s*·\s*)[0-9]+(?:[,.][0-9]+)?\s*МБ",
                rf"\g<1>{target_mb_comma}",
                outpost_panel,
                count=1,
            )
            if setup_mb_updates != 1:
                raise ReleaseError("OutPOSt download panel must contain exactly one Setup size marker")

            text = text[:panel_match.start()] + outpost_panel + text[panel_match.end():]

        elif path.name == "index.html":
            text = text.replace(f'<div class="version-pill">v{current}</div>', f'<div class="version-pill">v{target}</div>')
            text = text.replace(f"<h2>OutPOSt v{current}</h2>", f"<h2>OutPOSt v{target}</h2>")
            text = text.replace(
                f'<div aria-label="Поточна версія OutPOSt" class="version-card"><span>OutPOSt</span><strong>v{current}</strong>',
                f'<div aria-label="Поточна версія OutPOSt" class="version-card"><span>OutPOSt</span><strong>v{target}</strong>',
            )

        elif path.name == "demo.html":
            text = text.replace(f"v{current} · demo", f"v{target} · demo")
            text = text.replace(f"OutPOSt v{current}", f"OutPOSt v{target}")

        elif path.name in {"mini-t400.html", "prro-checkbox.html"}:
            text = text.replace(f"Завантажити OutPOSt v{current}", f"Завантажити OutPOSt v{target}")
            text = text.replace(f"Завантажити v{current}", f"Завантажити v{target}")

        if text != original:
            changes[path] = text


    # Changelog release notes are prepared/reviewed separately. Only its three
    # SEO descriptions are current-release metadata and may be advanced here.
    # Historical release notes and the visible release body remain immutable.
    changelog_original = read(CHANGELOG)
    head_end = changelog_original.lower().find("</head>")
    if head_end < 0:
        raise ReleaseError("site/changelog.html is missing head; cannot synchronize release SEO metadata")
    head = changelog_original[:head_end]
    tail = changelog_original[head_end:]
    old_marker = f"реліз v{current}"
    new_marker = f"реліз v{target}"
    if head.count(old_marker) == 3:
        head = head.replace(old_marker, new_marker)
    elif head.count(old_marker) != 0 or head.count(new_marker) != 3:
        raise ReleaseError(
            "changelog requires three aligned search, social and structured SEO release descriptions"
        )
    if head.count(new_marker) != 3:
        raise ReleaseError("changelog release SEO descriptions were not updated exactly three times")
    changelog_updated = head + tail
    if changelog_updated != changelog_original:
        changes[CHANGELOG] = changelog_updated

    # Every old current-release reference outside changelog must be accounted for.
    leftovers: list[str] = []
    for path in sorted(SITE.glob("*.html")):
        if path == CHANGELOG:
            continue
        text = changes.get(path, read(path))
        for line_no, line in enumerate(text.splitlines(), 1):
            if current in line or old_exe in line or old_checksum in line or current_sha in line:
                leftovers.append(f"site/{path.name}:{line_no}: {line.strip()[:220]}")
    if leftovers:
        raise ReleaseError(
            "ambiguous references to the previous current release remain outside changelog:\n"
            + "\n".join(leftovers)
        )

    # Essential target markers must be present in the transformed download page.
    transformed_download = changes.get(DOWNLOAD_PAGE, read(DOWNLOAD_PAGE))
    required = (target, new_exe, new_checksum, target_sha, target_bytes)
    for marker in required:
        if marker not in transformed_download:
            raise ReleaseError(f"transformed download page is missing required target marker: {marker}")

    return changes


def check_current() -> int:
    current = current_version()
    exe_name, checksum_name, _, _, size, digest = artifact_info(current)
    verify_registry(ROOT)
    require_changelog_current(current)
    print("OutPOSt public release tooling: CURRENT PASS")
    print(f"  current release: v{current}")
    print(f"  installer: {exe_name}")
    print(f"  checksum: {checksum_name}")
    print(f"  bytes: {size}")
    print(f"  SHA-256: {digest}")
    print("  changelog current-release marker is aligned")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare OutPOSt public release metadata safely")
    parser.add_argument("version", nargs="?", help="target semantic version, for example 0.24.3")
    parser.add_argument("--apply", action="store_true", help="write the prepared HTML changes")
    parser.add_argument("--check-current", action="store_true", help="validate current release inputs without changing files")
    parser.add_argument("--evidence", type=Path, help="sanitized owner-reviewed Windows receipt; defaults to release/evidence/outpost-vVERSION.json")
    args = parser.parse_args()

    try:
        if args.check_current:
            if args.version or args.apply:
                raise ReleaseError("--check-current cannot be combined with a target version or --apply")
            return check_current()

        if not args.version:
            parser.error("target version is required unless --check-current is used")

        target = args.version
        current = current_version()
        version_tuple(target)
        version_tuple(current)

        if target == current:
            raise ReleaseError(
                f"target v{target} is already current; use --check-current to validate the current release"
            )
        if version_tuple(target) <= version_tuple(current):
            raise ReleaseError(f"target v{target} must be newer than current v{current}")

        exe_name, checksum_name, _, _, target_size, target_sha = artifact_info(target)
        receipt = load_receipt(ROOT, "outpost", target, args.evidence)
        rows = verify_registry(ROOT, allow_new={exe_name, checksum_name})
        # Hash original checksum bytes (including Windows CRLF), not universal-newline normalized text.
        registry_text = json.dumps(append_target(rows, receipt, (DOWNLOADS / checksum_name).read_bytes().decode("utf-8")), ensure_ascii=False, indent=2) + "\n"
        require_changelog_current(target)
        changes = prepare_html_changes(current, target, target_size, target_sha)
        try:
            sitemap_text, release_date, release_sitemap_urls = prepare_release_sitemap(changes.keys(), receipt["published_date"])
        except ValueError as exc:
            raise ReleaseError(str(exc)) from exc
        if sitemap_text != read(SITEMAP):
            changes[SITEMAP] = sitemap_text

        print("OutPOSt public release preparation: PLAN PASS")
        print(f"  current: v{current}")
        print(f"  target: v{target}")
        print(f"  installer: {exe_name}")
        print(f"  checksum: {checksum_name}")
        print(f"  bytes: {target_size}")
        print(f"  SHA-256: {target_sha}")
        print(f"  release sitemap lastmod: {release_date}")
        print(f"  release sitemap URLs: {len(release_sitemap_urls)}")
        print(f"  site files to update: {len(changes)}")
        for path in changes:
            print(f"    - {path.relative_to(ROOT)}")

        if not args.apply:
            print("  dry-run only; rerun with --apply after reviewing the plan")
            return 0

        for path, text in changes.items():
            path.write_text(text, encoding="utf-8", newline="\n")
        (ROOT / REGISTRY).write_text(registry_text, encoding="utf-8", newline="\n")
        evidence_path = ROOT / f"release/evidence/outpost-v{target}.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        if (ROOT/'site/setup/OutPOSt-Setup.exe').exists():
            # Reuse the reviewed stable executable; do not revert buttons to a
            # full versioned download when preparing the next product release.
            from desktop_bootstrap import render_universal_downloads
            render_universal_downloads(ROOT,target)

        print("OutPOSt public release preparation: APPLIED")
        print("  run the standard static CI/release guards before any merge to main")
        return 0

    except (ReleaseError, IntegrityError, OSError) as exc:
        print(f"OutPOSt public release preparation: FAIL\n  - {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
