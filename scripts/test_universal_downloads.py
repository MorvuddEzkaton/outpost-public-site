"""Synthetic UI/receipt tests. No release, signing or acceptance generation."""
from pathlib import Path
import hashlib,json,tempfile,unittest
from desktop_bootstrap import render_universal_downloads,validated_bootstrap

class UniversalDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        for folder in ('site/setup','site/downloads','release'): (self.root/folder).mkdir(parents=True)
        bootstrap=b'MZ SYNTHETIC UNIVERSAL SETUP';full=b'MZ SYNTHETIC FULL INSTALLER'
        self.bootstrap_hash=hashlib.sha256(bootstrap).hexdigest().upper();self.full_hash=hashlib.sha256(full).hexdigest().upper()
        (self.root/'site/setup/OutPOSt-Setup.exe').write_bytes(bootstrap)
        (self.root/'site/setup/OutPOSt-Setup.sha256.txt').write_text(self.bootstrap_hash+' *OutPOSt-Setup.exe\n')
        (self.root/'site/downloads/OutPOSt-Setup-v0.25.2.exe').write_bytes(full)
        key=b'SYNTHETIC PUBLIC KEY';(self.root/'release/desktop-update-public-key.xml').write_bytes(key)
        self.receipt=dict(kind='owner-reviewed-universal-setup',runtime='net48',architecture='x86',windows_acceptance='PASS',approved_for_publication=True,size_bytes=len(bootstrap),sha256=self.bootstrap_hash,feed_url='https://outpost.com.ua/updates/desktop/stable.json',public_key_sha256=hashlib.sha256(key).hexdigest().upper(),windows_report_sha256='A'*64,version='1.0.0')
        (self.root/'release/bootstrap.json').write_text(json.dumps(self.receipt))
        html='<script type="application/ld+json">{"downloadUrl":"https://outpost.com.ua/downloads/OutPOSt-Setup-v0.25.2.exe"}</script><section data-download-product="outpost"><div><dt>Інсталятор</dt><dd>27 байти</dd></div><a class="btn btn-primary" download href="/downloads/OutPOSt-Setup-v0.25.2.exe">Завантажити Setup · 16,1 МБ</a><a class="btn btn-outline" href="/downloads/OutPOSt-Setup-v0.25.2.sha256.txt">SHA-256</a><div class="hash-panel"><code>'+self.full_hash+'</code></div></section><section data-download-product="accounting"><a href="/downloads/OutPOSt-Accounting-Setup-v1.0.2.exe">Accounting unchanged</a></section>'
        (self.root/'site/download.html').write_text(html,encoding='utf-8')
        (self.root/'site/index.html').write_text('<a href="/downloads/OutPOSt-Setup-v0.25.2.exe">Download</a><code id="setup-hash">'+self.full_hash+'</code>',encoding='utf-8')
    def test_only_one_product_download_button(self):
        render_universal_downloads(self.root,'0.25.2');html=(self.root/'site/download.html').read_text()
        self.assertEqual(html.count('href="/setup/OutPOSt-Setup.exe"'),1)
        self.assertNotIn('href="/downloads/OutPOSt-Setup-v0.25.2.exe"',html)
        self.assertIn('https://outpost.com.ua/downloads/OutPOSt-Setup-v0.25.2.exe',html)
        self.assertTrue((self.root/'site/downloads/OutPOSt-Setup-v0.25.2.exe').exists())
    def test_checksum_matches_actual_download_and_keeps_recovery_integrity(self):
        render_universal_downloads(self.root,'0.25.2');html=(self.root/'site/download.html').read_text()
        self.assertIn(self.bootstrap_hash,html);self.assertIn(self.full_hash,html)
        self.assertIn('href="/setup/OutPOSt-Setup.sha256.txt"',html)
        self.assertIn('<code id="setup-hash">'+self.bootstrap_hash+'</code>',(self.root/'site/index.html').read_text())
    def test_accounting_stays_independent(self):
        render_universal_downloads(self.root,'0.25.2')
        self.assertIn('<section data-download-product="accounting"><a href="/downloads/OutPOSt-Accounting-Setup-v1.0.2.exe">Accounting unchanged</a></section>',(self.root/'site/download.html').read_text())
    def test_repeated_release_render_is_idempotent(self):
        render_universal_downloads(self.root,'0.25.2');before=(self.root/'site/download.html').read_bytes()
        render_universal_downloads(self.root,'0.25.2');self.assertEqual(before,(self.root/'site/download.html').read_bytes())
    def test_unapproved_downloader_cannot_change_buttons(self):
        self.receipt['approved_for_publication']=False;(self.root/'release/bootstrap.json').write_text(json.dumps(self.receipt))
        before=(self.root/'site/download.html').read_bytes()
        with self.assertRaises(ValueError):render_universal_downloads(self.root,'0.25.2')
        self.assertEqual(before,(self.root/'site/download.html').read_bytes())

if __name__=='__main__':unittest.main()
