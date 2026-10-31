"""Bounded validation of signed native program blobs. No signing or publication."""
from pathlib import Path
import gzip, hashlib, re

CONTRACT = 'outpost-inno-net48-x86-v1'
BLOB_ROOT = Path('site/updates/desktop/blobs')

def require(value, message):
    if not value: raise ValueError(message)

def program_path(path):
    require(isinstance(path, str) and len(path) <= 180 and '..' not in path and
            re.fullmatch(r'(?:OutPOSt(?:\.Connector)?\.exe(?:\.config)?|[A-Za-z0-9_.-]+\.(?:dll|so|dylib)|release-info\.txt|release-manifest\.sha256|ThirdParty/ZXing\.Net/(?:LICENSE|NOTICE-OutPOSt)\.txt)', path), 'unsafe program path')
    return path

def validate_metadata(update):
    require(isinstance(update, dict) and update.get('schema') == 1 and update.get('contract') == CONTRACT, 'invalid file update contract')
    minimum = update.get('minimum_installed')
    require(isinstance(minimum, str) and re.fullmatch(r'(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})\.(0|[1-9][0-9]{0,4})(\.(0|[1-9][0-9]{0,4}))?', minimum), 'invalid minimum file updater version')
    parts = tuple(map(int, minimum.split('.')))
    require(parts+(0,)*(4-len(parts)) >= (0,25,1,0), 'unsafe minimum file updater version')
    files = update.get('files'); removed = update.get('removed')
    require(isinstance(files, list) and 1 <= len(files) <= 128 and isinstance(removed, list) and len(removed) <= 128, 'invalid file list')
    names = set(); total = 0
    for row in files:
        require(isinstance(row, dict), 'invalid file row')
        name = program_path(row.get('path')); require(name.lower() not in names, 'duplicate program path'); names.add(name.lower())
        for key in ('sha256','gzip_sha256'):
            require(isinstance(row.get(key),str) and re.fullmatch(r'[A-F0-9]{64}',row[key]), 'invalid file hash')
        for key in ('size_bytes','gzip_size_bytes'):
            require(type(row.get(key)) is int and 1 <= row[key] <= 128*1024*1024, 'invalid file size')
        total += row['size_bytes']
    require(total <= 512*1024*1024, 'oversize program payload')
    require({'outpost.exe','outpost.exe.config','release-info.txt','release-manifest.sha256'} <= names, 'incomplete program manifest')
    for name in removed:
        program_path(name); require(name.lower() not in names, 'conflicting removed path'); names.add(name.lower())
        require(name.lower() not in {'outpost.exe','outpost.exe.config'}, 'cannot remove main application')
    return files

def validate_blobs(root, update, receipt):
    root = Path(root); files = validate_metadata(update); manifest = None
    for row in files:
        blob = root / BLOB_ROOT / (row['gzip_sha256'].lower()+'.gz')
        require(blob.is_file() and not blob.is_symlink() and blob.stat().st_size == row['gzip_size_bytes'], 'missing/unsafe file update blob')
        with blob.open('rb') as compressed:
            require(hashlib.file_digest(compressed,'sha256').hexdigest().upper() == row['gzip_sha256'], 'compressed blob hash mismatch')
        raw_hash = hashlib.sha256(); count = 0; chunks = []
        with gzip.open(blob,'rb') as stream:
            while chunk := stream.read(65536):
                count += len(chunk); require(count <= row['size_bytes'], 'decompressed blob exceeds signed size')
                raw_hash.update(chunk)
                if row['path'] == 'release-manifest.sha256':
                    require(count <= 131072, 'oversize payload manifest'); chunks.append(chunk)
        require(count == row['size_bytes'] and raw_hash.hexdigest().upper() == row['sha256'], 'raw program file mismatch')
        if row['path'] == 'release-manifest.sha256':
            require(row['sha256'] == receipt.get('payload_manifest_sha256'), 'file payload differs from reviewed full installer')
            manifest = b''.join(chunks).decode('utf-8-sig')
    require(manifest is not None, 'missing payload manifest')
    expected = {row['path']:(row['sha256'],row['size_bytes']) for row in files if row['path'] != 'release-manifest.sha256'}
    actual = {}
    for line in manifest.splitlines():
        if not line.strip(): continue
        fields = line.split('\t'); require(len(fields)==3, 'invalid payload manifest row')
        name = program_path(fields[2]); require(name not in actual, 'duplicate payload manifest row')
        actual[name] = (fields[0],int(fields[1]))
    require(actual == expected, 'file update does not describe exact reviewed payload')
    return {row['gzip_sha256'].lower()+'.gz' for row in files}

def validated_blob_inventory(root):
    from desktop_update_feed import validate_feed
    root=Path(root); result=set()
    archives=sorted((root/'release/desktop-updates').glob('*.json'))
    for source in [None]+archives:
        item=validate_feed(root,source,historical=source is not None)
        if source is not None: require(source.stem==item['version'], 'archived feed/version mismatch')
        for row in item.get('file_update',{}).get('files',[]): result.add(row['gzip_sha256'].lower()+'.gz')
    return result
