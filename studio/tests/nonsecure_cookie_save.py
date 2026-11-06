"""Actual Chromium cookie export; generated cookies, no external networking.

Use --https-only to reproduce the previous permission omission. Production
navigation policies remain unchanged; no real site or account is accessed.
"""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from login_service import DesktopBrowser,BrowserActor,make_login_server
from site_sessions import CookieVault,SITES


def main():
    SITES['ehentai']['login']='about:blank'
    observed=[]
    class TraceActor(BrowserActor):
        def call(self,data):
            if data.get('op')=='desktop-session':observed.append(len(data['cookies']))
            return super().call(data)
    with tempfile.TemporaryDirectory() as directory:
        vault=CookieVault(Path(directory)/'sessions');token='generated-'+'a'*48
        browser=DesktopBrowser(vault,bridge_token=token)
        original=browser.extension
        def extension(path):
            original(path)
            script=path/'save.js';text=script.read_text()
            generated="""await chrome.cookies.set({url:'https://e-hentai.org/',domain:'.e-hentai.org',path:'/',name:'fixture_account',value:'generated-account',secure:false});
    await chrome.cookies.set({url:'https://e-hentai.org/',domain:'.e-hentai.org',path:'/',name:'cf_clearance',value:'generated-excluded',secure:true});
    const groups ="""
            script.write_text(text.replace('const groups =',generated))
            if '--https-only' in sys.argv:
                manifest=path/'manifest.json';value=json.loads(manifest.read_text())
                value['host_permissions'].remove('http://*.e-hentai.org/*')
                manifest.write_text(json.dumps(value))
        browser.extension=extension
        actor=TraceActor(vault,browser=browser)
        server=make_login_server('127.0.0.1',8091,actor,token)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        def call(data):
            request=urllib.request.Request('http://127.0.0.1:8091/rpc',data=json.dumps(data).encode(),
                headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
            with urllib.request.urlopen(request,timeout=25) as response:return json.load(response)
        try:
            frame=call({'op':'start','provider':'ehentai'});session=frame['session'];time.sleep(.5)
            assert call({'op':'save','session':session})['saving']
            until=time.monotonic()+5
            while not observed and time.monotonic()<until:time.sleep(.1)
            status=call({'op':'status'})
            state=next(s['state'] for s in status['sites'] if s['provider']=='ehentai')
            if '--https-only' in sys.argv:
                assert observed==[0] and state=='not_saved'
                for _ in range(2):
                    frame=call({'op':'frame','session':session})
                    assert frame['save_error_kind']=='no_account_cookies' and frame['save_error']
            else:
                assert observed==[1] and state=='saved_unverified'
                cookies=list(vault.read('ehentai'))
                assert [(c.name,c.value,c.secure) for c in cookies]==[('fixture_account','generated-account',False)]
            print('NONSECURE_COOKIE_SAVE=PASS mode='+('previous_https_only' if '--https-only' in sys.argv else 'fixed_same_provider')+' challenge_cookie_excluded=true')
        finally:server.shutdown();server.server_close();actor.close()


if __name__=='__main__':main()
