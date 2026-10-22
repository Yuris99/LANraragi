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
import shutil
import signal
import subprocess
import tempfile
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
        return {'configured':True,'source_documents':True,'sites':[self.vault.status(k) for k in SITES],
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


class DesktopBrowser(LoginBrowser):
    """Ordinary visible Chromium, manually controlled through X11 only.

    No browser debugging port, browser automation framework or challenge solver.
    A small extension reads provider account cookies only after explicit Save.
    The temporary browser profile, display and extension are destroyed on close.
    """
    def __init__(self, vault, bridge_token=None, bridge_url='http://127.0.0.1:8091/rpc'):
        super().__init__(vault)
        self.bridge_token=bridge_token;self.bridge_url=bridge_url
        self.processes=[];self.directory=None;self.env=None;self.window=None
        self.saving_until=0;self.saved=False

    def available(self):
        return all(shutil.which(tool) for tool in ('Xvfb','xauth','xdotool','scrot')) and bool(shutil.which(os.environ.get('STUDIO_CHROMIUM','chromium')))

    def run(self, args, **kwargs):
        return subprocess.run(args,env=self.env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                              timeout=kwargs.pop('timeout',5),check=True,**kwargs).stdout

    def status(self):
        value=super().status();value.update(browser_mode='desktop',desktop_available=self.available())
        return value

    def close(self):
        for process in reversed(self.processes):
            if process.poll() is None:
                try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=3)
                except (ProcessLookupError,subprocess.TimeoutExpired):
                    try:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=2)
                    except (ProcessLookupError,subprocess.TimeoutExpired):pass
        self.processes=[]
        if self.directory:self.directory.cleanup()
        self.directory=self.env=self.window=None
        self.provider=self.session=None;self.deadline=0;self.saving_until=0;self.saved=False

    def extension(self, directory):
        token=self.bridge_token or read_service_token(os.environ['STUDIO_LOGIN_TOKEN_FILE'])
        config={'token':token,'url':self.bridge_url,'session':self.session,'domains':list(site(self.provider)['domains'])}
        manifest={'manifest_version':3,'name':'Studio account session save','version':'1.0',
                  'permissions':['cookies'],'host_permissions':['https://*.e-hentai.org/*','https://exhentai.org/*',
                  'https://*.nhentai.net/*','http://127.0.0.1/*'],
                  'background':{'service_worker':'save.js'},
                  'commands':{'save-account-session':{'suggested_key':{'default':'Alt+Shift+S'},'description':'Save this provider account session to Studio'}}}
        # Domain permissions are generated from the fixed server configuration.
        # Fixture domains exist only in isolated tests, never in a web argument.
        manifest['host_permissions']=[('http://'+d+'/*' if d in ('127.0.0.1','localhost') else 'https://*.'+d+'/*') for d in config['domains']]+['http://127.0.0.1/*']
        (directory/'manifest.json').write_text(json.dumps(manifest))
        script='const config='+json.dumps(config)+';\n'+'''chrome.commands.onCommand.addListener(async command => {
  if (command !== 'save-account-session') return;
  try {
    const groups = await Promise.all(config.domains.map(domain => chrome.cookies.getAll({domain})));
    const unique = new Map();
    for (const c of groups.flat()) {
      if (/^(?:cf_|__cf)/i.test(c.name)) continue;
      unique.set(c.domain+'\\n'+c.path+'\\n'+c.name, {
        domain:c.domain, path:c.path, name:c.name, value:c.value,
        secure:c.secure, httpOnly:c.httpOnly, expires:c.expirationDate ?? -1
      });
    }
    await fetch(config.url,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+config.token},
      body:JSON.stringify({op:'desktop-session',session:config.session,cookies:[...unique.values()]})});
  } catch (_) { /* The Studio Save operation times out visibly; no secret logs. */ }
});'''
        (directory/'save.js').write_text(script)
        for path in directory.iterdir():path.chmod(0o600)

    def start(self, provider):
        self.expire();configuration=site(provider)
        if not configuration['login']:raise ValueError('이 출처에는 지원하는 로그인 화면이 없습니다.')
        if self.session:raise ValueError('열린 로그인 창을 먼저 저장하거나 취소하세요.')
        if not self.available():raise LoginFailure('browser_start_failed')
        self.provider=provider;self.session=secrets.token_hex(16);self.deadline=time.monotonic()+600
        try:
            self.directory=tempfile.TemporaryDirectory(prefix='studio-desktop-')
            root=Path(self.directory.name);root.chmod(0o700)
            self.env={**os.environ,'DISPLAY':':99','XAUTHORITY':str(root/'display.auth'),'HOME':str(root)}
            self.run(['xauth','-f',self.env['XAUTHORITY'],'add',':99','.',secrets.token_hex(16)])
            os.chmod(self.env['XAUTHORITY'],0o600)
            display=subprocess.Popen(['Xvfb',':99','-screen','0','1000x700x24','-nolisten','tcp','-auth',self.env['XAUTHORITY']],
                env=self.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            self.processes.append(display)
            extension=root/'extension';extension.mkdir(mode=0o700);self.extension(extension)
            args=[os.environ.get('STUDIO_CHROMIUM','/usr/bin/chromium'),'--no-sandbox','--disable-dev-shm-usage',
                  '--no-first-run','--no-default-browser-check','--window-size=1000,700','--start-maximized',
                  '--user-data-dir='+str(root/'profile'),'--disable-extensions-except='+str(extension),
                  '--load-extension='+str(extension)]
            proxy=os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
            if proxy:args.append('--proxy-server='+proxy)
            args.append(configuration['login'])
            browser=subprocess.Popen(args,env=self.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            self.processes.append(browser)
            until=time.monotonic()+15
            while time.monotonic()<until:
                if display.poll() is not None or browser.poll() is not None:raise RuntimeError('desktop exited')
                try:
                    windows=self.run(['xdotool','search','--onlyvisible','--class','chromium'],timeout=1).decode().splitlines()
                    if windows:
                        self.window=next(w for w in windows if w.isdigit())
                        self.run(['xdotool','windowfocus','--sync',self.window])
                        return self.frame()
                except (subprocess.SubprocessError,StopIteration):pass
                time.sleep(.15)
            raise RuntimeError('desktop window unavailable')
        except Exception:
            self.close();raise LoginFailure('browser_start_failed') from None

    def frame(self):
        # scrot writes only into this disposable private profile; remove each
        # image immediately. It never enters a media volume, export or log.
        path=Path(self.directory.name)/'frame.png'
        try:
            self.run(['scrot','--overwrite',str(path)])
            with path.open('rb') as stream:raw=stream.read(2*1024*1024+1)
            if len(raw)>2*1024*1024 or not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('preview')
        except Exception:raise LoginFailure('login_preview_failed') from None
        finally:path.unlink(missing_ok=True)
        error=bool(self.saving_until and time.monotonic()>self.saving_until and not self.saved)
        if error:self.saving_until=0
        return {'session':self.session,'provider':self.provider,'width':1000,'height':700,
                'location':site(self.provider)['name']+' · 일반 NAS 브라우저 (주소는 화면의 주소창에서 확인)',
                'restricted_request':False,'response_status':None,'browser_mode':'desktop',
                'saving':bool(self.saving_until and not self.saved),'save_error':error,'session_saved':self.saved,
                'image':'data:image/png;base64,'+base64.b64encode(raw).decode()}

    def call(self, data):
        if not isinstance(data,dict):raise ValueError('잘못된 로그인 요청입니다.')
        op=data.get('op')
        if op in ('status','start','forget'):return super().call(data)
        schemas={'frame':set(),'cancel':set(),'save':set(),'visit':set(),'click':{'x','y'},
                 'text':{'text'},'key':{'key'},'scroll':{'delta'},'desktop-session':{'cookies'}}
        if op not in schemas or set(data)!=(schemas[op]|{'op','session'}):raise ValueError('잘못된 로그인 요청입니다.')
        self.expire()
        if not self.session or not secrets.compare_digest(str(data['session']),self.session):raise ValueError('로그인 창이 만료됐습니다.')
        if op=='cancel':self.close();return {'closed':True}
        if op=='frame':return self.frame()
        if op=='desktop-session':
            if not self.saving_until or time.monotonic()>self.saving_until:raise ValueError('먼저 세션 저장을 선택하세요.')
            cookies=data['cookies']
            if not isinstance(cookies,list) or any(not isinstance(c,dict) for c in cookies):raise ValueError('쿠키 형식을 확인하세요.')
            result=self.vault.save(self.provider,cookies);self.saved=True;self.saving_until=0
            return result
        if op=='save':
            self.saving_until=time.monotonic()+15;self.saved=False
            self.run(['xdotool','key','--clearmodifiers','alt+shift+s'])
            return {'saving':True}
        if op=='click':
            if any(type(data[k]) not in (int,float) or not math.isfinite(data[k]) for k in ('x','y')) or not (0<=data['x']<1000 and 0<=data['y']<700):raise ValueError('화면 안을 선택하세요.')
            self.run(['xdotool','mousemove','--sync',str(int(data['x'])),str(int(data['y'])),'click','1'])
        elif op=='text':
            text=data['text']
            if not isinstance(text,str) or not 1<=len(text)<=2000 or '\x00' in text:raise ValueError('입력 문자를 확인하세요.')
            self.run(['xdotool','type','--clearmodifiers','--file','-'],input=text.encode())
        elif op=='key':
            if data['key'] not in KEYS:raise ValueError('지원하지 않는 키입니다.')
            key={'Enter':'Return','Backspace':'BackSpace','ArrowLeft':'Left','ArrowRight':'Right','ArrowUp':'Up','ArrowDown':'Down'}.get(data['key'],data['key'])
            self.run(['xdotool','key','--clearmodifiers',key])
        elif op=='scroll':
            if type(data['delta']) is not int or not -700<=data['delta']<=700:raise ValueError('스크롤 범위를 확인하세요.')
            self.run(['xdotool','click','--repeat',str(max(1,abs(data['delta'])//100)),'4' if data['delta']<0 else '5'])
        elif op=='visit':
            url={'ehentai':'https://e-hentai.org/','exhentai':'https://exhentai.org/','nhentai':'https://nhentai.net/'}[self.provider]
            self.run(['xdotool','key','--clearmodifiers','ctrl+l'])
            self.run(['xdotool','type','--clearmodifiers','--file','-'],input=url.encode())
            self.run(['xdotool','key','Return'])
        return {'accepted':True}


class BrowserActor:
    """Playwright objects stay on one thread; no parallel login windows."""
    def __init__(self, vault, route_fixture=None, browser=None):
        self.executor=ThreadPoolExecutor(max_workers=1)
        # Production browser is an ordinary desktop process, without CDP/WebDriver.
        # Playwright remains available only for explicit generated-route fixtures.
        self.browser=browser or (LoginBrowser(vault,route_fixture) if route_fixture else DesktopBrowser(vault))
        self.stop=threading.Event()
        self.document_lock=threading.Lock()
        self.reaper=threading.Thread(target=self.reap,daemon=True); self.reaper.start()
    def call(self,data):
        if isinstance(data,dict) and data.get('op')=='source-document':
            if set(data) not in ({'op','url'},{'op','url','offset'}):raise ValueError('invalid_source_document')
            from site_sessions import source_document
            if not self.document_lock.acquire(blocking=False):return {'status':'busy'}
            try:return source_document(self.browser.vault,data['url'],data.get('offset',0))
            finally:self.document_lock.release()
        return self.executor.submit(self.browser.call,data).result(timeout=40)
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
                if not 0<length<=262144: raise ValueError('요청 크기를 확인하세요.')
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
