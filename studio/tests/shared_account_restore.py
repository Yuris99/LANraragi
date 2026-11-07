"""Ordinary Chromium restores one saved family; idle wake never rolls it back."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import urllib.request

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from login_service import DesktopBrowser,BrowserActor,make_login_server
from site_sessions import CookieVault,SITES
from test_eh_family import account


def main():
    SITES['ehentai']['login']='about:blank'
    with tempfile.TemporaryDirectory() as directory:
        vault=CookieVault(Path(directory)/'sessions')
        vault.save('ehentai',account('.e-hentai.org')+account('.exhentai.org')+
            [dict(domain='.e-hentai.org',name='cf_clearance',value='generated-excluded')])
        token='generated-'+'a'*48;browser=DesktopBrowser(vault,bridge_token=token)
        original=browser.extension
        def extension(path):
            original(path)
            manifest=path/'manifest.json';value=json.loads(manifest.read_text())
            value['commands']['fixture-update']={'suggested_key':{'default':'Ctrl+Shift+Y'},'description':'Generated test only'}
            manifest.write_text(json.dumps(value))
            with (path/'save.js').open('a') as output:
                output.write("""
chrome.commands.onCommand.addListener(async command => {
 if (command !== 'fixture-update') return;
 await Promise.all(config.domains.map(domain=>chrome.cookies.set({url:'https://'+domain+'/',domain:'.'+domain,path:'/',name:'ipb_member_id',value:'generated-new-account',secure:false})));
});
""")
        browser.extension=extension
        actor=BrowserActor(vault,browser=browser);server=make_login_server('127.0.0.1',8091,actor,token)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        def call(data):
            request=urllib.request.Request('http://127.0.0.1:8091/rpc',data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
            with urllib.request.urlopen(request,timeout=25) as response:return json.load(response)
        try:
            frame=call({'op':'start','provider':'ehentai'});session=frame['session'];time.sleep(.5)
            def save():
                assert call({'op':'save','session':session})['saving']
                until=time.monotonic()+5
                while time.monotonic()<until:
                    frame=call({'op':'frame','session':session})
                    if frame.get('session_saved'):return
                    assert not frame.get('save_error');time.sleep(.1)
                raise AssertionError('Generated save did not complete')
            save()
            assert len(vault.read('ehentai'))==4
            assert {c.domain for c in vault.read('ehentai')}=={'.e-hentai.org','.exhentai.org'}
            browser.run(['xdotool','key','--clearmodifiers','ctrl+shift+y']);time.sleep(.4)
            # Extension idle shutdown must not cause startup restoration to undo
            # a later user login in this same profile.
            time.sleep(32)
            save()
            assert {c.value for c in vault.read('exhentai') if c.name=='ipb_member_id'}=={'generated-new-account'}
            assert all(c.name!='cf_clearance' for c in vault.read('ehentai'))
            print('SHARED_ACCOUNT_RESTORE=PASS both_original_domains=true challenge_cookie_excluded=true idle_wake_preserves_later_login=true')
        finally:server.shutdown();server.server_close();actor.close()


if __name__=='__main__':main()
