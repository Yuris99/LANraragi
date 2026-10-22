"""Run inside the desktop image: no real site, credentials or security challenge."""
import base64
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import urllib.request
from urllib.parse import parse_qs
import sys
sys.path.insert(0,'/app')
from login_service import BrowserActor,DesktopBrowser,make_login_server
from site_sessions import CookieVault,SITES


def main():
    token='generated-desktop-rpc-'+'b'*48;posted=[]
    class Fixture(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            body=b'<form method="POST"><input autofocus name="user"><input type="password" name="password"><button>Generated login</button></form>'
            self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_POST(self):
            posted.append(parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode()))
            body=b'<h1>Generated account session ready</h1>'
            self.send_response(200)
            self.send_header('Content-Type','text/html')
            self.send_header('Set-Cookie','fixture_account=generated-account; Path=/; HttpOnly')
            self.send_header('Set-Cookie','cf_clearance=generated-never-transfer; Path=/')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    site_server=ThreadingHTTPServer(('127.0.0.1',19877),Fixture)
    threading.Thread(target=site_server.serve_forever,daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        # Test-only provider configuration cannot be selected through RPC.
        SITES['ehentai']={'name':'Generated account','login':'http://127.0.0.1:19877/', 'domains':('127.0.0.1',)}
        vault=CookieVault(Path(tmp)/'sessions');desktop=DesktopBrowser(vault,bridge_token=token)
        actor=BrowserActor(vault,browser=desktop);rpc=make_login_server('127.0.0.1',8091,actor,token)
        threading.Thread(target=rpc.serve_forever,daemon=True).start()
        def call(data):
            request=urllib.request.Request('http://127.0.0.1:8091/rpc',data=json.dumps(data).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=40) as response:return json.load(response)
        def wait(fn,seconds=15):
            until=time.monotonic()+seconds
            while time.monotonic()<until:
                if fn():return
                time.sleep(.2)
            raise AssertionError('Generated desktop condition timed out')
        try:
            assert call({'op':'status'})['desktop_available']
            frame=call({'op':'start','provider':'ehentai'});session=frame['session']
            assert base64.b64decode(frame['image'].split(',',1)[1]).startswith(b'\x89PNG')
            browser=desktop.processes[-1]
            args=Path('/proc/'+str(browser.pid)+'/cmdline').read_bytes().split(b'\0')
            assert not any(b'headless' in a or b'remote-debugging' in a or b'enable-automation' in a for a in args)
            time.sleep(3)
            def op(name,**data):return call({'op':name,'session':session,**data})
            op('text',text='generated-user');op('key',key='Tab');op('text',text='generated-password');op('key',key='Enter')
            wait(lambda:bool(posted))
            assert posted==[{'user':['generated-user'],'password':['generated-password']}],posted
            assert op('save')['saving']
            wait(lambda:op('frame')['session_saved'])
            saved=list(vault.read('ehentai'));assert [(c.name,c.value) for c in saved]==[('fixture_account','generated-account')]
            profile=Path(desktop.directory.name)
            assert not (profile/'frame.png').exists()
            op('cancel');assert not profile.exists()
            assert call({'op':'status'})['active'] is None
            if os.environ.get('STUDIO_DESKTOP_UI_SMOKE')=='1':
                vault.forget('ehentai')
                from playwright.sync_api import sync_playwright
                from server import Studio,make_server
                from store import Store
                from site_sessions import LoginClient
                os.environ['STUDIO_PASSWORD']='generated-admin'
                key=Path(tmp)/'key';key.write_text(token);key.chmod(0o600)
                app=Studio(Store(Path(tmp)/'catalog.db'),object(),Path(tmp)/'uploads')
                app.login=LoginClient('http://127.0.0.1:8091',str(key))
                web=make_server('127.0.0.1',8090,app)
                threading.Thread(target=web.serve_forever,daemon=True).start()
                try:
                    with sync_playwright() as pw:
                        client=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                        context=client.new_context(http_credentials={'username':'admin','password':'generated-admin'},viewport={'width':1440,'height':1000})
                        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                        response=page.goto('http://127.0.0.1:8090')
                        print('generated_UI_HTTP='+str(response.status),flush=True)
                        if not page.locator('#connections-open').count():
                            print('generated_UI_body='+page.locator('body').inner_text()[:500],flush=True)
                        page.locator('#connections-open').click()
                        page.locator('[data-site-start="ehentai"]').click()
                        page.wait_for_function('()=>document.querySelector("#login-screen").naturalWidth===1000')
                        page.wait_for_timeout(3000)
                        def text(value):
                            page.locator('#login-text').fill(value);page.locator('#login-text-form button').click()
                            page.wait_for_function('()=>!document.querySelector("#login-text").disabled')
                        text('generated-ui-user');page.locator('[data-login-key="Tab"]').click()
                        page.wait_for_function('()=>!document.querySelector("#login-text").disabled')
                        text('generated-ui-password');page.locator('[data-login-key="Enter"]').click()
                        wait(lambda:len(posted)==2)
                        page.locator('#login-save').click()
                        page.wait_for_function('()=>document.querySelector("#login-controls").hidden',timeout=25000)
                        page.wait_for_function('()=>document.querySelector("#connections-sites").textContent.includes("세션 저장됨")')
                        assert 'generated-account' not in page.content()
                        assert 'generated-ui-password' not in page.evaluate('JSON.stringify(localStorage)')
                        assert not errors,errors
                        client.close()
                    print('desktop_studio_UI=passed; async_save_confirmation; controls_close; status_refresh; no_secret_in_DOM_or_localStorage',flush=True)
                finally:web.shutdown();web.server_close()
            print('desktop_login=passed; real_Xvfb_Chromium_X11; no_browser_automation_protocol; manual_input; explicit_account_export; challenge_cookie_excluded; private_profile_cleanup; generated_only=true; nas_changed=false',flush=True)
        except Exception:
            if desktop.session and Path('/artifacts').is_dir():
                frame=call({'op':'frame','session':desktop.session})
                Path('/artifacts/desktop.png').write_bytes(base64.b64decode(frame['image'].split(',',1)[1]))
            raise
        finally:
            rpc.shutdown();rpc.server_close();actor.close();site_server.shutdown();site_server.server_close()


if __name__=='__main__':main()
