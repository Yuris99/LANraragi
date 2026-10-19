"""NAS-local, provider-scoped sessions and a fixed login-service client.

No credentials belong in the catalog, export, logs, or browser localStorage.
Saved cookies establish a saved session, never verified site support.
"""
import http.cookiejar
import io
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


SITES = {
    'ehentai': {'name': 'E-Hentai', 'login': 'https://forums.e-hentai.org/index.php?act=Login',
                'domains': ('e-hentai.org',)},
    'exhentai': {'name': 'ExHentai', 'login': 'https://forums.e-hentai.org/index.php?act=Login',
                 'domains': ('e-hentai.org', 'exhentai.org')},
    'nhentai': {'name': 'nHentai', 'login': 'https://nhentai.net/login/',
                'domains': ('nhentai.net',)},
    'hitomi': {'name': 'Hitomi', 'login': None, 'domains': ('hitomi.la',)},
}


def site(name):
    if name not in SITES: raise ValueError('지원하는 사이트를 선택하세요.')
    return SITES[name]


def allowed_domain(name, domain):
    if not isinstance(domain,str): return False
    domain = domain.lstrip('.').lower()
    return any(domain == base or domain.endswith('.' + base) for base in site(name)['domains'])


def session_provider(url):
    host = urllib.parse.urlsplit(url).hostname
    if host == 'exhentai.org': return 'exhentai'
    if host == 'e-hentai.org': return 'ehentai'
    if host == 'nhentai.net': return 'nhentai'
    if host == 'hitomi.la': return 'hitomi'
    raise ValueError('지원하지 않는 세션 출처입니다.')


class CookieVault:
    def __init__(self, root, readonly=False):
        self.root = Path(root)
        if not readonly: self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValueError('세션 전용 디렉터리가 필요합니다.')
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('세션 디렉터리는 실행 계정 전용 0700이어야 합니다.')
        self.readonly = readonly

    def path(self, name):
        site(name)
        return self.root / (name + '.cookies')

    def save(self, name, cookies):
        if self.readonly: raise ValueError('읽기 전용 세션입니다.')
        if not isinstance(cookies, list) or len(cookies) > 500:
            raise ValueError('쿠키 형식을 확인하세요.')
        lines = ['# Netscape HTTP Cookie File']; count = 0
        for c in cookies:
            domain = c.get('domain', '')
            if not allowed_domain(name, domain): continue
            path, key, value = c.get('path', '/'), c.get('name', ''), c.get('value', '')
            if not all(isinstance(v, str) and not any(x in v for x in '\t\r\n\x00') for v in (domain,path,key,value)):
                raise ValueError('잘못된 쿠키 항목입니다.')
            if not key or not path.startswith('/') or len(value) > 16384:
                raise ValueError('잘못된 쿠키 항목입니다.')
            expiry = c.get('expires', -1)
            if not isinstance(expiry,(int,float)) or not math.isfinite(expiry):
                raise ValueError('잘못된 쿠키 만료 시간입니다.')
            if expiry > 0 and expiry <= time.time(): continue
            expiry = max(0, int(expiry))
            prefix = '#HttpOnly_' if c.get('httpOnly') else ''
            lines.append('\t'.join((prefix+domain,'TRUE' if domain.startswith('.') else 'FALSE',path,
                                    'TRUE' if c.get('secure') else 'FALSE',str(expiry) if expiry else '',key,value)))
            count += 1
        if not count: raise ValueError('이 사이트에서 저장할 유효한 세션이 없습니다.')
        raw = ('\n'.join(lines)+'\n').encode()
        if len(raw) > 1024*1024: raise ValueError('세션 크기 제한을 초과했습니다.')
        fd, temporary = tempfile.mkstemp(prefix='.session-', dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(raw); output.flush(); os.fsync(output.fileno())
            os.replace(temporary, self.path(name))
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        return self.status(name)

    def read(self, name):
        fd = os.open(self.path(name), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 1024*1024:
                raise ValueError('세션 파일 권한 또는 크기를 확인하세요.')
            raw = stream.read(1024*1024+1)
        jar = http.cookiejar.MozillaCookieJar()
        jar._really_load(io.StringIO(raw.decode()), str(self.path(name)), True, False)
        # Discard unrelated domains even if a local administrator edited the file.
        cookies = [c for c in jar if allowed_domain(name,c.domain) and not c.is_expired()]
        if not cookies: raise ValueError('세션이 만료됐습니다. 다시 로그인하세요.')
        return cookies

    def status(self, name):
        try: count = len(self.read(name)); state = 'saved_unverified'
        except FileNotFoundError: count = 0; state = 'not_saved'
        except (ValueError, OSError, http.cookiejar.LoadError): count = 0; state = 'unavailable'
        return {'provider':name,'name':site(name)['name'],'state':state,'cookie_count':count,
                'login_available':bool(site(name)['login']),'site_verified':False,
                'download_enabled':name != 'exhentai'}

    def forget(self, name):
        if self.readonly: raise ValueError('읽기 전용 세션입니다.')
        try: self.path(name).unlink()
        except FileNotFoundError: pass
        return self.status(name)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def read_service_token(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>256:
            raise ValueError('로그인 서비스 키 파일 권한을 확인하세요.')
        token=stream.read().strip()
    if len(token)<32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError('로그인 서비스 키 파일을 확인하세요.')
    return token


class LoginClient:
    """An operator-configured endpoint, never a URL selected by a web request."""
    def __init__(self, url=None, token_file=None, config_root=None):
        self.url = (url if url is not None else os.environ.get('STUDIO_LOGIN_URL','')).rstrip('/')
        self.token_file = token_file if token_file is not None else os.environ.get('STUDIO_LOGIN_TOKEN_FILE','')
        self.config_root = Path(config_root) if config_root else None
        self.discovered = False
        self.validate_url()

    def validate_url(self):
        if self.url:
            parsed=urllib.parse.urlsplit(self.url)
            if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                raise ValueError('로그인 서비스의 고정 주소를 확인하세요.')

    def call(self, data):
        # A separate reviewed NAS installer can provision these TWO new files in
        # the existing dedicated data volume. No base Compose/controller changes.
        if (not self.url or self.discovered) and self.config_root:
            path=self.config_root/'.site-login.json'
            try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            except FileNotFoundError:
                if self.discovered:self.url='';self.token_file='';self.discovered=False
            else:
                with os.fdopen(fd) as stream:
                    info=os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>512:
                        raise ValueError('로그인 연결 설정 파일 권한을 확인하세요.')
                    configuration=json.load(stream)
                if configuration!={'schema':1,'url':'http://site-login:8091'}:
                    raise ValueError('로그인 서비스 연결 설정을 확인하세요.')
                self.url=configuration['url'];self.token_file=str(self.config_root/'.site-login-token')
                self.discovered=True
                self.validate_url()
        if not self.url or not self.token_file:
            if data == {'op':'status'}:
                return {'configured':False,'sites':[{'provider':k,'name':v['name'],'state':'not_configured',
                        'login_available':False,'site_verified':False} for k,v in SITES.items()]}
            raise ValueError('NAS 로그인 서비스를 먼저 설치해야 합니다.')
        token=read_service_token(self.token_file)
        request=urllib.request.Request(self.url+'/rpc',data=json.dumps(data).encode(),headers={
            'Content-Type':'application/json','Authorization':'Bearer '+token})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=40) as response:
                raw=response.read(3*1024*1024+1)
                if len(raw)>3*1024*1024: raise ValueError('로그인 화면 크기 제한을 초과했습니다.')
                return json.loads(raw)
        except urllib.error.HTTPError as error:
            # Never return the upstream response or URL: it may include credentials.
            raise ValueError('로그인 서비스가 요청을 처리하지 못했습니다. 연결 상태를 확인하세요.') from None
        except (urllib.error.URLError,OSError,TimeoutError):
            raise ValueError('NAS 로그인 서비스에 연결할 수 없습니다.') from None
