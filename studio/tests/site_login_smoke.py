"""Real Studio, login RPC, two Chromium browsers; synthetic login only.

The NAS browser's requests are fulfilled locally *after* domain checks. Never
uses an actual account, real site document, challenge solver or private media.
"""
import json
import os
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from gallery_engine import cookie_snapshot
from login_service import BrowserActor,make_login_server
from server import Studio,make_server
from site_sessions import CookieVault,LoginClient
from store import Store
from navigation_smoke import FixtureLRR


FORM='''<!doctype html><title>Generated login fixture</title><form action="/synthetic-login" method="post">
<input name="user" style="position:absolute;left:40px;top:60px;width:300px;height:30px">
<input name="password" type="password" style="position:absolute;left:40px;top:120px;width:300px;height:30px">
<button style="position:absolute;left:40px;top:180px;width:200px;height:30px">Generated sign in</button></form>'''


def main():
    with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-studio-admin'}):
        root=Path(temporary);vault=CookieVault(root/'sessions');submitted=[]
        def fixture(route):
            if route.request.method=='POST':
                submitted.append(route.request.post_data)
                assert route.request.post_data=='user=generated-user&password=generated-password'
                route.fulfill(status=200,content_type='text/html',headers={
                    'Set-Cookie':'fixture_session=generated-cookie; Domain=.e-hentai.org; Path=/; Secure; HttpOnly'},
                    body='<title>Generated authenticated page</title><p>Fixture login complete</p>')
            else: route.fulfill(status=200,content_type='text/html',body=FORM)
        actor=BrowserActor(vault,fixture)
        token='generated-only-service-'+'a'*48
        key=root/'service.key';key.write_text(token);key.chmod(0o600)
        gateway=make_login_server('127.0.0.1',0,actor,token)
        gt=threading.Thread(target=gateway.serve_forever,daemon=True);gt.start()
        app=Studio(Store(root/'studio.db'),FixtureLRR(),root/'uploads')
        app.login=LoginClient('http://127.0.0.1:'+str(gateway.server_port),str(key))
        server=make_server('127.0.0.1',0,app);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':'generated-studio-admin'},viewport={'width':1440,'height':1000})
                page=context.new_page();errors=[];requests=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda r:requests.append(r.url))
                page.goto(base)
                page.locator('#connections-open').click()
                page.locator('[data-site-start="ehentai"]').click()
                page.wait_for_function('()=>document.querySelector("#login-screen").naturalWidth===1000')
                def input_at(y,text):
                    page.wait_for_function('()=>!document.querySelector("#login-text").disabled')
                    scale=page.locator('#login-screen').bounding_box()['width']/1000
                    page.locator('#login-screen').click(position={'x':100*scale,'y':y*scale})
                    page.locator('#login-text').fill(text)
                    page.locator('#login-text-form button').click()
                    page.wait_for_function('()=>!document.querySelector("#login-text").disabled')
                    assert page.locator('#login-text').input_value()==''
                input_at(75,'generated-user');input_at(135,'generated-password')
                scale=page.locator('#login-screen').bounding_box()['width']/1000
                page.locator('#login-screen').click(position={'x':100*scale,'y':195*scale})
                page.wait_for_function('()=>!document.querySelector("#login-text").disabled')
                page.wait_for_function('()=>document.querySelector("#login-location").textContent.includes("synthetic-login")')
                page.locator('#login-save').click()
                page.wait_for_function('()=>document.querySelector("#connections-sites").textContent.includes("세션 저장됨")')
                assert submitted==['user=generated-user&password=generated-password']
                assert vault.read('ehentai')[0].value=='generated-cookie'
                assert page.locator('#login-controls').is_hidden()
                assert 'generated-cookie' not in page.content()
                assert 'generated-password' not in page.evaluate('JSON.stringify(localStorage)')
                assert all(url.startswith(base) or url.startswith('data:') for url in requests)
                # Fresh vault/engine process sees the saved provider session, not text from the browser.
                again=CookieVault(vault.root,readonly=True)
                assert again.status('ehentai')['state']=='saved_unverified'
                with patch.dict(os.environ,{'STUDIO_SESSION_DIR':str(vault.root)}):
                    with cookie_snapshot('https://e-hentai.org/g/123/abc123/') as snapshot:
                        assert 'generated-cookie' in Path(snapshot).read_text()
                for width,height in [(1440,1000),(390,844)]:
                    page.set_viewport_size({'width':width,'height':height})
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert page.locator('#connections-dialog').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
                page.on('dialog',lambda dialog:dialog.accept())
                page.locator('[data-site-forget="ehentai"]').click()
                page.wait_for_function('()=>document.querySelector("[data-site-forget=ehentai]").disabled')
                assert not vault.path('ehentai').exists()
                assert not errors,errors
                browser.close()
            print('site_login_browser=passed; real_Studio_RPC_Chromium; explicit_login_save; domain_scoped_cookie; engine_snapshot; forget; desktop_mobile; no_real_site_or_account; nas_changed=false')
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)
            gateway.shutdown();gateway.server_close();gt.join(timeout=3);actor.close()


if __name__=='__main__':main()
