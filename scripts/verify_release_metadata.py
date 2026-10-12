#!/usr/bin/env python3
"""Verify that public release metadata points to one current OutPOSt installer.

The current release is inferred from site/download.html rather than hardcoded, so a
future release can update the site and installer together. The guard is read-only.
"""

from __future__ import annotations

from html.parser import HTMLParser
import hashlib
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DOWNLOAD_PAGE = SITE / "download.html"
CHANGELOG_PAGE = SITE / "changelog.html"
DOWNLOADS = SITE / "downloads"

VERSION_RE = r"\d+\.\d+\.\d+"
INSTALLER_NAME_RE = re.compile(rf"OutPOSt-Setup-v({VERSION_RE})\.exe")
SOFTWARE_VERSION_RE = re.compile(r'"softwareVersion"\s*:\s*"([^"]+)"')
SOFTWARE_SIZE_RE = re.compile(
    r'"softwareVersion"\s*:\s*"([^"]+)".{0,1200}?"fileSize"\s*:\s*"([^"]+)"',
    re.DOTALL,
)
DOWNLOAD_URL_RE = re.compile(
    rf'"downloadUrl"\s*:\s*"https://outpost\.com\.ua/downloads/OutPOSt-Setup-v({VERSION_RE})\.exe"'
)
VISIBLE_VERSION_RE = re.compile(rf"\bv({VERSION_RE})\b", re.IGNORECASE)
CURRENT_LABEL_RE = re.compile(rf"актуальна\s+версія\s+v({VERSION_RE})", re.IGNORECASE)
DOWNLOAD_CTA_VERSION_RE = re.compile(rf"Завантажити\s+OutPOSt\s+v({VERSION_RE})", re.IGNORECASE)
DEMO_VERSION_RE = re.compile(rf'class=["\']app-version["\'][^>]*>\s*v({VERSION_RE})\s*·\s*demo', re.IGNORECASE)
ABSOLUTE_PRODUCTION_ANCHOR_RE = re.compile(
    r'<a\b[^>]*\bhref=["\']https?://(?:www\.)?outpost\.com\.ua(?:/[^"\']*)?["\'][^>]*>',
    re.IGNORECASE,
)
HASH_RE = re.compile(r"\b[A-Fa-f0-9]{64}\b")
CHECKSUM_RE = re.compile(r"^([A-Fa-f0-9]{64})\s+\*?([^\s]+)\s*$")
BYTE_FACT_RE = re.compile(r"<dt>Інсталятор</dt>\s*<dd>([0-9\s\u00a0]+)\s*байти</dd>", re.IGNORECASE)
HOMEPAGE_HASH_RE = re.compile(
    r'<code[^>]*id=["\']setup-hash["\'][^>]*>\s*([A-Fa-f0-9]{64})\s*</code>',
    re.IGNORECASE,
)
CHANGELOG_VERSION_RE = r"\d+\.\d+(?:\.\d+){0,2}"
CHANGELOG_RELEASE_HEADING_RE = re.compile(
    rf"<h2\b[^>]*>\s*v({CHANGELOG_VERSION_RE})\b",
    re.IGNORECASE,
)
CHANGELOG_DECLARED_COUNT_RE = re.compile(
    r"<span>\s*(\d+)\s+основних\s+змін\s*</span>",
    re.IGNORECASE,
)
CHANGELOG_NOTES_LIST_RE = re.compile(
    r'<ul\b[^>]*class=["\'][^"\']*\brelease-notes-list\b[^"\']*["\'][^>]*>([\s\S]*?)</ul>',
    re.IGNORECASE,
)
CHANGELOG_LIST_ITEM_RE = re.compile(r"<li\b", re.IGNORECASE)


class VisibleTextParser(HTMLParser):
    """Collect user-visible text while ignoring script/style/template payloads."""

    SKIP_TAGS = {"script", "style", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data)

    def text(self) -> str:
        return " ".join(self._chunks)


def visible_release_versions(html: str) -> set[str]:
    parser = VisibleTextParser()
    parser.feed(html)
    parser.close()
    return set(VISIBLE_VERSION_RE.findall(parser.text()))


def validate_changelog_change_counts(html: str) -> list[str]:
    errors: list[str] = []
    headings = list(CHANGELOG_RELEASE_HEADING_RE.finditer(html))

    for index, heading in enumerate(headings):
        version = heading.group(1)
        segment_end = headings[index + 1].start() if index + 1 < len(headings) else len(html)
        segment = html[heading.end():segment_end]
        declarations = CHANGELOG_DECLARED_COUNT_RE.findall(segment)
        if not declarations:
            continue

        if len(declarations) != 1:
            errors.append(
                f"site/changelog.html: v{version} must declare exactly one 'основних змін' count; "
                f"got {declarations!r}"
            )
            continue

        lists = CHANGELOG_NOTES_LIST_RE.findall(segment)
        if len(lists) != 1:
            errors.append(
                f"site/changelog.html: v{version} declares a change count but must contain exactly one "
                f"release-notes-list; found {len(lists)}"
            )
            continue

        declared = int(declarations[0])
        actual = len(CHANGELOG_LIST_ITEM_RE.findall(lists[0]))
        if declared != actual:
            errors.append(
                f"site/changelog.html: v{version} declares {declared} основних змін but has {actual} release-note items"
            )

    return errors


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    errors: list[str] = []

    if not DOWNLOAD_PAGE.is_file():
        print("OutPOSt release metadata guard: FAIL")
        print("  - missing site/download.html")
        return 1

    download_html = read(DOWNLOAD_PAGE)
    if not CHANGELOG_PAGE.is_file():
        errors.append("site/changelog.html: changelog is missing")
    else:
        errors.extend(validate_changelog_change_counts(read(CHANGELOG_PAGE)))
    referenced_versions = set(INSTALLER_NAME_RE.findall(download_html))
    if len(referenced_versions) != 1:
        errors.append(
            f"site/download.html must reference exactly one installer version; got {sorted(referenced_versions)!r}"
        )
        current_version = None
    else:
        current_version = next(iter(referenced_versions))

    if current_version is not None:
        exe_name = f"OutPOSt-Setup-v{current_version}.exe"
        sha_name = f"OutPOSt-Setup-v{current_version}.sha256.txt"
        exe_path = DOWNLOADS / exe_name
        sha_path = DOWNLOADS / sha_name
        homepage_path = SITE / "index.html"
        homepage_html = read(homepage_path) if homepage_path.is_file() else None

        if not exe_path.is_file():
            errors.append(f"current installer is missing: site/downloads/{exe_name}")
        if not sha_path.is_file():
            errors.append(f"current checksum file is missing: site/downloads/{sha_name}")
        if homepage_html is None:
            errors.append("site/index.html: homepage is missing")
        else:
            visible_versions = visible_release_versions(homepage_html)
            stale_visible_versions = sorted(version for version in visible_versions if version != current_version)
            if stale_visible_versions:
                errors.append(
                    "site/index.html: visible release version(s) "
                    f"{stale_visible_versions!r} differ from current {current_version!r}"
                )

        expected_hash = None
        if sha_path.is_file():
            checksum_text = read(sha_path).strip()
            match = CHECKSUM_RE.match(checksum_text)
            if not match:
                errors.append(f"site/downloads/{sha_name}: invalid checksum format")
            else:
                expected_hash = match.group(1).upper()
                checksum_filename = match.group(2)
                if checksum_filename != exe_name:
                    errors.append(
                        f"site/downloads/{sha_name}: checksum filename {checksum_filename!r} does not match {exe_name!r}"
                    )

        if expected_hash is not None:
            if exe_path.is_file():
                actual_hash = sha256_file(exe_path)
                if actual_hash != expected_hash:
                    errors.append(
                        f"site/downloads/{exe_name}: actual SHA-256 {actual_hash} differs from checksum file {expected_hash}"
                    )

            page_hashes = {value.upper() for value in HASH_RE.findall(download_html)}
            if expected_hash not in page_hashes:
                errors.append("site/download.html: displayed SHA-256 does not match current checksum file")

            if homepage_html is not None:
                homepage_hashes = HOMEPAGE_HASH_RE.findall(homepage_html)
                if len(homepage_hashes) != 1:
                    errors.append(
                        f"site/index.html: expected exactly one #setup-hash value, got {len(homepage_hashes)}"
                    )
                elif homepage_hashes[0].upper() != expected_hash:
                    errors.append(
                        "site/index.html: displayed #setup-hash does not match current checksum file"
                    )

        expected_structured_size = None
        if exe_path.is_file():
            size_match = BYTE_FACT_RE.search(download_html)
            if not size_match:
                errors.append("site/download.html: installer byte-size fact is missing")
            else:
                stated_size = int(re.sub(r"\s+", "", size_match.group(1)))
                actual_size = exe_path.stat().st_size
                if stated_size != actual_size:
                    errors.append(
                        f"site/download.html: stated installer size {stated_size} differs from actual {actual_size}"
                    )
                expected_structured_size = f"{actual_size / 1_000_000:.1f} MB"

        if current_version not in SOFTWARE_VERSION_RE.findall(download_html):
            errors.append(
                f"site/download.html: SoftwareApplication softwareVersion must be {current_version!r}"
            )

        expected_absolute_url = f"https://outpost.com.ua/downloads/{exe_name}"
        if current_version not in DOWNLOAD_URL_RE.findall(download_html):
            errors.append(
                f"site/download.html: structured downloadUrl is missing for current release: {expected_absolute_url}"
            )

        if expected_structured_size is not None:
            current_structured_sizes = [
                file_size
                for version, file_size in SOFTWARE_SIZE_RE.findall(download_html)
                if version == current_version
            ]
            if not current_structured_sizes:
                errors.append(
                    f"site/download.html: structured fileSize is missing for current release {current_version!r}"
                )

        for html_path in sorted(SITE.glob("*.html")):
            text = read(html_path)

            visible_current_versions = set(CURRENT_LABEL_RE.findall(text))
            visible_download_versions = set(DOWNLOAD_CTA_VERSION_RE.findall(text))
            # The optional noindex web demo is versioned independently from the stable desktop release.
            demo_versions = set() if html_path.name == "demo.html" else set(DEMO_VERSION_RE.findall(text))
            absolute_production_anchors = ABSOLUTE_PRODUCTION_ANCHOR_RE.findall(text)
            if absolute_production_anchors:
                errors.append(
                    f"site/{html_path.name}: visible internal anchors must be relative for staging preview safety; "
                    f"found production anchor(s) {absolute_production_anchors!r}"
                )

            for label, versions in (
                ("current-version label", visible_current_versions),
                ("download CTA", visible_download_versions),
                ("demo app-version", demo_versions),
            ):
                stale = sorted(version for version in versions if version != current_version)
                if stale:
                    errors.append(
                        f"site/{html_path.name}: visible {label} version(s) {stale!r} differ from current {current_version!r}"
                    )

            for version in SOFTWARE_VERSION_RE.findall(text):
                if version != current_version:
                    errors.append(
                        f"site/{html_path.name}: structured softwareVersion {version!r} differs from current {current_version!r}"
                    )
            for version in DOWNLOAD_URL_RE.findall(text):
                if version != current_version:
                    errors.append(
                        f"site/{html_path.name}: structured downloadUrl version {version!r} differs from current {current_version!r}"
                    )
            if expected_structured_size is not None:
                for version, file_size in SOFTWARE_SIZE_RE.findall(text):
                    if version == current_version and file_size != expected_structured_size:
                        errors.append(
                            f"site/{html_path.name}: structured fileSize {file_size!r} differs from current installer {expected_structured_size!r}"
                        )

        if homepage_html is not None:
            relative_homepage_href = f'href="/downloads/{exe_name}"'
            if relative_homepage_href not in homepage_html:
                errors.append("site/index.html: relative current installer link is missing")

    unique_errors = list(dict.fromkeys(errors))
    if unique_errors:
        print(f"OutPOSt release metadata guard: FAIL ({len(unique_errors)} issue(s))")
        for item in unique_errors:
            print(f"  - {item}")
        return 1

    print("OutPOSt release metadata guard: PASS")
    print(f"  current public release: v{current_version}")
    print("  installer bytes match checksum SHA-256 and stated byte size")
    print("  download page checksum and displayed hash are consistent")
    print("  homepage #setup-hash matches the current checksum file")
    print("  visible homepage release-version labels do not contain stale versions")
    print("  visible current-version footers, OutPOSt download CTAs and demo version labels are globally aligned")
    print("  structured softwareVersion/downloadUrl/fileSize references match the current release")
    print("  all visible internal outpost.com.ua anchors are relative and preview-safe across public HTML")
    print("  changelog declared change counts match release-note item counts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
