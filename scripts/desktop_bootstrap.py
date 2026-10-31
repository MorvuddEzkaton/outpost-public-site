"""One visible downloader, independently reviewed full recovery packages retained."""
from pathlib import Path
import hashlib, re

BOOTSTRAP_RELATIVE='site/setup/OutPOSt-Setup.exe'
BOOTSTRAP_URL='/setup/OutPOSt-Setup.exe'
CHECKSUM_URL='/setup/OutPOSt-Setup.sha256.txt'

def validated_bootstrap(root):
    from verify_public_repository_security import installer_errors
    root=Path(root); source=root/BOOTSTRAP_RELATIVE
    if not source.exists(): return None
    payload=source.read_bytes(); errors=installer_errors(BOOTSTRAP_RELATIVE,payload,root)
    if errors: raise ValueError('; '.join(errors))
    return dict(sha256=hashlib.sha256(payload).hexdigest().upper(),size_bytes=len(payload),url=BOOTSTRAP_URL,checksum_url=CHECKSUM_URL)

def render_universal_downloads(root,version):
    root=Path(root); bootstrap=validated_bootstrap(root)
    if bootstrap is None: raise ValueError('Reviewed universal downloader is required before changing buttons')
    exe='OutPOSt-Setup-v'+version+'.exe'; full=root/'site/downloads'/exe
    full_hash=hashlib.sha256(full.read_bytes()).hexdigest().upper()
    full_mb=f'{full.stat().st_size/1_000_000:.1f}'.replace('.',',')
    changes={}
    for source in sorted((root/'site').glob('*.html')):
        original=source.read_text(encoding='utf-8'); text=original
        # Only current product anchors change. Historical packages, JSON-LD and
        # Accounting's independent installer/receipt/links remain untouched.
        text=text.replace('href="/downloads/'+exe+'"','href="'+BOOTSTRAP_URL+'"')
        text=text.replace('href="/downloads/'+exe.removesuffix('.exe')+'.sha256.txt"','href="'+CHECKSUM_URL+'"')
        if source.name=='index.html':
            text=re.sub(r'(<code\b[^>]*id="setup-hash"[^>]*>)\s*[A-Fa-f0-9]{64}\s*(</code>)',lambda m:m[1]+bootstrap['sha256']+m[2],text)
            text=text.replace('Get-FileHash .\\'+exe,'Get-FileHash .\\OutPOSt-Setup.exe')
        if source.name=='download.html':
            # The visible checksum belongs to the file actually downloaded. Full
            # package integrity is still visible in the separate technical facts.
            text=text.replace(full_hash,bootstrap['sha256'])
            text=text.replace('Get-FileHash .\\'+exe,'Get-FileHash .\\OutPOSt-Setup.exe')
            panel=re.search(r'<section\b[^>]*data-download-product="outpost"[^>]*>.*?</section>',text,re.S)
            if panel is None: raise ValueError('OutPOSt download card missing')
            card=panel[0]
            card=re.sub(r'(<a\b(?=[^>]*href="/setup/OutPOSt-Setup.exe")[^>]*>).*?(</a>)',r'\1Завантажити OutPOSt\2',card,flags=re.S)
            card=re.sub(r'(<a\b[^>]*class=")btn btn-outline("[^>]*href="/setup/OutPOSt-Setup.sha256.txt")',r'\1text-link\2',card)
            card=re.sub(r'Від v[0-9.]+ це відбувається без додаткової повної копії бази перед встановленням\.',
                'Встановлення не вимагає додаткової повної копії бази. Сумісні оновлення передають лише змінені файли; за потреби використовується повний пакет.',card)
            card=re.sub(r'<p\b[^>]*data-universal-download-info=""[^>]*>.*?</p>','',card,flags=re.S)
            # Move the old button-size marker to the program package facts. The
            # normal future-release preparation tool keeps updating this marker.
            card=re.sub(r'Setup\s*·\s*[0-9]+(?:[,.][0-9]+)?\s*МБ','пакет програми',card)
            info='<p class="muted" data-universal-download-info="">Завантажувач: '+str(round(bootstrap['size_bytes']/1024))+' КБ. Автоматично отримує актуальний пакет програми: Setup · '+full_mb+' МБ. Для встановлення потрібен Інтернет.</p>'
            facts='<details data-full-package-integrity=""><summary>Контрольна сума пакета програми v'+version+'</summary><p>Повний інсталятор зберігається на сервері для встановлення та відновлення. SHA-256:</p><div class="hash-panel"><code>'+full_hash+'</code></div></details>'
            if 'data-full-package-integrity=""' in card:
                card=re.sub(r'<details data-full-package-integrity="">.*?</details>',facts,card,flags=re.S)
            else:
                card=card.replace('</section>',facts+'</section>')
            card=card.replace('</section>',info+'</section>')
            text=text[:panel.start()]+card+text[panel.end():]
            text=text.replace('<h3>OutPOSt v'+version+'</h3>','<h3>Завантажувач OutPOSt</h3>')
        if text!=original:
            source.write_text(text,encoding='utf-8',newline='\n');changes[source.relative_to(root).as_posix()]=hashlib.sha256(text.encode()).hexdigest()
    return changes
