from pathlib import Path
from datetime import datetime,timezone
import base64,json,unittest
import desktop_update_feed as feed
import verify_security_headers as security_headers

class SignedFeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vector=json.loads((Path(__file__).with_name('fixtures')/'desktop-update-rsa-test-vector.json').read_text(encoding='utf-8'))
        assert cls.vector['test_only'] is True
        cls.envelope=base64.b64decode(cls.vector['envelope_base64']);cls.key=cls.vector['public_key_xml']
        cls.now=datetime(2026,10,26,14,0,tzinfo=timezone.utc)
    def verify(self,envelope=None,key=None,now=None):
        return feed.verify_envelope(self.envelope if envelope is None else envelope,self.key if key is None else key,self.now if now is None else now)
    def test_dotnet_signed_vector(self):self.assertEqual(self.verify()['version'],'0.24.47')
    def test_changed_payload(self):
        outer=json.loads(self.envelope);outer['payload']=base64.b64encode(b'{"version":"9.9.9"}').decode()
        with self.assertRaises(ValueError):self.verify(json.dumps(outer).encode())
    def test_changed_signature(self):
        outer=json.loads(self.envelope);signature=bytearray(base64.b64decode(outer['signature']));signature[-1]^=1;outer['signature']=base64.b64encode(signature).decode()
        with self.assertRaises(ValueError):self.verify(json.dumps(outer).encode())
    def test_padding_forgery(self):
        outer=json.loads(self.envelope);outer['signature']=base64.b64encode(bytes(384)).decode()
        with self.assertRaises(ValueError):self.verify(json.dumps(outer).encode())
    def test_unknown_key(self):
        outer=json.loads(self.envelope);outer['key_id']='other'
        with self.assertRaises(ValueError):self.verify(json.dumps(outer).encode())
    def test_expired(self):
        with self.assertRaises(ValueError):self.verify(now=datetime(2027,6,1,tzinfo=timezone.utc))
    def test_future_issue(self):
        with self.assertRaises(ValueError):self.verify(now=datetime(2026,10,1,tzinfo=timezone.utc))
    def test_oversize(self):
        with self.assertRaises(ValueError):self.verify(bytes(feed.MAX_ENVELOPE+1))
    def test_html_fallback(self):
        with self.assertRaises(ValueError):self.verify(b'<html>fallback</html>')
    def test_duplicate_outer_key(self):
        outer=self.envelope.decode().rstrip();duplicate=(outer[:-1]+',"key_id":"outpost-update-2026-10"}').encode()
        with self.assertRaises(ValueError):self.verify(duplicate)
    def test_private_key_cannot_be_public_pin(self):
        with self.assertRaises(ValueError):self.verify(key=self.key.replace('</RSAKeyValue>','<D>AA==</D></RSAKeyValue>'))
    def test_version_traversal(self):
        with self.assertRaises(ValueError):feed.version('../1.2.3')
    def test_feed_cache_route_is_exact(self):
        text=security_headers.HEADERS_FILE.read_text(encoding='utf-8');routes,_=security_headers.parse_headers(text)
        self.assertEqual(security_headers.header_route_errors(routes),[])
        self.assertTrue(security_headers.header_route_errors([route.replace('/updates/desktop/stable.json','/updates/desktop/*') for route in routes]))
    def test_narrow_route_cannot_override_security(self):
        text=security_headers.HEADERS_FILE.read_text(encoding='utf-8')
        self.assertEqual(security_headers.narrow_cache_route_errors(text),[])
        changed=text.replace('  X-Robots-Tag: noindex, nofollow','  X-Robots-Tag: noindex, nofollow\n  Content-Security-Policy: default-src *')
        self.assertTrue(security_headers.narrow_cache_route_errors(changed))
    def test_feed_cannot_be_cached_immutably(self):
        text=security_headers.HEADERS_FILE.read_text(encoding='utf-8').replace('no-cache, max-age=0, must-revalidate','public, max-age=31536000, immutable',1)
        self.assertTrue(security_headers.narrow_cache_route_errors(text))
    def test_feed_cannot_be_indexed(self):
        text=security_headers.HEADERS_FILE.read_text(encoding='utf-8').replace('X-Robots-Tag: noindex, nofollow','X-Robots-Tag: index, follow')
        self.assertTrue(security_headers.narrow_cache_route_errors(text))
if __name__=='__main__':unittest.main()
