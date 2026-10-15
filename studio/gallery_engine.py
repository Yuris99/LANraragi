"""Conservative gallery-dl adapter. Site operation remains unverified until tested.

No user config, browser-cookie extraction, alternate-source fallback or bypass flags.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
import zipfile
from sources import parse_source

IMAGE_SUFFIXES={'.jpg','.jpeg','.png','.gif','.webp','.avif'}


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
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_STORED) as output:
        for path in files:output.write(path,path.relative_to(root).as_posix())
        if metadata.get('source') or info.exists():output.writestr('info.json',json.dumps(metadata,ensure_ascii=False))
        if original_metadata is not None:output.writestr('gallery-dl-original.json',original_metadata)
    return len(files)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();root=Path(args.output).resolve(strict=True)
    argv=engine_argv(args.url,root,os.environ.get('STUDIO_ENGINE_COOKIES'))
    result=subprocess.run(argv,stdin=subprocess.DEVNULL,check=False)
    if result.returncode:raise SystemExit(result.returncode)
    count=package_images(root,parse_source(args.url))
    (root/'studio-source.json').write_text(json.dumps({'source':parse_source(args.url),'engine':'gallery-dl','version':'1.32.16','pages':count},ensure_ascii=False),encoding='utf-8')
    print('Verified image pages packaged:',count)


if __name__=='__main__':main()
