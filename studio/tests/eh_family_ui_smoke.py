"""Full local Studio UI with generated EH/EX records and account status only."""
import os
import mimetypes
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from server import Studio,make_server
from store import Store
from navigation_smoke import FixtureLRR


class GeneratedLogin:
    def call(self,data):
        assert data=={'op':'status'}
        return {'configured':True,'session_import':True,'shared_eh_account':True,'browser_mode':'desktop','desktop_available':True,'active':None,
                'sites':[dict(provider=provider,name=provider,state='saved_unverified',cookie_count=2,session_family='ehentai',
                    target_session_available=provider=='ehentai',login_available=True,last_request=None) for provider in ('ehentai','exhentai')]}


def main():
    # Windows file associations can label .js text/plain; match the NAS fixture.
    mimetypes.add_type('text/javascript','.js')
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-admin'}):
        store=Store(Path(directory)/'catalog.db');store.set_automatic_enabled(False)
        work=store.create_work('Generated shared gallery')
        for host in ('e-hentai.org','exhentai.org'):
            store.upsert_source(work['id'],{'url':'https://'+host+'/g/123/abc/','tags':['artist:generated'],
                'comments':[{'id':'generated','author':'Generated author','posted_at':'generated','text':'Generated preserved comment'}]})
        other=store.create_work('Generated EX-only gallery');store.upsert_source(other['id'],{'url':'https://exhentai.org/g/456/def/'})
        app=Studio(store,FixtureLRR());app.login=GeneratedLogin()
        server=make_server('127.0.0.1',0,app);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        output=Path(__file__).resolve().parents[2]/'work/eh-family-ui';output.mkdir(parents=True,exist_ok=True)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=os.environ.get('STUDIO_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':'generated-admin'},viewport={'width':1440,'height':1000})
                page=context.new_page();errors=[];console=[];requests=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('console',lambda message:console.append(message.text) if message.type=='error' else None)
                page.on('request',lambda request:requests.append(request.url) if '/api/works?' in request.url else None)
                page.goto('http://127.0.0.1:'+str(server.server_port))
                page.locator('[data-filter=ehentai]').click()
                try:expect(page.locator('#grid .card')).to_have_count(2)
                except AssertionError:
                    response=page.request.get('http://127.0.0.1:'+str(server.server_port)+'/api/works?provider=ehentai')
                    value=response.json()
                    print('GENERATED_UI_ERRORS='+repr(errors)+' API_STATUS='+str(response.status)+' API_TOTAL='+str(value.get('total'))+' API_ERROR='+str(value.get('error')),flush=True)
                    print('GENERATED_TOAST='+page.locator('#toast').inner_text(),flush=True)
                    print('GENERATED_CONSOLE='+repr(console)+' REQUESTS='+repr(requests)+' URL='+page.url,flush=True)
                    print('GENERATED_GRID='+page.locator('#grid').inner_html()[:700],flush=True)
                    page.screenshot(path=str(output/'debug.png'))
                    raise
                assert page.locator('[data-filter=exhentai]').count()==0
                assert page.locator('[data-provider=exhentai]').count()==0
                page.locator('#grid .card[data-id="'+work['id']+'"]').click()
                page.wait_for_selector('#connected-source-list .source-row')
                assert page.locator('#connected-source-list .source-row').count()==1
                assert page.locator('#connected-source-list a[href^="https://"]').count()==2
                assert page.locator('#connected-source-list [data-fetch]').count()==2
                assert not page.get_by_text('Generated preserved comment',exact=True).is_visible()
                page.locator('#connected-source-list summary').click()
                assert page.locator('#connected-source-list').inner_text().count('Generated preserved comment')==1
                page.screenshot(path=str(output/'desktop-sources.png'))
                page.locator('#close-detail').click()
                page.locator('#connections-open').click()
                page.wait_for_selector('[data-site-start=ehentai]')
                assert page.locator('[data-site-start=ehentai]').count()==1
                assert page.locator('[data-site-start=exhentai]').count()==0
                assert page.locator('#session-import-provider').input_value()=='ehentai'
                for width,height in ((1440,1000),(390,844)):
                    page.set_viewport_size({'width':width,'height':height})
                    box=page.locator('#connections-dialog').bounding_box()
                    assert box['x']>=0 and box['x']+box['width']<=width+1
                    page.screenshot(path=str(output/('desktop-account.png' if width>400 else 'mobile-account.png')))
                assert not errors,errors
                browser.close()
            print('EH_FAMILY_UI=PASS combined_filter=true one_source_group=true original_urls_and_comments=true one_account_control=true desktop_mobile=true')
        finally:server.shutdown();server.server_close();thread.join(timeout=3)


if __name__=='__main__':main()
