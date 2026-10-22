"""NAS-local, provider-scoped sessions and a fixed login-service client.

No credentials belong in the catalog, export, logs, or browser localStorage.
Saved cookies establish a saved session, never verified site support.
"""
import http.cookiejar
import io
import json
import math
import os
import re
import base64
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


def account_cookie(name):
    """Do not transfer browser-specific security challenge clearance to engines."""
    return isinstance(name,str) and not name.lower().startswith(('cf_', '__cf'))


def session_provider(url):
    host = urllib.parse.urlsplit(url).hostname
    if host == 'exhentai.org': return 'exhentai'
    if host == 'e-hentai.org': return 'ehentai'
    if host == 'nhentai.net': return 'nhentai'
    if host == 'hitomi.la': return 'hitomi'
    raise ValueError('지원하지 않는 세션 출처입니다.')


def source_document(vault,url,offset=0):
    """Fixed read-only metadata routes; account cookies never leave this service."""
    if not isinstance(url,str) or len(url)>2048 or any(c in url for c in '\r\n\x00'):
        raise ValueError('invalid_source_url')
    value=urllib.parse.urlsplit(url)
    if type(offset) is not int or not 0<=offset<=100000:raise ValueError('invalid_index_offset')
    if value.scheme!='https' or value.username or value.password or value.port or value.fragment:
        raise ValueError('invalid_source_url')
    host=value.hostname;index=False
    if host in ('e-hentai.org','exhentai.org'):
        provider='exhentai' if host=='exhentai.org' else 'ehentai'
        search=urllib.parse.parse_qs(value.query,keep_blank_values=True)
        gallery=re.fullmatch(r'/g/[0-9]+/[A-Za-z0-9]+/',value.path) and not value.query
        searching=value.path=='/' and set(search) in ({'f_search'},{'f_search','page'}) and len(search['f_search'])==1 and 0<len(search['f_search'][0])<=150
        if 'page' in search and (len(search['page'])!=1 or not re.fullmatch(r'[0-9]{1,4}',search['page'][0]) or int(search['page'][0])>1000):searching=False
        if not (gallery or searching):raise ValueError('invalid_source_url')
    elif host=='ltn.gold-usergeneratedcontent.net' and not value.query:
        provider='hitomi'
        index=bool(re.fullmatch(r'/artist/[^/]+-all\.nozomi',value.path))
        if not (index or re.fullmatch(r'/galleries/[0-9]+\.js',value.path)):
            raise ValueError('invalid_source_url')
    else:raise ValueError('invalid_source_url')
    if offset and not index:raise ValueError('invalid_index_offset')
    cookies=[]
    if provider!='hitomi':
        try:cookies=vault.read(provider)
        except FileNotFoundError:
            if provider=='exhentai':return {'status':'session_required'}
        except (ValueError,OSError):return {'status':'session_required'}
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    jar=http.cookiejar.CookieJar()
    for cookie in cookies:jar.set_cookie(cookie)
    headers={'User-Agent':'LibraryStudio/0.1','Accept':'text/html,text/javascript,application/json,application/octet-stream'}
    if index:headers['Range']=f'bytes={offset*4}-{offset*4+31}'
    request=urllib.request.Request(url,headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect(),urllib.request.HTTPCookieProcessor(jar)).open(request,timeout=20) as response:
            if index:
                if response.headers.get_content_type().startswith('text/') or response.headers.get_content_type()=='application/json':
                    return {'status':'invalid_response'}
                scope=re.fullmatch(r'bytes ([0-9]+)-([0-9]+)/([0-9]+)',response.headers.get('Content-Range',''))
                if response.status==206 and (not scope or int(scope[1])!=offset*4):return {'status':'invalid_response'}
                if response.status==200 and offset:return {'status':'invalid_response'}
            raw=response.read(32 if index else 1024*1024+1)
        if len(raw)>1024*1024:return {'status':'response_limit'}
        if index:
            if len(raw)%4:return {'status':'invalid_response'}
            if scope and (int(scope[2])-int(scope[1])+1!=len(raw) or int(scope[3])%4):return {'status':'invalid_response'}
            complete=len(raw)<32 or bool(scope and int(scope[2])+1>=int(scope[3]))
            return {'status':'ok','index':base64.b64encode(raw).decode('ascii'),'complete':complete}
        return {'status':'ok','document':raw.decode('utf-8')}
    except urllib.error.HTTPError as error:
        if index and offset and error.code==416:return {'status':'ok','index':'','complete':True}
        return {'status':'access_required' if error.code in (301,302,303,307,308,401,403,429) else 'not_found' if error.code in (404,410) else 'unavailable','http_status':error.code}
    except (OSError,UnicodeError):return {'status':'unavailable'}


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
            if not account_cookie(c.get('name', '')): continue
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
        cookies = [c for c in jar if allowed_domain(name,c.domain) and account_cookie(c.name) and not c.is_expired()]
        if not cookies: raise ValueError('세션이 만료됐습니다. 다시 로그인하세요.')
        return cookies

    def status(self, name):
        try: count = len(self.read(name)); state = 'saved_unverified'
        except FileNotFoundError: count = 0; state = 'not_saved'
        except (ValueError, OSError, http.cookiejar.LoadError): count = 0; state = 'unavailable'
        try:revision=str(self.path(name).stat().st_mtime_ns)
        except OSError:revision=''
        return {'provider':name,'name':site(name)['name'],'state':state,'cookie_count':count,'session_revision':revision,
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
            messages={
                'browser_start_failed':'NAS 브라우저를 시작하지 못했습니다. 브라우저 실행·메모리 상태를 확인해야 합니다.',
                'login_site_timeout':'NAS에서 로그인 사이트의 응답을 기다리다 시간 제한에 도달했습니다.',
                'login_site_unreachable':'NAS 브라우저가 로그인 사이트에 연결하지 못했습니다. 사이트 접근 또는 페이지 이동 제한을 확인해야 합니다.',
                'login_preview_failed':'로그인 페이지는 열었지만 NAS 브라우저 화면을 생성하지 못했습니다.',
            }
            try:
                raw=error.read(1025)
                code=json.loads(raw).get('error') if len(raw)<=1024 else None
                message=messages.get(code) if isinstance(code,str) else None
            except (ValueError,AttributeError,OSError):message=None
            if message:raise ValueError(message) from None
            raise ValueError('로그인 서비스가 요청을 처리하지 못했습니다. 연결 상태를 확인하세요.') from None
        except (urllib.error.URLError,OSError,TimeoutError):
            raise ValueError('NAS 로그인 서비스에 연결할 수 없습니다.') from None
