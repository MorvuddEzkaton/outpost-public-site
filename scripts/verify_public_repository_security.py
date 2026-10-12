"""Fail-closed public-source boundary checks; no network or production access."""
from pathlib import Path
import hashlib
import json
import re
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'.gitignore', '.gitattributes', '.gitleaks.toml', 'README.md', 'SECURITY.md', 'NOTICE.md', 'wrangler.jsonc'}
SCHEMAS = {'analytics/0001_installer_download_daily.sql', 'analytics/0002_telegram_update_subscribers.sql', 'cms/0001_cms.sql', 'cms/0002_cms_v02.sql'}
BAD_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.pfx', '.p12', '.jks', '.key', '.pem', '.bak', '.zip', '.7z', '.tgz', '.log', '.map'}
PATTERNS = {
    'GitHub credential': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{60,})\b'),
    'Telegram credential': re.compile(rb'\b\d{7,12}:[A-Za-z0-9_-]{30,}\b'),
    'private key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----'),
    'AWS credential': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'credential URL': re.compile(rb'https?://[^\s/@<>]{2,}:[^\s/@<>]{4,}@'),
}
IGNORED = {'.git', 'node_modules', '__pycache__', 'test-results', 'playwright-report', 'browser-ui-artifacts', 'browser-runtime-artifacts', 'browser-keyboard-artifacts'}

def path_errors(relative: str) -> list[str]:
    p = Path(relative)
    errors = []
    if relative not in ROOT_FILES and not relative.startswith(('site/', 'scripts/', 'release/', '.github/', 'docs/')) and relative not in SCHEMAS:
        errors.append('outside public source allowlist')
    if p.name.startswith('.env') or p.name in {'.dev.vars', 'default.toml'} or p.suffix.lower() in BAD_SUFFIXES:
        errors.append('private/runtime/archive file is forbidden')
    if any(part.lower() in {'private', 'backups', 'backup', '.wrangler', 'artifacts', 'diagnostics'} for part in p.parts):
        errors.append('private evidence/runtime directory is forbidden')
    return errors

def content_errors(payload: bytes) -> list[str]:
    return [category for category, pattern in PATTERNS.items() if pattern.search(payload)]

def workflow_errors(payload: bytes) -> list[str]:
    text = payload.decode('utf-8')
    errors = []
    if re.search(r'^  pull_request_target:', text, re.MULTILINE):
        errors.append('privileged pull_request_target event forbidden')
    for action in re.findall(r'uses:\s*([^\s#]+)', text):
        if not re.fullmatch(r'actions/[A-Za-z0-9_-]+@[0-9a-f]{40}', action):
            errors.append('action must use an audited official full commit SHA')
    return errors

def installer_errors(relative: str, payload: bytes, root: Path) -> list[str]:
    errors = []
    # Preserve the existing historical two-component artifact; new release tools
    # still require X.Y.Z. This exception never skips PE/size/checksum checks.
    legacy = relative == 'site/downloads/OutPOSt-Setup-v0.24.exe'
    if not legacy and not re.fullmatch(r'site/downloads/OutPOSt-(?:Accounting-)?Setup-v\d+\.\d+\.\d+\.exe', relative):
        errors.append('unexpected executable')
    if len(payload) > 25 * 1024 * 1024:
        errors.append('installer exceeds Pages 25 MiB asset limit')
    if not payload.startswith(b'MZ'):
        errors.append('installer is not a PE executable')
    checksum = root / relative.replace('.exe', '.sha256.txt')
    if not checksum.is_file():
        errors.append('installer checksum is missing')
    else:
        expected = hashlib.sha256(payload).hexdigest().upper()
        actual = checksum.read_text(encoding='utf-8-sig').strip().split()
        if len(actual) != 2 or actual[0].upper() != expected or actual[1].lstrip('*') != Path(relative).name:
            errors.append('installer checksum/name mismatch')
    return errors

def image_errors(file: Path, reviewed: dict | None) -> list[str]:
    errors = []
    try:
        with Image.open(file) as image:
            image.load()
            if image.getexif():
                errors.append('unreviewed EXIF metadata')
    except (OSError, ValueError):
        return ['image cannot be decoded']
    if 'screenshots' in file.parts:
        if not reviewed or reviewed.get('status') != 'reviewed-public-demo':
            errors.append('screenshot needs explicit public-demo review')
        elif reviewed.get('sha256') != hashlib.sha256(file.read_bytes()).hexdigest():
            errors.append('screenshot differs from reviewed bytes')
    return errors

def verify(root: Path = ROOT) -> list[str]:
    errors = []
    manifest_path = root / 'release/public-screenshot-review.json'
    reviews = {}
    if manifest_path.is_file():
        try:
            rows = json.loads(manifest_path.read_text(encoding='utf-8'))['images']
            reviews = {row['file']: row for row in rows}
            if len(reviews) != len(rows):
                errors.append('duplicate screenshot review entries')
        except (ValueError, KeyError, TypeError):
            errors.append('screenshot review manifest is invalid')
    else:
        errors.append('screenshot review manifest missing')
    for file in sorted(root.rglob('*')):
        if any(part in IGNORED for part in file.relative_to(root).parts):
            continue
        if file.is_symlink():
            errors.append(f'{file.relative_to(root).as_posix()}: symlink forbidden')
            continue
        if not file.is_file():
            continue
        relative = file.relative_to(root).as_posix()
        payload = file.read_bytes()
        reasons = path_errors(relative) + content_errors(payload)
        if relative.startswith('.github/workflows/'):
            reasons += workflow_errors(payload)
        if file.suffix.lower() == '.exe':
            reasons += installer_errors(relative, payload, root)
        if file.suffix.lower() in {'.png', '.webp', '.jpg', '.jpeg', '.ico'}:
            reasons += image_errors(file, reviews.get(relative))
        errors.extend(f'{relative}: {reason}' for reason in reasons)
    return errors

if __name__ == '__main__':
    failures = verify()
    if failures:
        print('Public repository security: FAIL')
        for failure in failures:
            print('- ' + failure)
        sys.exit(1)
    print('Public repository security: PASS; source allowlist, forbidden files, credentials, installer integrity, image decoding and reviewed screenshot bytes')
