#!/usr/bin/env python3
"""Synthetic regression test for future OutPOSt public release preparation.

The test builds an isolated temporary mini-repository, copies only the reusable
release scripts into it, creates fake current/next installers and metadata, and
runs the real dry-run/apply code. The real repository and production are never
modified or called.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from release_test_fixtures import fixture_row, synthetic_pe, write_synthetic_receipt

ROOT = Path(__file__).resolve().parents[1]
CURRENT = "1.2.3"
TARGET = "1.2.4"
PUBLIC_ORIGIN = "https://outpost.com.ua"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build_fixture(root: Path, *, bad_target_checksum: bool = False, bad_changelog: bool = False) -> dict[str, str]:
    scripts = root / "scripts"
    site = root / "site"
    downloads = site / "downloads"
    scripts.mkdir(parents=True)
    downloads.mkdir(parents=True)

    shutil.copy2(ROOT / "scripts" / "prepare_public_release.py", scripts / "prepare_public_release.py")
    shutil.copy2(ROOT / "scripts" / "release_sitemap.py", scripts / "release_sitemap.py")
    shutil.copy2(ROOT / "scripts" / "verify_release_metadata.py", scripts / "verify_release_metadata.py")
    shutil.copy2(ROOT / "scripts" / "release_integrity.py", scripts / "release_integrity.py")

    current_bytes = synthetic_pe(4096)
    target_bytes = synthetic_pe(1_234_567)
    current_sha = digest(current_bytes)
    target_sha = digest(target_bytes)

    current_exe = f"OutPOSt-Setup-v{CURRENT}.exe"
    target_exe = f"OutPOSt-Setup-v{TARGET}.exe"
    current_sum = f"OutPOSt-Setup-v{CURRENT}.sha256.txt"
    target_sum = f"OutPOSt-Setup-v{TARGET}.sha256.txt"

    (downloads / current_exe).write_bytes(current_bytes)
    (downloads / target_exe).write_bytes(target_bytes)
    write(downloads / current_sum, f"{current_sha} *{current_exe}\n")
    published_target_sha = "0" * 64 if bad_target_checksum else target_sha
    write(downloads / target_sum, f"{published_target_sha} *{target_exe}\n")
    write(root / "release/artifact-registry.json", json.dumps({"schema_version": 1, "artifacts": [fixture_row(downloads / current_exe, "outpost", CURRENT)]}))
    write_synthetic_receipt(root, downloads / target_exe, "outpost", TARGET)

    write(
        site / "download.html",
        f'''<!doctype html>
<html><body>
<script type="application/ld+json">{{"softwareVersion":"{CURRENT}","fileSize":"0.0 MB","downloadUrl":"{PUBLIC_ORIGIN}/downloads/{current_exe}"}}</script>
<section data-download-product="outpost">
<h1>OutPOSt v{CURRENT}</h1>
<a href="/downloads/{current_exe}">Setup</a>
<a href="/downloads/{current_sum}">SHA-256</a>
<code>{current_sha}</code>
<dl><div><dt>Інсталятор</dt><dd>{len(current_bytes)} байти</dd></div></dl>
<span>Інсталятор 0,0 МБ</span><span>Setup · 0,0 МБ</span>
</section>
<section data-download-product="accounting">
<h2>Завантажити Бухгалтерію v0.402.3</h2>
<a href="/downloads/OutPOSt-Accounting-Setup-v0.402.3.exe">Завантажити Setup · 4,4 МБ</a>
<dl><div><dt>Інсталятор</dt><dd>4 371 102 байт</dd></div></dl>
</section>
</body></html>
''',
    )
    write(
        site / "index.html",
        f'''<!doctype html>
<html><body>
<div class="version-pill">v{CURRENT}</div><h2>OutPOSt v{CURRENT}</h2>
<div aria-label="Поточна версія OutPOSt" class="version-card"><span>OutPOSt</span><strong>v{CURRENT}</strong><small>Windows 10/11</small></div>
<a href="/downloads/{current_exe}">Завантажити</a>
<a href="/downloads/{current_sum}">Контрольна сума</a>
<code id="setup-hash">{current_sha}</code>
<footer><span>Windows 10/11<br/>актуальна версія v{CURRENT}</span></footer>
</body></html>
''',
    )
    write(
        site / "mini-t400.html",
        f'''<!doctype html><html><body><a href="/downloads/{current_exe}">Завантажити OutPOSt v{CURRENT}</a></body></html>\n''',
    )
    write(
        site / "prro-checkbox.html",
        f'''<!doctype html><html><body><a href="/downloads/{current_exe}">Завантажити v{CURRENT}</a></body></html>\n''',
    )

    write(
        site / "seo-page.html",
        f'''<!doctype html><html><body>
<script type="application/ld+json">{{"@type":"SoftwareApplication","softwareVersion":"{CURRENT}","fileSize":"0.0 MB","downloadUrl":"{PUBLIC_ORIGIN}/downloads/{current_exe}"}}</script>
<section><a class="btn btn-primary" href="/download">Завантажити OutPOSt v{CURRENT}</a></section>
</body></html>\n''',
    )

    write(
        site / "demo.html",
        f'''<!doctype html><html><body>
<span class="app-version">v{CURRENT} · demo</span>
<span class="app-version">v{CURRENT} · demo</span>
<span class="app-version">v{CURRENT} · demo</span>
<p>OutPOSt v{CURRENT}</p>
</body></html>\n''',
    )

    marker_version = CURRENT if bad_changelog else TARGET
    seo_description = f"Повна історія версій OutPOSt: реліз v{CURRENT}; Бухгалтерія v1.0.2."
    seo_jsonld = json.dumps({
        "@graph": [{
            "@type": "WebPage",
            "@id": f"{PUBLIC_ORIGIN}/changelog#webpage",
            "description": seo_description,
        }]
    }, ensure_ascii=False)
    write(
        site / "changelog.html",
        f'''<!doctype html>
<html><head>
<meta content="{seo_description}" name="description"/>
<meta content="{seo_description}" property="og:description"/>
<script type="application/ld+json">{seo_jsonld}</script>
</head><body>
<div class="changelog-version"><span>Поточний реліз</span><strong>{marker_version}</strong></div>
<a href="/download">Завантажити v{marker_version}</a>
<div class="changelog-version"><span>Попередній реліз</span><strong>{CURRENT}</strong></div>
</body></html>
''',
    )

    write(
        site / "sitemap.xml",
        f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{PUBLIC_ORIGIN}/</loc><lastmod>2026-01-01</lastmod></url>
  <url><loc>{PUBLIC_ORIGIN}/download</loc><lastmod>2026-01-01</lastmod></url>
  <url><loc>{PUBLIC_ORIGIN}/changelog</loc><lastmod>2026-01-01</lastmod></url>
  <url><loc>{PUBLIC_ORIGIN}/mini-t400</loc><lastmod>2026-01-01</lastmod></url>
  <url><loc>{PUBLIC_ORIGIN}/prro-checkbox</loc><lastmod>2026-01-01</lastmod></url>
</urlset>
''',
    )

    write(site / "_worker.js", "// protected worker sentinel\n")
    write(site / "_telegram-support.js", "// protected telegram worker sentinel\n")
    write(site / "_telegram-faq.js", "// protected telegram faq sentinel\n")
    write(site / "_headers", "/\n  X-Frame-Options: DENY\n")
    write(root / "wrangler.jsonc", '{"name":"fixture-protected"}\n')

    return {
        "current_sha": current_sha,
        "target_sha": target_sha,
        "current_exe": current_exe,
        "target_exe": target_exe,
        "current_sum": current_sum,
        "target_sum": target_sum,
        "target_bytes": str(len(target_bytes)),
    }


def run_release(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/prepare_public_release.py", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )


def run_metadata_guard(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/verify_release_metadata.py"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )


def snapshot_public_payload(root: Path) -> dict[str, bytes]:
    paths = [path for path in (root / "site").rglob("*") if path.is_file()]
    paths.append(root / "wrangler.jsonc")
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(paths)}


def sitemap_lastmods(path: Path) -> dict[str, str]:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    values: dict[str, str] = {}
    for url_node in root:
        loc = None
        lastmod = None
        for child in url_node:
            name = child.tag.rsplit("}", 1)[-1]
            if name == "loc" and child.text:
                loc = child.text.strip()
            elif name == "lastmod" and child.text:
                lastmod = child.text.strip()
        if loc and lastmod:
            values[loc] = lastmod
    return values


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_success_path() -> None:
    with tempfile.TemporaryDirectory(prefix="outpost-release-regression-") as tmp:
        root = Path(tmp)
        fixture = build_fixture(root)
        before = snapshot_public_payload(root)

        dry = run_release(root, TARGET)
        require(dry.returncode == 0, f"dry-run failed:\n{dry.stdout}\n{dry.stderr}")
        require("PLAN PASS" in dry.stdout, "dry-run did not report PLAN PASS")
        require("dry-run only" in dry.stdout, "dry-run did not state read-only mode")
        require(snapshot_public_payload(root) == before, "dry-run modified the fixture payload")

        applied = run_release(root, TARGET, "--apply")
        require(applied.returncode == 0, f"apply failed:\n{applied.stdout}\n{applied.stderr}")
        require("APPLIED" in applied.stdout, "apply did not report APPLIED")

        changelog_after_apply = (root / "site" / "changelog.html").read_text(encoding="utf-8")
        changelog_head = changelog_after_apply.split("</head>", 1)[0]
        require(
            changelog_head.count(f"реліз v{TARGET}") == 3,
            "standard release preparation did not advance all three changelog SEO descriptions",
        )
        require(
            f"реліз v{CURRENT}" not in changelog_head,
            "changelog SEO still describes the previous public release",
        )

        metadata = run_metadata_guard(root)
        require(
            metadata.returncode == 0 and "OutPOSt release metadata guard: PASS" in metadata.stdout,
            f"post-apply metadata guard failed:\n{metadata.stdout}\n{metadata.stderr}",
        )

        download = (root / "site" / "download.html").read_text(encoding="utf-8")
        index = (root / "site" / "index.html").read_text(encoding="utf-8")
        mini = (root / "site" / "mini-t400.html").read_text(encoding="utf-8")
        prro = (root / "site" / "prro-checkbox.html").read_text(encoding="utf-8")
        demo = (root / "site" / "demo.html").read_text(encoding="utf-8")
        seo = (root / "site" / "seo-page.html").read_text(encoding="utf-8")

        formatted_target_bytes = f"{int(fixture['target_bytes']):,}".replace(",", " ")

        for marker in (
            TARGET,
            fixture["target_exe"],
            fixture["target_sum"],
            fixture["target_sha"],
            formatted_target_bytes,
        ):
            require(marker in download, f"transformed download page misses {marker!r}")

        require(
            f"<dd>{formatted_target_bytes} байти</dd>" in download,
            "OutPOSt installer byte-size lost the separator before the unit",
        )

        for accounting_marker in (
            "Завантажити Бухгалтерію v0.402.3",
            "/downloads/OutPOSt-Accounting-Setup-v0.402.3.exe",
            "Завантажити Setup · 4,4 МБ",
            "<dd>4 371 102 байт</dd>",
        ):
            require(
                download.count(accounting_marker) == 1,
                f"OutPOSt release preparation changed Accounting marker {accounting_marker!r}",
            )

        for name, text in (("download", download), ("index", index), ("mini", mini), ("prro", prro), ("demo", demo), ("seo", seo)):
            require(fixture["current_exe"] not in text, f"{name} retains old installer name")
            require(fixture["current_sum"] not in text, f"{name} retains old checksum name")
            require(fixture["current_sha"] not in text, f"{name} retains old SHA-256")
            require(CURRENT not in text, f"{name} retains ambiguous previous current version")

        require(
            f'"softwareVersion":"{TARGET}"' in download,
            "minified primary download structured softwareVersion did not advance",
        )
        require(
            f'"downloadUrl":"{PUBLIC_ORIGIN}/downloads/{fixture["target_exe"]}"' in download,
            "minified primary download structured downloadUrl did not advance",
        )
        require(
            f'<div aria-label="Поточна версія OutPOSt" class="version-card"><span>OutPOSt</span><strong>v{TARGET}</strong>' in index,
            "homepage current-version card did not advance",
        )
        require(f"актуальна версія v{TARGET}" in index, "shared footer current-version marker did not advance")
        require(demo.count(f"v{TARGET} · demo") == 3, "demo app-version markers did not all advance")
        require(f"OutPOSt v{TARGET}" in demo, "demo About/version marker did not advance")
        require(
            f"Завантажити OutPOSt v{TARGET}" in seo,
            "SEO current-release download CTA did not advance",
        )
        target_size = int(fixture["target_bytes"])
        expected_mb = f"{target_size / 1_000_000:.1f} MB"
        require(
            f'"softwareVersion":"{TARGET}"' in seo,
            "minified SEO structured softwareVersion did not advance",
        )
        require(
            f'"fileSize":"{expected_mb}"' in seo,
            "minified SEO structured fileSize did not advance",
        )
        require(
            f'"downloadUrl":"{PUBLIC_ORIGIN}/downloads/{fixture["target_exe"]}"' in seo,
            "minified SEO structured downloadUrl did not advance",
        )

        release_date = datetime.now(ZoneInfo("Europe/Kyiv")).date().isoformat()
        lastmods = sitemap_lastmods(root / "site" / "sitemap.xml")
        for url in (
            f"{PUBLIC_ORIGIN}/",
            f"{PUBLIC_ORIGIN}/download",
            f"{PUBLIC_ORIGIN}/changelog",
            f"{PUBLIC_ORIGIN}/mini-t400",
            f"{PUBLIC_ORIGIN}/prro-checkbox",
        ):
            require(lastmods.get(url) == release_date, f"sitemap lastmod not updated for {url}")

        protected = {
            "site/_worker.js": b"// protected worker sentinel\n",
            "site/_telegram-support.js": b"// protected telegram worker sentinel\n",
            "site/_telegram-faq.js": b"// protected telegram faq sentinel\n",
            "site/_headers": b"/\n  X-Frame-Options: DENY\n",
            "wrangler.jsonc": b'{"name":"fixture-protected"}\n',
        }
        for relative, expected in protected.items():
            require((root / relative).read_bytes() == expected, f"protected fixture changed: {relative}")

        current_check = run_release(root, "--check-current")
        require(
            current_check.returncode == 0 and "CURRENT PASS" in current_check.stdout,
            f"post-apply current check failed:\n{current_check.stdout}\n{current_check.stderr}",
        )


def test_stale_visible_homepage_version_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="outpost-release-stale-visible-") as tmp:
        root = Path(tmp)
        build_fixture(root)
        baseline = run_metadata_guard(root)
        require(
            baseline.returncode == 0,
            f"baseline metadata guard failed:\n{baseline.stdout}\n{baseline.stderr}",
        )
        index_path = root / "site" / "index.html"
        index = index_path.read_text(encoding="utf-8")
        require("</body>" in index, "fixture homepage is missing </body>")
        index_path.write_text(
            index.replace("</body>", "<p>Робочий екран v0.9.9</p></body>", 1),
            encoding="utf-8",
            newline="\n",
        )
        result = run_metadata_guard(root)
        require(result.returncode != 0, "stale visible homepage version unexpectedly passed")
        combined = result.stdout + result.stderr
        require(
            "visible release version(s)" in combined and "0.9.9" in combined,
            "stale visible homepage failure was not explicit",
        )


def test_stale_visible_non_homepage_version_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="outpost-release-stale-visible-secondary-") as tmp:
        root = Path(tmp)
        build_fixture(root)
        baseline = run_metadata_guard(root)
        require(
            baseline.returncode == 0,
            f"baseline metadata guard failed:\n{baseline.stdout}\n{baseline.stderr}",
        )
        page_path = root / "site" / "mini-t400.html"
        page = page_path.read_text(encoding="utf-8")
        page_path.write_text(
            page.replace(
                "</body>",
                "<footer><span>актуальна версія v0.9.9</span></footer></body>",
                1,
            ),
            encoding="utf-8",
            newline="\n",
        )
        result = run_metadata_guard(root)
        require(result.returncode != 0, "stale non-homepage current-version label unexpectedly passed")
        combined = result.stdout + result.stderr
        require(
            "visible current-version label version(s)" in combined and "0.9.9" in combined,
            "stale non-homepage current-version failure was not explicit",
        )


def test_absolute_preview_download_link_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="outpost-release-absolute-preview-link-") as tmp:
        root = Path(tmp)
        fixture = build_fixture(root)
        baseline = run_metadata_guard(root)
        require(
            baseline.returncode == 0,
            f"baseline metadata guard failed:\n{baseline.stdout}\n{baseline.stderr}",
        )
        page_path = root / "site" / "mini-t400.html"
        page = page_path.read_text(encoding="utf-8")
        page_path.write_text(
            page.replace(
                f'href="/downloads/{fixture["current_exe"]}"',
                f'href="{PUBLIC_ORIGIN}/downloads/{fixture["current_exe"]}"',
                1,
            ),
            encoding="utf-8",
            newline="\n",
        )
        result = run_metadata_guard(root)
        require(result.returncode != 0, "absolute production download link unexpectedly passed preview guard")
        combined = result.stdout + result.stderr
        require(
            "visible internal anchors must be relative for staging preview safety" in combined,
            "absolute production download-link failure was not explicit",
        )


def test_absolute_internal_preview_link_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="outpost-release-absolute-internal-link-") as tmp:
        root = Path(tmp)
        build_fixture(root)
        baseline = run_metadata_guard(root)
        require(
            baseline.returncode == 0,
            f"baseline metadata guard failed:\n{baseline.stdout}\n{baseline.stderr}",
        )
        page_path = root / "site" / "mini-t400.html"
        page = page_path.read_text(encoding="utf-8")
        page_path.write_text(
            page.replace(
                "</body>",
                '<a href="https://outpost.com.ua/features">Можливості</a></body>',
                1,
            ),
            encoding="utf-8",
            newline="\n",
        )
        result = run_metadata_guard(root)
        require(result.returncode != 0, "absolute production internal link unexpectedly passed preview guard")
        combined = result.stdout + result.stderr
        require(
            "visible internal anchors must be relative for staging preview safety" in combined,
            "absolute internal production-link failure was not explicit",
        )


def test_missing_structured_download_url_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="outpost-release-missing-structured-url-") as tmp:
        root = Path(tmp)
        fixture = build_fixture(root)
        baseline = run_metadata_guard(root)
        require(
            baseline.returncode == 0,
            f"baseline metadata guard failed:\n{baseline.stdout}\n{baseline.stderr}",
        )
        page_path = root / "site" / "download.html"
        page = page_path.read_text(encoding="utf-8")
        needle = f'"downloadUrl":"{PUBLIC_ORIGIN}/downloads/{fixture["current_exe"]}"'
        require(needle in page, "fixture structured downloadUrl is missing")
        page_path.write_text(
            page.replace('"downloadUrl":', '"landingUrl":', 1),
            encoding="utf-8",
            newline="\n",
        )
        result = run_metadata_guard(root)
        require(result.returncode != 0, "missing structured downloadUrl unexpectedly passed")
        combined = result.stdout + result.stderr
        require(
            "structured downloadUrl is missing" in combined,
            "missing structured downloadUrl failure was not explicit",
        )


def test_missing_structured_file_size_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="outpost-release-missing-structured-size-") as tmp:
        root = Path(tmp)
        build_fixture(root)
        baseline = run_metadata_guard(root)
        require(
            baseline.returncode == 0,
            f"baseline metadata guard failed:\n{baseline.stdout}\n{baseline.stderr}",
        )
        page_path = root / "site" / "download.html"
        page = page_path.read_text(encoding="utf-8")
        require('"fileSize":"0.0 MB"' in page, "fixture structured fileSize is missing")
        page_path.write_text(
            page.replace('"fileSize":', '"displaySize":', 1),
            encoding="utf-8",
            newline="\n",
        )
        result = run_metadata_guard(root)
        require(result.returncode != 0, "missing structured fileSize unexpectedly passed")
        combined = result.stdout + result.stderr
        require(
            "structured fileSize is missing" in combined,
            "missing structured fileSize failure was not explicit",
        )


def test_tampered_current_installer_fails_metadata_guard() -> None:
    with tempfile.TemporaryDirectory(prefix="outpost-release-tampered-current-") as tmp:
        root = Path(tmp)
        fixture = build_fixture(root)
        baseline = run_metadata_guard(root)
        require(
            baseline.returncode == 0,
            f"baseline metadata guard failed:\n{baseline.stdout}\n{baseline.stderr}",
        )
        current_exe = root / "site" / "downloads" / fixture["current_exe"]
        current_exe.write_bytes(current_exe.read_bytes() + b"tampered\n")
        result = run_metadata_guard(root)
        require(result.returncode != 0, "tampered current installer unexpectedly passed metadata guard")
        combined = result.stdout + result.stderr
        require(
            "actual SHA-256" in combined and "differs from checksum file" in combined,
            "tampered installer failure did not explain binary SHA-256 mismatch",
        )


def test_bad_checksum_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="outpost-release-bad-sha-") as tmp:
        root = Path(tmp)
        build_fixture(root, bad_target_checksum=True)
        before = snapshot_public_payload(root)
        result = run_release(root, TARGET)
        require(result.returncode != 0, "bad target checksum unexpectedly passed")
        combined = result.stdout + result.stderr
        require("SHA-256 mismatch" in combined, "bad checksum failure did not explain SHA-256 mismatch")
        require(snapshot_public_payload(root) == before, "bad-checksum dry-run modified fixture payload")


def test_bad_changelog_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="outpost-release-bad-changelog-") as tmp:
        root = Path(tmp)
        build_fixture(root, bad_changelog=True)
        before = snapshot_public_payload(root)
        result = run_release(root, TARGET)
        require(result.returncode != 0, "stale changelog unexpectedly passed")
        combined = result.stdout + result.stderr
        require("changelog must contain exactly one current-release marker" in combined, "stale changelog failure was not explicit")
        require(snapshot_public_payload(root) == before, "bad-changelog dry-run modified fixture payload")


def test_missing_or_unverified_windows_receipt_blocks_apply() -> None:
    with tempfile.TemporaryDirectory(prefix="outpost-release-windows-evidence-") as tmp:
        root = Path(tmp)
        build_fixture(root)
        evidence = root / f"release/evidence/outpost-v{TARGET}.json"
        original = evidence.read_text(encoding="utf-8")
        for receipt in (None, dict(json.loads(original), windows_acceptance="NOT_VERIFIED"),
                        dict(json.loads(original), approved_for_publication=False),
                        dict(json.loads(original), product="accounting")):
            if receipt is None:
                evidence.unlink()
            else:
                evidence.write_text(json.dumps(receipt), encoding="utf-8")
            before = snapshot_public_payload(root)
            result = run_release(root, TARGET, "--apply")
            require(result.returncode != 0, "unverified Windows evidence unexpectedly allowed apply")
            require(snapshot_public_payload(root) == before, "rejected Windows evidence modified public pages/artifacts")


def main() -> int:
    try:
        test_success_path()
        test_stale_visible_homepage_version_fails_closed()
        test_stale_visible_non_homepage_version_fails_closed()
        test_absolute_preview_download_link_fails_closed()
        test_absolute_internal_preview_link_fails_closed()
        test_missing_structured_download_url_fails_closed()
        test_missing_structured_file_size_fails_closed()
        test_tampered_current_installer_fails_metadata_guard()
        test_bad_checksum_fails_closed()
        test_bad_changelog_fails_closed()
        test_missing_or_unverified_windows_receipt_blocks_apply()
    except AssertionError as exc:
        print("Public release tooling regression: FAIL", file=sys.stderr)
        print(f"  - {exc}", file=sys.stderr)
        return 1

    print("Public release tooling regression: PASS")
    print("  synthetic future release dry-run is read-only")
    print("  real apply path migrates version/installer/checksum/SHA/size metadata")
    print("  metadata guard rejects installer-byte tampering even when published checksum text is unchanged")
    print("  minified JSON-LD softwareVersion/fileSize/downloadUrl migration is covered")
    print("  missing structured downloadUrl/fileSize fields fail closed even when visible URL/size text remains")
    print("  release sitemap lastmod updates are exercised")
    print("  stale visible homepage and secondary-page release labels fail closed")
    print("  absolute production download and internal-navigation anchors fail closed so staging cannot silently jump to production")
    print("  protected Worker/Telegram/headers/Cloudflare sentinels stay byte-identical")
    print("  bad checksum and stale changelog fail closed without writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
