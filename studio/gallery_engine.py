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
import http.cookiejar
import re
import urllib.request
from http.cookies import SimpleCookie
from contextlib import contextmanager
from urllib.parse import urlsplit
import zipfile
from sources import parse_source,hitomi_download_metadata
from site_sessions import CookieVault,session_provider

IMAGE_SUFFIXES={'.jpg','.jpeg','.png','.gif','.webp','.avif'}
ADAPTER_VERSION='same-source-1'


def diagnostic(root,category,code,http_status=None):
    value={'engine':'gallery-dl','adapter':ADAPTER_VERSION,'category':category,'exit_code':code}
    if type(http_status) is int and 100<=http_status<=599:value['http_status']=http_status
    (Path(root)/'studio-engine-result.json').write_text(json.dumps(value),encoding='utf-8')


def require_ex_session(path,url):
    if not path:raise ValueError('익헨용 로그인 세션이 필요합니다.')
    jar=http.cookiejar.MozillaCookieJar(str(path));jar.load(ignore_discard=True,ignore_expires=False)
    request=urllib.request.Request(url);jar.add_cookie_header(request)
    values=SimpleCookie();values.load(request.get_header('Cookie',''))
    if not all(name in values and values[name].value for name in ('ipb_member_id','ipb_pass_hash')):
        raise ValueError('익헨에 적용되는 로그인 쿠키가 없거나 만료되었습니다.')
    return jar


def strict_ex_download(url,output,cookies,verification=False):
    """Pinned extractor, actual host/path cookie validation, no cross-origin login."""
    from gallery_dl import config,exception,job
    from gallery_dl.extractor.common import Message
    from gallery_dl.extractor.exhentai import ExhentaiGalleryExtractor
    import logging
    source=parse_source(url)
    if source['provider']!='exhentai':raise ValueError('익헨 작품 주소가 필요합니다.')
    require_ex_session(cookies,url)
    config.clear()
    options={'domain':'exhentai.org','source':'gallery','original':False,'fallback-retries':0,
             'cookies':str(cookies),'base-directory':str(Path(output).resolve()),'directory':[],
             'filename':'{num:04}.{extension}','retries':0,'timeout':30,'sleep-request':3,
             'input':False,'verify':True,'metadata':False,'skip':False,'async':False}
    for key,value in options.items():config.set(('extractor','exhentai'),key,value)
    config.set(('cache',),'file',False)
    logging.basicConfig(level=logging.WARNING,format='%(levelname)s: %(message)s')
    class SameSourceExtractor(ExhentaiGalleryExtractor):
        def items(self):
            for message in super().items():
                yield message
                if verification and message[0]==Message.Url:return

        def _image_page(self):
            # 1.32.16 can retain /gid-page from the first gallery href.
            if '/' in self.image_token:
                token,suffix=self.image_token.split('/',1)
                if not re.fullmatch('[0-9a-f]{10}',token) or suffix!=f'{self.gallery_id}-{self.image_num}':
                    raise self.exc.ExtractionError('invalid_image_page_identity')
                self.image_token=token
            return super()._image_page()

        def login(self):
            if self.root!='https://exhentai.org':raise self.exc.AuthorizationError('source_domain_changed')
            request=urllib.request.Request(url);self.cookies.add_cookie_header(request)
            values=SimpleCookie();values.load(request.get_header('Cookie',''))
            if not all(name in values and values[name].value for name in self.cookies_names):
                raise self.exc.AuthenticationError('saved_session_not_applicable')

        def request(self,target,**kwargs):
            value=urlsplit(target)
            if value.scheme!='https' or value.hostname!='exhentai.org' or value.username or value.password or value.port:
                diagnostic(output,'source_changed',16)
                raise self.exc.AuthorizationError('source_domain_changed')
            kwargs['allow_redirects']=False
            try:response=super().request(target,**kwargs)
            except self.exc.HttpError as error:
                status=getattr(error,'status',0)
                diagnostic(output,'access_required' if status in (401,403,429) else 'connection_failed' if not status else 'http_error',error.code,status)
                raise
            status=response.status_code
            if 300<=status<400:
                diagnostic(output,'login_redirect',16,status)
                raise self.exc.AuthenticationError('login_redirect_not_followed')
            if status in (401,403,429):
                diagnostic(output,'access_required',16,status)
                raise self.exc.AuthorizationError('access_required')
            if status in (404,410):
                diagnostic(output,'not_found',4,status)
                raise self.exc.NotFoundError('gallery')
            return response

    class GalleryJob(job.DownloadJob):
        def handle_directory(self,data):
            if str(data.get('gid'))!=source['external_id'] or data.get('token')!=source['url'].rstrip('/').split('/')[-1]:
                raise exception.ExtractionError('gallery_identity_mismatch')
            super().handle_directory(data)
            # Only public gallery metadata; never account/archiver credentials.
            fields=('gid','token','title','title_jpn','eh_category','uploader','date','parent','language','filesize','filecount','favorites','rating','tags','lang')
            public={key:data[key] for key in fields if key in data}
            (Path(output)/'info.json').write_text(json.dumps(public,ensure_ascii=False,default=str),encoding='utf-8')

    extractor=SameSourceExtractor.from_url(source['url'])
    if extractor is None:raise ValueError('익헨 작품 URL의 번호·식별값을 확인하세요.')
    result=GalleryJob(extractor).run()
    if result and not (Path(output)/'studio-engine-result.json').exists():
        diagnostic(output,'auth_failed' if result&16 else 'extraction_failed',result)
    return result


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
    host=urlsplit(url).hostname
    cookies=[cookie for cookie in cookies if host==cookie.domain.lstrip('.') or
             (cookie.domain.startswith('.') and host.endswith(cookie.domain))]
    if not cookies:raise ValueError('이 주소에 적용되는 저장 계정 쿠키가 없습니다.')
    # Expired/invalid saved sessions fail rather than silently becoming anonymous.
    import http.cookiejar
    with tempfile.TemporaryDirectory(prefix='studio-session-') as directory:
        path=Path(directory)/'cookies.txt'
        jar=http.cookiejar.MozillaCookieJar(str(path))
        for cookie in cookies:jar.set_cookie(cookie)
        jar.save(ignore_discard=True,ignore_expires=False);path.chmod(0o600)
        yield str(path)


def engine_argv(url,output,cookies=None,verification=False):
    source=parse_source(url)
    if urlsplit(source['url']).hostname=='exhentai.org':
        require_ex_session(cookies,source['url'])
        return [sys.executable,str(Path(__file__).resolve()),'--strict-exhentai','--url',source['url'],
                '--output',str(Path(output).resolve()),'--cookies',str(Path(cookies).resolve())]+(['--verify'] if verification else [])
    if verification:raise ValueError('연결 검증은 익헨에서 지원합니다.')
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
    infos=list(root.rglob('info.json'))
    if len(infos)>1:raise ValueError('Multiple gallery metadata files require review')
    info=infos[0] if infos else None
    if info:
        if info.is_symlink() or info.stat().st_size>4*1024*1024:raise ValueError('Invalid metadata file')
        original_metadata=info.read_text(encoding='utf-8')
        metadata=json.loads(original_metadata)
        if not isinstance(metadata,dict):raise ValueError('Gallery metadata must be an object')
    if source:metadata['source']=source['url']
    metadata.setdefault('tags',[])
    receipt={'source':source,'engine':'gallery-dl','version':'1.32.16','pages':len(files)} if source else None
    if receipt:
        normalized=hitomi_download_metadata(source,metadata,len(files))
        if normalized:receipt['metadata']=normalized
    name=(source['provider']+'-'+source['external_id']) if source else 'gallery'
    archive=root/(name+'.cbz')
    fd,temporary=tempfile.mkstemp(prefix='.gallery-',suffix='.part',dir=root)
    try:
        with os.fdopen(fd,'w+b') as stream:
            with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as output:
                for path in files:output.write(path,path.relative_to(root).as_posix())
                if metadata.get('source') or info:output.writestr('info.json',json.dumps(metadata,ensure_ascii=False))
                if original_metadata is not None:output.writestr('gallery-dl-original.json',original_metadata)
                if receipt:output.writestr('studio-source.json',json.dumps(receipt,ensure_ascii=False))
            stream.flush();os.fsync(stream.fileno())
        if receipt:(root/'studio-source.json').write_text(json.dumps(receipt,ensure_ascii=False),encoding='utf-8')
        # LRR's watcher sees only the complete CBZ. Never overwrite an existing one.
        os.link(temporary,archive)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return len(files)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--strict-exhentai',action='store_true');parser.add_argument('--cookies')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();root=Path(args.output).resolve(strict=True)
    try:
        source=parse_source(args.url)
        if source['provider']=='exhentai' and not re.fullmatch(r'https://exhentai.org/g/[0-9]+/[0-9a-f]{10}/',source['url']):raise ValueError('invalid_gallery_url')
    except ValueError:
        diagnostic(root,'invalid_url',32);raise SystemExit(32)
    if args.strict_exhentai:
        try:raise SystemExit(strict_ex_download(args.url,root,args.cookies,args.verify))
        except (ValueError,OSError,http.cookiejar.LoadError):
            diagnostic(root,'session_required',16);raise SystemExit(16)
    try:
        with cookie_snapshot(args.url) as cookies:
            argv=engine_argv(args.url,root,cookies,args.verify)
            result=subprocess.run(argv,stdin=subprocess.DEVNULL,check=False)
    except (ValueError,OSError,http.cookiejar.LoadError):
        diagnostic(root,'session_required',16);raise SystemExit(16)
    if result.returncode:
        if not (root/'studio-engine-result.json').exists():
            diagnostic(root,'auth_failed' if result.returncode&16 else 'access_required' if result.returncode&8 else 'extraction_failed',result.returncode)
        raise SystemExit(result.returncode)
    if args.verify:
        images=[path for path in root.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES]
        if len(images)!=1 or not is_image(images[0]):
            diagnostic(root,'extraction_failed',4);raise SystemExit(4)
        print('Verified one image page; no archive published')
        return
    count=package_images(root,parse_source(args.url))
    print('Verified image pages packaged:',count)


if __name__=='__main__':main()
