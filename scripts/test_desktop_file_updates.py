"""Synthetic negative tests; never creates Windows acceptance or deploys assets."""
from pathlib import Path
from datetime import datetime, timezone
import base64, copy, gzip, hashlib, json, tempfile, unittest
from unittest.mock import patch
import desktop_file_updates as files
import desktop_update_feed as feed
import verify_public_repository_security as security
import prepare_desktop_delivery as delivery

class FileDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
        self.blobs=self.root/files.BLOB_ROOT; self.blobs.mkdir(parents=True)
        raw={'OutPOSt.exe':b'MZ SYNTHETIC PROGRAM','OutPOSt.exe.config':b'SYNTHETIC CONFIG','release-info.txt':b'Version=0.25.2'}
        raw['release-manifest.sha256']=''.join(hashlib.sha256(data).hexdigest().upper()+'\t'+str(len(data))+'\t'+name+'\n' for name,data in raw.items()).encode()
        rows=[]
        for name,data in raw.items():
            compressed=gzip.compress(data,mtime=0); digest=hashlib.sha256(compressed).hexdigest().upper()
            (self.blobs/(digest.lower()+'.gz')).write_bytes(compressed)
            rows.append(dict(path=name,size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest().upper(),gzip_size_bytes=len(compressed),gzip_sha256=digest))
        self.update=dict(schema=1,contract=files.CONTRACT,minimum_installed='0.25.1',files=rows,removed=[])
        self.receipt=dict(payload_manifest_sha256=hashlib.sha256(raw['release-manifest.sha256']).hexdigest().upper())
    def test_complete_reviewed_payload(self):
        self.assertEqual(len(files.validate_blobs(self.root,self.update,self.receipt)),4)
    def test_private_paths_rejected(self):
        for path in ('../OutPOSt.exe','OutPOSt.exe:evil','retailpos.db','RetailPOS_Data/retailpos.db','license.json','malicious.exe','ThirdParty/evil.dll'):
            with self.subTest(path=path),self.assertRaises(ValueError): files.program_path(path)
    def test_case_insensitive_duplicate_rejected(self):
        changed=copy.deepcopy(self.update); changed['files'].append(dict(changed['files'][0],path='outpost.exe'))
        with self.assertRaises(ValueError): files.validate_metadata(changed)
    def test_unknown_contract_rejected(self):
        with self.assertRaises(ValueError): files.validate_metadata(dict(self.update,contract='other'))
    def test_boolean_sizes_rejected(self):
        changed=copy.deepcopy(self.update); changed['files'][0]['size_bytes']=True
        with self.assertRaises(ValueError): files.validate_metadata(changed)
    def test_missing_required_file_rejected(self):
        changed=copy.deepcopy(self.update); changed['files']=changed['files'][1:]
        with self.assertRaises(ValueError): files.validate_metadata(changed)
    def test_conflicting_removal_rejected(self):
        with self.assertRaises(ValueError): files.validate_metadata(dict(self.update,removed=['OutPOSt.exe']))
    def test_compressed_corruption_rejected(self):
        path=next(self.blobs.iterdir()); path.write_bytes(path.read_bytes()[::-1])
        with self.assertRaises(ValueError): files.validate_blobs(self.root,self.update,self.receipt)
    def test_uncompressed_bound_enforced(self):
        changed=copy.deepcopy(self.update); changed['files'][0]['size_bytes']=1
        with self.assertRaises(ValueError): files.validate_blobs(self.root,changed,self.receipt)
    def test_receipt_payload_must_match(self):
        with self.assertRaises(ValueError): files.validate_blobs(self.root,self.update,dict(payload_manifest_sha256='A'*64))
    def test_whole_payload_manifest_must_match(self):
        changed=copy.deepcopy(self.update); changed['files'][0]['path']='other.dll'
        with self.assertRaises(ValueError): files.validate_blobs(self.root,changed,self.receipt)
    def test_native_signed_vector(self):
        vector=json.loads((Path(__file__).with_name('fixtures')/'desktop-fast-update-rsa-test-vector.json').read_text())
        self.assertTrue(vector['test_only'])
        item=feed.verify_envelope(base64.b64decode(vector['envelope']),vector['public_key'],datetime(2026,10,30,15,tzinfo=timezone.utc))
        self.assertEqual(item['version'],'0.25.2'); self.assertEqual(len(item['file_update']['files']),5)

class UniversalSetupBoundaryTests(unittest.TestCase):
    def test_unreviewed_universal_setup_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            errors=security.installer_errors('site/setup/OutPOSt-Setup.exe',b'MZ SYNTHETIC SETUP',Path(temporary))
            self.assertTrue(any('acceptance' in error for error in errors))
    def test_other_executable_name_remains_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIn('unexpected executable',security.installer_errors('site/setup/evil.exe',b'MZ SYNTHETIC',Path(temporary)))

class DeliveryPreparationTests(unittest.TestCase):
    """Receipt values below are SYNTHETIC fixtures, never release evidence."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)/'public'; self.bundle=Path(self.temp.name)/'bundle'
        vector=json.loads((Path(__file__).with_name('fixtures')/'desktop-fast-update-rsa-test-vector.json').read_text()); self.envelope=base64.b64decode(vector['envelope'])
        self.item=feed.verify_envelope(self.envelope,vector['public_key'],datetime(2026,10,30,15,tzinfo=timezone.utc))
        for folder in ('release/evidence','site/downloads','site/updates/desktop'): (self.root/folder).mkdir(parents=True,exist_ok=True)
        (self.bundle/'blobs').mkdir(parents=True)
        raw={'OutPOSt.exe':b'N'*65536,'OutPOSt.exe.config':b'unchanged config','release-info.txt':b'Version=0.25.2','new.dll':b'new dependency'}
        rows=self.item['file_update']['files']; raw['release-manifest.sha256']=''.join(row['sha256']+'\t'+str(row['size_bytes'])+'\t'+row['path']+'\n' for row in rows if row['path']!='release-manifest.sha256').encode()
        # Exact native gzip bytes: verify the full signed delivery across the
        # native/Python boundary without substituting a hash/decompression gate.
        for row in rows:
            self.assertEqual(hashlib.sha256(raw[row['path']]).hexdigest().upper(),row['sha256'])
            name=row['gzip_sha256'].lower()+'.gz'
            (self.bundle/'blobs'/name).write_bytes(base64.b64decode(vector['blobs'][name]))
        manifest=next(row['sha256'] for row in rows if row['path']=='release-manifest.sha256')
        self.receipt=dict(kind='owner-reviewed-windows-release',product='outpost',version='0.25.2',installer='OutPOSt-Setup-v0.25.2.exe',size_bytes=2048,sha256=self.item['sha256'],windows_acceptance='PASS',runtime='net48',architecture='x86',approved_for_publication=True,published_date='2026-10-30',payload_manifest_sha256=manifest)
        (self.root/'release/evidence/outpost-v0.25.2.json').write_text(json.dumps(self.receipt))
        (self.root/'release/desktop-update-public-key.xml').write_text(vector['public_key'])
        (self.root/'release/artifact-registry.json').write_text(json.dumps(dict(artifacts=[self.receipt])))
        (self.root/'site/downloads/OutPOSt-Setup-v0.25.2.exe').write_bytes(bytes(2048))
        (self.root/'site/download.html').write_text('<a href="/downloads/OutPOSt-Setup-v0.25.2.exe">SYNTHETIC FALLBACK</a>')
        (self.root/'site/updates/desktop/stable.json').write_bytes(b'SYNTHETIC PREVIOUS FEED')
        (self.bundle/'file-update.json').write_text(json.dumps(dict(installer_sha256=self.item['sha256'],payload_manifest_sha256=manifest,file_update=self.item['file_update'])))
        self.source=Path(self.temp.name)/'signed.json'; self.source.write_bytes(self.envelope)
        self.addCleanup(patch.stopall)
        patch('desktop_update_feed.datetime',FixtureDateTime).start()
    def test_stages_full_fallback_and_signed_archive(self):
        result=delivery.prepare(self.root,self.bundle,self.source)
        self.assertEqual(result['version'],'0.25.2')
        self.assertEqual((self.root/'site/updates/desktop/stable.json').read_bytes(),self.envelope)
        self.assertEqual((self.root/'release/desktop-updates/0.25.2.json').read_bytes(),self.envelope)
        self.assertEqual((self.root/'site/downloads/OutPOSt-Setup-v0.25.2.exe').read_bytes(),bytes(2048))
    def test_missing_full_installer_cannot_advance_feed(self):
        (self.root/'site/downloads/OutPOSt-Setup-v0.25.2.exe').unlink()
        with self.assertRaises(OSError): delivery.prepare(self.root,self.bundle,self.source)
        self.assertEqual((self.root/'site/updates/desktop/stable.json').read_bytes(),b'SYNTHETIC PREVIOUS FEED')

class FixtureDateTime(datetime):
    @classmethod
    def now(cls,tz=None): return cls(2026,10,30,15,tzinfo=timezone.utc)

if __name__=='__main__': unittest.main()
