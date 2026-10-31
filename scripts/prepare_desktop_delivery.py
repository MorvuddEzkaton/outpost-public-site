"""Stage reviewed desktop delivery assets. Local files only; never deploys or signs."""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil
from desktop_update_feed import KEY_RELATIVE, verify_envelope, validate_feed
from desktop_file_updates import validate_blobs

def require(value,message):
    if not value: raise ValueError(message)

def immutable_copy(source,destination):
    source=Path(source); destination=Path(destination)
    require(not source.is_symlink() and source.is_file(),'unsafe/missing delivery asset')
    for parent in [destination]+list(destination.parents):
        require(not parent.is_symlink() and not (hasattr(parent,'is_junction') and parent.is_junction()),'delivery destination contains a link')
    if destination.exists():
        require(hashlib.sha256(source.read_bytes()).digest()==hashlib.sha256(destination.read_bytes()).digest(),'immutable delivery asset differs: '+destination.name)
        return
    destination.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,destination)

def prepare(root,bundle,envelope,bootstrap=None):
    root=Path(root).resolve(); bundle=Path(bundle).resolve(); envelope=Path(envelope).resolve()
    data=envelope.read_bytes(); item=verify_envelope(data,(root/KEY_RELATIVE).read_text(encoding='utf-8'))
    meta=json.loads((bundle/'file-update.json').read_text(encoding='utf-8'))
    require(meta['installer_sha256']==item['sha256'] and meta['file_update']==item.get('file_update'),'bundle differs from signed installer/file manifest')
    receipt=json.loads((root/'release/evidence'/('outpost-v'+item['version']+'.json')).read_text(encoding='utf-8'))
    require(meta['payload_manifest_sha256']==receipt['payload_manifest_sha256'],'bundle differs from reviewed payload')
    # Validate all compressed and decompressed bytes in a local fixture layout
    # before any existing feed or page is changed.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='outpost-delivery-') as temporary:
        staging=Path(temporary); blobs=staging/'site/updates/desktop/blobs'; blobs.mkdir(parents=True)
        for row in item['file_update']['files']:
            name=row['gzip_sha256'].lower()+'.gz'
            immutable_copy(bundle/'blobs'/name,blobs/name)
        validate_blobs(staging,item['file_update'],receipt)
        for source in blobs.iterdir(): immutable_copy(source,root/'site/updates/desktop/blobs'/source.name)
    archive=root/'release/desktop-updates'/(item['version']+'.json')
    immutable_copy(envelope,archive)
    # This includes the FULL installer, Windows receipt, artifact registry, date
    # and current download metadata gates. Fast blobs never replace those gates.
    validate_feed(root,archive)
    target=root/'site/updates/desktop/stable.json'; temporary=target.with_suffix('.json.new')
    require(not temporary.exists() and not target.is_symlink(),'unsafe feed destination')
    with temporary.open('xb') as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary,target)
    if bootstrap is not None:
        from verify_public_repository_security import installer_errors
        binary=Path(bootstrap).read_bytes(); relative='site/setup/OutPOSt-Setup.exe'
        # Receipt and matching checksum must be provided through the normal
        # reviewed release process; this command cannot manufacture acceptance.
        errors=installer_errors(relative,binary,root); require(not errors,'; '.join(errors))
        immutable_copy(bootstrap,root/relative)
    # Once introduced, the reviewed stable downloader is reused automatically by
    # subsequent releases. Only its server-side package/feed changes each time.
    if (root/'site/setup/OutPOSt-Setup.exe').exists():
        from desktop_bootstrap import render_universal_downloads
        render_universal_downloads(root,item['version'])
    return item

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]); parser.add_argument('--bundle',type=Path,required=True); parser.add_argument('--signed-feed',type=Path,required=True); parser.add_argument('--bootstrap',type=Path)
    args=parser.parse_args(); item=prepare(args.root,args.bundle,args.signed_feed,args.bootstrap)
    print('Prepared desktop delivery '+item['version']+'. Full installer preserved. No publication performed.')
