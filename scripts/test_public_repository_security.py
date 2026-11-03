"""Offline negative regressions; synthetic values never contact any service."""
from pathlib import Path
import hashlib
import tempfile
import unittest
from PIL import Image
from verify_public_repository_security import path_errors, content_errors, installer_errors, image_errors, workflow_errors

class PublicSecurityTests(unittest.TestCase):
    def test_zero_price_is_scoped_to_the_identified_lite_application(self):
        import json,copy
        from verify_public_license_terms import validate_structured_commercial_facts
        page='https://outpost.com.ua/bezkoshtovna-programa-dlya-magazynu'
        url='https://outpost.com.ua/downloads/OutPOSt-Lite-Setup-v1.1.0.exe'
        app={'@type':'SoftwareApplication','@id':page+'#lite-software','name':'OutPOSt Lite','isAccessibleForFree':True,'downloadUrl':url,'offers':{'@type':'Offer','@id':page+'#lite-offer','price':'0','priceCurrency':'UAH','url':url,'itemOffered':{'@id':page+'#lite-software'}}}
        def errors(value,location=page):
            result=[];validate_structured_commercial_facts(location,'<script type="application/ld+json">'+json.dumps(value)+'</script>',result);return result
        self.assertEqual(errors(app),[])
        for key,value in [('name','OutPOSt'),('isAccessibleForFree',False),('downloadUrl','https://example.com/setup.exe')]:
            bad=copy.deepcopy(app);bad[key]=value;self.assertTrue(errors(bad),key)
        bad=copy.deepcopy(app);bad['offers']['price']='2000';self.assertTrue(errors(bad))
        self.assertTrue(errors(app,'https://outpost.com.ua/license'))
        self.assertTrue(errors({'@type':'Offer','price':'0','priceCurrency':'UAH'}))

    def test_lite_keeps_a_distinct_canonical_product_identity(self):
        from verify_public_seo_uniqueness import is_lite_software
        page='https://outpost.com.ua/bezkoshtovna-programa-dlya-magazynu'
        app={'@type':'SoftwareApplication','@id':page+'#lite-software','url':page,'name':'OutPOSt Lite','isAccessibleForFree':True,'downloadUrl':'https://outpost.com.ua/downloads/OutPOSt-Lite-Setup-v1.1.0.exe'}
        self.assertTrue(is_lite_software(app,page))
        self.assertFalse(is_lite_software(app,'https://outpost.com.ua/'))
        for key,value in [('name','OutPOSt'),('@id','https://outpost.com.ua/#software'),('isAccessibleForFree',False),('downloadUrl','https://example.com/setup.exe')]:
            self.assertFalse(is_lite_software(dict(app,**{key:value}),page),key)

    def test_download_checksums_remain_product_specific_with_lite(self):
        import re
        from verify_accounting_release import guard_download_consistency,ROOT
        text=(ROOT/'site/download.html').read_text(encoding='utf-8')
        errors=[];guard_download_consistency(text,errors);self.assertEqual(errors,[])
        if 'data-download-product="lite"' in text:
            card=re.search(r'<section\b(?=[^>]*data-download-product="lite")[^>]*>.*?</section>',text,re.S).group(0)
            checksum=re.search(r'\b[A-F0-9]{64}\b',card).group(0)
            errors=[];guard_download_consistency(text.replace(checksum,'F'*64),errors);self.assertTrue(errors)

    def test_only_reviewed_lite_has_an_independent_structured_version(self):
        import json
        from verify_release_metadata import full_release_metadata, SOFTWARE_VERSION_RE
        page='https://outpost.com.ua/bezkoshtovna-programa-dlya-magazynu'
        app={'@type':'SoftwareApplication','@id':page+'#lite-software','url':page,'name':'OutPOSt Lite','isAccessibleForFree':True,'softwareVersion':'1.1.0','downloadUrl':'https://outpost.com.ua/downloads/OutPOSt-Lite-Setup-v1.1.0.exe'}
        def versions(node, filename='bezkoshtovna-programa-dlya-magazynu.html'):
            text='<script type="application/ld+json">'+json.dumps({'@graph':[{'softwareVersion':'0.25.3'},node]})+'</script>'
            return SOFTWARE_VERSION_RE.findall(full_release_metadata(text,filename))
        self.assertEqual(versions(app),['0.25.3'])
        self.assertEqual(versions(app,'license.html'),['0.25.3','1.1.0'])
        for key,value in [('name','OutPOSt'),('@id',page+'#software'),('isAccessibleForFree',False),('downloadUrl','https://example.com/setup.exe'),('softwareVersion','9.9.9')]:
            self.assertEqual(len(versions(dict(app,**{key:value}))),2,key)

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

    def test_lite_requires_its_own_reviewed_receipt(self):
        from release_test_fixtures import synthetic_pe,write_synthetic_receipt
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            name='site/downloads/OutPOSt-Lite-Setup-v1.1.0.exe'
            exe=root/name;exe.parent.mkdir(parents=True);exe.write_bytes(synthetic_pe())
            exe.with_suffix('.sha256.txt').write_text(hashlib.sha256(exe.read_bytes()).hexdigest().upper()+' *'+exe.name+'\n',encoding='utf-8')
            self.assertIn('Lite installer requires matching reviewed Windows acceptance',installer_errors(name,exe.read_bytes(),root))
            write_synthetic_receipt(root,exe,'lite','1.1.0')
            self.assertEqual(installer_errors(name,exe.read_bytes(),root),[])
            self.assertIn('unexpected executable',installer_errors(name.replace('Lite-','Other-'),exe.read_bytes(),root))

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
