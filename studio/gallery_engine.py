"""Conservative gallery-dl adapter. Site operation remains unverified until tested.

No user config, browser-cookie extraction, alternate-source fallback or bypass flags.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from urllib.parse import urlsplit
import zipfile
from sources import parse_source
from site_sessions import CookieVault,session_provider

IMAGE_SUFFIXES={'.jpg','.jpeg','.png','.gif','.webp','.avif'}


@contextmanager
def cookie_snapshot(url):
    """A per-attempt private snapshot; gallery-dl cannot rewrite the saved session."""
    root=os.environ.get('STUDIO_SESSION_DIR')
    if not root:
        yield os.environ.get('STUDIO_ENGINE_COOKIES'); return
    vault=CookieVault(root,readonly=True);provider=session_provider(url)
    try: cookies=vault.read(provider)
    except FileNotFoundError:
        yield None; return
    # Expired/invalid saved sessions fail rather than silently becoming anonymous.
    import http.cookiejar
    with tempfile.TemporaryDirectory(prefix='studio-session-') as directory:
        path=Path(directory)/'cookies.txt'
        jar=http.cookiejar.MozillaCookieJar(str(path))
        for cookie in cookies:jar.set_cookie(cookie)
        jar.save(ignore_discard=True,ignore_expires=False);path.chmod(0o600)
        yield str(path)


def engine_argv(url,output,cookies=None):
    source=parse_source(url)
    if urlsplit(source['url']).hostname=='exhentai.org':
        # gallery-dl silently falls back to E-Hentai when ExHentai cookies are absent.
        # Do not permit this behavior; authenticated ExHentai support needs validation.
        raise ValueError('ExHentai is disabled until authenticated same-source behavior is verified')
    args=[sys.executable,'-m','gallery_dl','--config-ignore','--no-input','--no-colors',
          '--retries','0','--http-timeout','30','--sleep-request','3',
          '--write-info-json','--directory',str(Path(output).resolve()),
          '--filename','{num:04}.{extension}',
          '-o','extractor.exhentai.source=gallery',
          '-o','extractor.exhentai.original=false',
          '-o','extractor.exhentai.fallback-retries=0']
    if cookies:
        path=Path(cookies).resolve(strict=True)
        if not path.is_file():raise ValueError('Cookies must be an explicitly supplied file')
        args.extend(['--cookies',str(path)])
    return args+['--',source['url']]


def is_image(path):
    with path.open('rb') as stream:head=stream.read(32)
    return (head.startswith(b'\xff\xd8\xff') or head.startswith(b'\x89PNG\r\n\x1a\n') or
            head.startswith((b'GIF87a',b'GIF89a')) or
            (head.startswith(b'RIFF') and head[8:12]==b'WEBP') or
            (head[4:8]==b'ftyp' and (b'avif' in head[8:] or b'avis' in head[8:])))


def package_images(root,source=None):
    root=Path(root).resolve();files=[]
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('Symbolic links are not supported')
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            if not is_image(path):raise ValueError('Downloaded file is not a recognized image')
            files.append(path)
    if not files:raise ValueError('No verified images were downloaded')
    metadata={};original_metadata=None
    info=root/'info.json'
    if info.exists():
        if info.is_symlink() or info.stat().st_size>4*1024*1024:raise ValueError('Invalid metadata file')
        original_metadata=info.read_text(encoding='utf-8')
        metadata=json.loads(original_metadata)
        if not isinstance(metadata,dict):raise ValueError('Gallery metadata must be an object')
    if source:metadata['source']=source['url']
    metadata.setdefault('tags',[])
    name=(source['provider']+'-'+source['external_id']) if source else 'gallery'
    archive=root/(name+'.cbz')
    fd,temporary=tempfile.mkstemp(prefix='.gallery-',suffix='.part',dir=root)
    try:
        with os.fdopen(fd,'w+b') as stream:
            with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as output:
                for path in files:output.write(path,path.relative_to(root).as_posix())
                if metadata.get('source') or info.exists():output.writestr('info.json',json.dumps(metadata,ensure_ascii=False))
                if original_metadata is not None:output.writestr('gallery-dl-original.json',original_metadata)
            stream.flush();os.fsync(stream.fileno())
        # LRR's watcher sees only the complete CBZ. Never overwrite an existing one.
        os.link(temporary,archive)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return len(files)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();root=Path(args.output).resolve(strict=True)
    with cookie_snapshot(args.url) as cookies:
        argv=engine_argv(args.url,root,cookies)
        result=subprocess.run(argv,stdin=subprocess.DEVNULL,check=False)
    if result.returncode:raise SystemExit(result.returncode)
    count=package_images(root,parse_source(args.url))
    (root/'studio-source.json').write_text(json.dumps({'source':parse_source(args.url),'engine':'gallery-dl','version':'1.32.16','pages':count},ensure_ascii=False),encoding='utf-8')
    print('Verified image pages packaged:',count)


if __name__=='__main__':main()
