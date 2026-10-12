"""Offline negative regressions; synthetic values never contact any service."""
from pathlib import Path
import hashlib
import tempfile
import unittest
from PIL import Image
from verify_public_repository_security import path_errors, content_errors, installer_errors, image_errors, workflow_errors

class PublicSecurityTests(unittest.TestCase):
    def test_mutable_action_ref_blocked(self):
        self.assertTrue(workflow_errors(b'uses: actions/checkout@v7'))

    def test_pinned_official_action_passes(self):
        self.assertEqual(workflow_errors(b'uses: actions/checkout@' + b'a' * 40), [])

    def test_privileged_pr_event_blocked(self):
        self.assertTrue(workflow_errors(b'on:\n  pull_request_target:\n'))

    def test_public_source_allowed(self):
        self.assertEqual(path_errors('site/index.html'), [])

    def test_database_is_blocked(self):
        self.assertTrue(path_errors('site/Accounting.db'))

    def test_private_evidence_blocked(self):
        self.assertTrue(path_errors('docs/private/baseline.json'))

    def test_env_blocked(self):
        self.assertTrue(path_errors('.env.production'))

    def test_seed_not_implicitly_allowed(self):
        self.assertTrue(path_errors('cms/seed-real-pages.sql'))

    def test_sql_cannot_hide_in_scripts_or_site(self):
        for name in ('scripts/customers.sql', 'site/database.sql', 'docs/private-export.sql'):
            self.assertIn('SQL outside the exact reviewed public schema allowlist is forbidden', path_errors(name))

    def test_desktop_source_and_dependencies_stay_private(self):
        for suffix in ('.cs', '.csproj', '.sln', '.dll', '.pdb'):
            self.assertTrue(path_errors('site/OutPOSt' + suffix))

    def test_github_token_blocked(self):
        token = b'gh' + b'p_' + b'A' * 36
        self.assertIn('GitHub credential', content_errors(token))

    def test_private_key_blocked(self):
        key = b'-----BEGIN ' + b'PRIVATE KEY-----'
        self.assertIn('private key', content_errors(key))

    def test_wrong_installer_hash_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'site/downloads/OutPOSt-Setup-v1.2.3.sha256.txt'
            target.parent.mkdir(parents=True)
            target.write_text('0' * 64 + ' *OutPOSt-Setup-v1.2.3.exe', encoding='utf-8')
            self.assertIn('installer checksum/name mismatch', installer_errors('site/downloads/OutPOSt-Setup-v1.2.3.exe', b'MZdemo', root))

    def test_oversize_installer_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn('installer exceeds Pages 25 MiB asset limit', installer_errors('site/downloads/OutPOSt-Setup-v1.2.3.exe', b'MZ' + bytes(25 * 1024 * 1024), Path(directory)))

    def test_unreviewed_image_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'screenshots/demo.png'
            file.parent.mkdir()
            Image.new('RGB', (100, 100)).save(file)
            self.assertIn('screenshot needs explicit public-demo review', image_errors(file, None))

    def test_changed_image_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'screenshots/demo.png'
            file.parent.mkdir()
            Image.new('RGB', (100, 100)).save(file)
            self.assertIn('screenshot differs from reviewed bytes', image_errors(file, {'status': 'reviewed-public-demo', 'sha256': '0' * 64}))

    def test_reviewed_image_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'screenshots/demo.png'
            file.parent.mkdir()
            picture = Image.new('RGB', (640, 480), 'white')
            picture.paste('navy', (20, 20, 620, 160))
            picture.save(file)
            self.assertEqual(image_errors(file, {'status': 'reviewed-public-demo', 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}), [])

    def test_review_does_not_allow_blank_screenshot(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'screenshots/blank.png'
            file.parent.mkdir()
            Image.new('RGB', (1920, 1080), 'white').save(file)
            reviewed = {'status': 'reviewed-public-demo', 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}
            self.assertIn('screenshot is blank or practically uniform', image_errors(file, reviewed))

    def test_review_does_not_allow_tiny_screenshot(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'screenshots/tiny.png'
            file.parent.mkdir()
            Image.new('RGB', (16, 16)).save(file)
            reviewed = {'status': 'reviewed-public-demo', 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}
            self.assertIn('screenshot is too small to demonstrate the application', image_errors(file, reviewed))

if __name__ == '__main__':
    unittest.main()
