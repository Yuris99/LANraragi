"""Optional NAS-local interactive login browser. Never expose its port publicly.

The Studio admin proxies a small RPC interface. Browser actions are explicit user
input; there is no CAPTCHA solving, stealth mode, arbitrary URL or auto-login.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

from site_sessions import CookieVault, SITES, allowed_domain, site, read_service_token


KEYS = {'Tab','Enter','Backspace','Delete','Escape','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'}
LOGIN_ERRORS = {'browser_start_failed','login_site_timeout','login_site_unreachable','login_preview_failed'}


class LoginFailure(ValueError):
    pass


class LoginBrowser:
    def __init__(self, vault, route_fixture=None):
        self.vault=vault; self.route_fixture=route_fixture
        self.pw=None; self.browser=None; self.context=None; self.page=None
        self.provider=None; self.session=None; self.deadline=0; self.denied=False
        self.blocked_navigation=False; self.response_status=None

    def close(self):
        try:
            if self.browser: self.browser.close()
        finally:
            if self.pw: self.pw.stop()
            self.pw=self.browser=self.context=self.page=None
            self.provider=self.session=None; self.deadline=0

    def expire(self):
        if self.session and time.monotonic()>=self.deadline: self.close()

    def status(self):
        self.expire()
        return {'configured':True,'sites':[self.vault.status(k) for k in SITES],
                'active':{'provider':self.provider,'session':self.session} if self.session else None}

    def route(self, route):
        parsed=urlsplit(route.request.url)
        navigation=route.request.is_navigation_request()
        main_navigation=navigation and route.request.frame==self.page.main_frame if self.page else navigation
        # Official verification dependency, not a destination or a bypass.
        # Keep top-level browsing restricted to the selected site's family.
        current=urlsplit(self.page.url) if self.page else None
        verification=(parsed.hostname=='challenges.cloudflare.com' and not main_navigation
                      and current is not None and current.scheme=='https'
                      and allowed_domain(self.provider,current.hostname or ''))
        if parsed.scheme != 'https' or parsed.port not in (None,443) or parsed.username or parsed.password or not (allowed_domain(self.provider,parsed.hostname or '') or verification):
            self.denied=True
            try:
                if main_navigation:
                    self.blocked_navigation=True
            except AttributeError: pass
            route.abort(); return
        if self.route_fixture: self.route_fixture(route)
        else: route.continue_()

    def start(self, provider):
        self.expire(); configuration=site(provider)
        if not configuration['login']: raise ValueError('이 출처에는 지원하는 로그인 화면이 없습니다.')
        if self.session: raise ValueError('열린 로그인 창을 먼저 저장하거나 취소하세요.')
        from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
        self.provider=provider; self.session=secrets.token_hex(16); self.denied=False
        self.blocked_navigation=False; self.response_status=None
        self.deadline=time.monotonic()+600
        phase='browser'
        try:
            self.pw=sync_playwright().start()
            proxy=os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
            launch={'executable_path':os.environ.get('STUDIO_CHROMIUM','/usr/bin/chromium'),
                    'headless':True,'timeout':15000,'args':['--no-sandbox','--disable-dev-shm-usage']}
            if proxy: launch['proxy']={'server':proxy}
            self.browser=self.pw.chromium.launch(**launch)
            self.context=self.browser.new_context(viewport={'width':1000,'height':700},
                accept_downloads=False,service_workers='block')
            # Never inherit a normal user's browser profile or cached credentials.
            try:
                cookies=self.vault.read(provider)
                restored=[]
                for c in cookies:
                    value={'name':c.name,'value':c.value,'domain':c.domain,'path':c.path,'secure':c.secure,
                           'httpOnly':c.has_nonstandard_attr('HTTPOnly')}
                    if c.expires: value['expires']=c.expires
                    restored.append(value)
                self.context.add_cookies(restored)
            except (FileNotFoundError,ValueError): pass
            self.context.route('**/*',self.route)
            self.context.route_web_socket('**/*',lambda websocket:websocket.close())
            self.page=self.context.new_page()
            self.context.on('page',lambda page:page.close() if page!=self.page else None)
            phase='site'
            response=self.page.goto(configuration['login'],wait_until='domcontentloaded',timeout=15000)
            self.response_status=response.status if response else None
            phase='preview'
            return self.frame()
        except Exception as error:
            code=('browser_start_failed' if phase=='browser' else 'login_preview_failed' if phase=='preview'
                  else 'login_site_timeout' if isinstance(error,BrowserTimeout) else 'login_site_unreachable')
            self.close()
            raise LoginFailure(code) from None

    def frame(self):
        parsed=urlsplit(self.page.url)
        # Strip queries/fragments that can contain one-time authentication values.
        return {'session':self.session,'provider':self.provider,'width':1000,'height':700,
                'location':parsed.scheme+'://'+parsed.netloc+parsed.path,
                'restricted_request':self.denied,
                'blocked_navigation':self.blocked_navigation,'response_status':self.response_status,
                'image':'data:image/png;base64,'+base64.b64encode(self.page.screenshot(type='png',timeout=5000)).decode()}

    def call(self, data):
        if not isinstance(data,dict): raise ValueError('잘못된 로그인 요청입니다.')
        op=data.get('op'); schemas={
            'status':set(),'start':{'provider'},'frame':{'session'},'cancel':{'session'},
            'save':{'session'},'forget':{'provider'},'click':{'session','x','y'},
            'text':{'session','text'},'key':{'session','key'},'scroll':{'session','delta'},'visit':{'session'}}
        if op not in schemas or set(data)!=(schemas[op]|{'op'}): raise ValueError('잘못된 로그인 요청입니다.')
        self.expire()
        if op=='status': return self.status()
        if op=='start': return self.start(data['provider'])
        if op=='forget':
            site(data['provider'])
            if self.provider==data['provider']: self.close()
            return self.vault.forget(data['provider'])
        if not self.session or not secrets.compare_digest(str(data['session']),self.session):
            raise ValueError('로그인 창이 만료됐거나 다른 창에서 변경됐습니다.')
        if op=='cancel': self.close(); return {'closed':True}
        if op=='save':
            result=self.vault.save(self.provider,self.context.cookies())
            self.close(); return result
        if op=='frame': return self.frame()
        if op=='visit':
            url={'ehentai':'https://e-hentai.org/','exhentai':'https://exhentai.org/',
                 'nhentai':'https://nhentai.net/'}[self.provider]
            response=self.page.goto(url,wait_until='domcontentloaded',timeout=15000)
            self.response_status=response.status if response else None
            return self.frame()
        if op=='click':
            if any(type(data[k]) not in (float,int) or not math.isfinite(data[k]) for k in ('x','y')) or not (0<=data['x']<1000 and 0<=data['y']<700):
                raise ValueError('로그인 화면 안을 선택하세요.')
            self.page.mouse.click(data['x'],data['y'])
        elif op=='text':
            if not isinstance(data['text'],str) or not 1<=len(data['text'])<=2000 or '\x00' in data['text']:
                raise ValueError('입력할 문자를 확인하세요.')
            self.page.keyboard.insert_text(data['text'])
        elif op=='key':
            if data['key'] not in KEYS: raise ValueError('지원하지 않는 키입니다.')
            self.page.keyboard.press(data['key'])
        elif op=='scroll':
            if type(data['delta']) is not int or not -700<=data['delta']<=700: raise ValueError('잘못된 스크롤입니다.')
            self.page.mouse.wheel(0,data['delta'])
        return {'accepted':True}


class BrowserActor:
    """Playwright objects stay on one thread; no parallel login windows."""
    def __init__(self, vault, route_fixture=None):
        self.executor=ThreadPoolExecutor(max_workers=1)
        self.browser=LoginBrowser(vault,route_fixture)
        self.stop=threading.Event()
        self.reaper=threading.Thread(target=self.reap,daemon=True); self.reaper.start()
    def call(self,data): return self.executor.submit(self.browser.call,data).result(timeout=40)
    def reap(self):
        while not self.stop.wait(15):
            try: self.executor.submit(self.browser.expire).result(timeout=40)
            except Exception: pass
    def close(self):
        self.stop.set();self.reaper.join(timeout=1)
        self.executor.submit(self.browser.close).result(timeout=40)
        self.executor.shutdown()


def make_login_server(host,port,actor,token):
    if len(token)<32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError('전용 서비스 키가 필요합니다.')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def respond(self,value,status=200):
            raw=json.dumps(value).encode()
            self.send_response(status); self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            self.connection.settimeout(45)
            if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                return self.respond({'error':'unauthorized'},401)
            if self.path!='/rpc': return self.respond({'error':'not_found'},404)
            if self.headers.get('Transfer-Encoding') or self.headers.get_content_type()!='application/json':
                return self.respond({'error':'invalid_request'},400)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384: raise ValueError('요청 크기를 확인하세요.')
                data=json.loads(self.rfile.read(length));result=actor.call(data)
                self.respond(result)
            except LoginFailure as error:
                self.respond({'error':str(error) if str(error) in LOGIN_ERRORS else 'login_browser_unavailable'},503)
            except ValueError:
                self.respond({'error':'invalid_login_operation'},400)
            except Exception:
                self.respond({'error':'login_browser_unavailable'},503)
    return ThreadingHTTPServer((host,port),Handler)


def main():
    os.umask(0o077)
    root=Path(os.environ.get('STUDIO_SESSION_DIR','/sessions'))
    vault=CookieVault(root)
    # LoginClient validates the same key's file mode; never pass keys as argv.
    token=read_service_token(os.environ['STUDIO_LOGIN_TOKEN_FILE'])
    actor=BrowserActor(vault)
    server=make_login_server('0.0.0.0',8091,actor,token)
    try: server.serve_forever()
    finally: server.server_close();actor.close()


if __name__=='__main__': main()
