"""Credential-free verifier for the future signed desktop update feed.

No private key, network request, deployment, or release acceptance generation.
Only the pinned public key can authorize the exact signed payload bytes.
"""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import argparse,base64,hashlib,hmac,json,re,xml.etree.ElementTree as ET

KEY_ID='outpost-update-2026-10'
MAX_ENVELOPE=131072
KEY_RELATIVE=Path('release/desktop-update-public-key.xml')
FEED_RELATIVE=Path('site/updates/desktop/stable.json')

def require(condition,message):
    if not condition:raise ValueError(message)
def unique(pairs):
    out={}
    for key,value in pairs:
        require(key not in out,'duplicate JSON key')
        out[key]=value
    return out
def timestamp(text):
    require(isinstance(text,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,7})?Z',text),'invalid timestamp')
    return datetime.fromisoformat(text.replace('Z','+00:00'))
def version(text):
    require(isinstance(text,str) and re.fullmatch(r'(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})(\.(0|[1-9][0-9]{0,4}))?',text),'invalid version')
    parts=tuple(map(int,text.split('.')))
    return parts+(0,)*(4-len(parts))
def verify_envelope(envelope,public_xml,now=None):
    now=now or datetime.now(timezone.utc)
    require(0<len(envelope)<=MAX_ENVELOPE,'invalid envelope size')
    outer=json.loads(envelope.decode('utf-8'),object_pairs_hook=unique)
    require(isinstance(outer,dict) and set(outer)=={'key_id','payload','signature'} and outer['key_id']==KEY_ID,'unknown envelope key')
    payload=base64.b64decode(outer['payload'],validate=True);signature=base64.b64decode(outer['signature'],validate=True)
    require(0<len(payload)<=65536 and len(signature)==384,'invalid payload/signature size')
    require(len(public_xml)<4096,'invalid pinned key size')
    key=ET.fromstring(public_xml)
    require(key.tag=='RSAKeyValue' and set(child.tag for child in key)=={'Modulus','Exponent'},'invalid pinned RSA key')
    modulus=base64.b64decode(key.findtext('Modulus'),validate=True);exponent=base64.b64decode(key.findtext('Exponent'),validate=True)
    n=int.from_bytes(modulus,'big');e=int.from_bytes(exponent,'big');s=int.from_bytes(signature,'big')
    require(len(modulus)==384 and n.bit_length()==3072 and e==65537 and s<n,'invalid RSA parameters')
    digest_info=bytes.fromhex('3031300d060960864801650304020105000420')+hashlib.sha256(payload).digest()
    expected=b'\x00\x01'+b'\xff'*(384-len(digest_info)-3)+b'\x00'+digest_info
    require(hmac.compare_digest(pow(s,e,n).to_bytes(384,'big'),expected),'signature mismatch')
    item=json.loads(payload.decode('utf-8'),object_pairs_hook=unique)
    require(isinstance(item,dict),'invalid payload')
    for name,value in {'schema':1,'product':'OutPOSt','channel':'stable','architecture':'x86','minimum_updater':1}.items():
        require(type(item.get(name)) is type(value) and item[name]==value,'invalid '+name)
    version(item.get('version'))
    require(item.get('installer_url')=='https://outpost.com.ua/downloads/OutPOSt-Setup-v'+item['version']+'.exe','untrusted installer URL')
    require(type(item.get('size_bytes')) is int and 1024<=item['size_bytes']<=536870912,'invalid package size')
    require(isinstance(item.get('sha256'),str) and re.fullmatch('[A-F0-9]{64}',item['sha256']),'invalid package hash')
    require(isinstance(item.get('release_notes'),str) and len(item['release_notes'].encode('utf-16-le'))//2<=24000,'invalid notes')
    published=timestamp(item.get('published_at'));issued=timestamp(item.get('issued_at'));expires=timestamp(item.get('expires_at'))
    require(published<=now+timedelta(hours=24) and issued<=now+timedelta(hours=24) and published<=issued+timedelta(hours=24) and now<expires and issued<expires<=issued+timedelta(days=180),'invalid metadata validity')
    if 'file_update' in item:
        from desktop_file_updates import validate_metadata
        validate_metadata(item['file_update'])
    return item

def validate_feed(root, envelope_path=None, historical=False):
    root=Path(root).resolve()
    envelope=(Path(envelope_path) if envelope_path is not None else root/FEED_RELATIVE).read_bytes()
    now=None
    if historical:
        # Archive validation authorizes retaining old immutable blobs, never runtime
        # installation. Runtime clients always enforce the current expiration date.
        require(0<len(envelope)<=MAX_ENVELOPE,'invalid archived envelope size')
        payload=base64.b64decode(json.loads(envelope)['payload'],validate=True)
        now=timestamp(json.loads(payload)['issued_at'])
    item=verify_envelope(envelope,(root/KEY_RELATIVE).read_text(encoding='utf-8'),now)
    name='OutPOSt-Setup-v'+item['version']+'.exe'
    installer=root/'site/downloads'/name
    digest=hashlib.sha256()
    with installer.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    require(installer.stat().st_size==item['size_bytes'] and digest.hexdigest().upper()==item['sha256'],'package bytes do not match signed metadata')
    receipt=json.loads((root/'release/evidence'/('outpost-v'+item['version']+'.json')).read_text(encoding='utf-8'))
    for field,value in {'kind':'owner-reviewed-windows-release','product':'outpost','version':item['version'],'installer':name,'size_bytes':item['size_bytes'],'sha256':item['sha256'],'windows_acceptance':'PASS','runtime':'net48','architecture':'x86','approved_for_publication':True}.items():
        require(type(receipt.get(field)) is type(value) and receipt[field]==value,'reviewed Windows receipt mismatch: '+field)
    require(item['published_at'][:10]==receipt['published_date'],'publication date differs from reviewed date')
    if 'file_update' in item:
        from desktop_file_updates import validate_blobs
        validate_blobs(root,item['file_update'],receipt)
    registry=json.loads((root/'release/artifact-registry.json').read_text(encoding='utf-8'))['artifacts']
    require(any(row['product']=='outpost' and row['version']==item['version'] and row['installer']==name and row['size_bytes']==item['size_bytes'] and row['sha256']==item['sha256'] for row in registry),'signed artifact is absent from immutable release registry')
    current=set(re.findall(r'OutPOSt-Setup-v(\d+\.\d+\.\d+)\.exe',(root/'site/download.html').read_text(encoding='utf-8')))
    require(len(current)==1 and version(item['version'])<=version(next(iter(current))),'unpublished/future update feed')
    if not historical and (root/'site/setup/OutPOSt-Setup.exe').exists():
        require(item['version']==next(iter(current)),'universal downloader must resolve the current approved release')
    return item

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args()
    item=validate_feed(args.root)
    print('Signed desktop feed PASS: OutPOSt '+item['version']+'; exact approved installer, receipt and immutable registry agree. No publication performed.')
if __name__=='__main__':main()
