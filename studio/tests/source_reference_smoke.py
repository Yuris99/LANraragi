"""Existing-work number/code linking in real desktop/mobile UI; no downloads."""
import hashlib
import mimetypes
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from store import Store
from server import Studio,make_server
from navigation_smoke import FixtureLRR


def main():
    mimetypes.add_type('text/javascript','.js')
    output=Path(__file__).resolve().parents[2]/'work/source-number-link';output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ['STUDIO_TEST_CHROMIUM'],headless=True,args=['--no-sandbox'])
        for width in [1440,390]:
            with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-source-link'}):
                store=Store(Path(temporary)/'studio.db');store.set_automatic_enabled(False)
                work=store.create_work('Generated original title',artist='Generated original artist',lrr_id='a'*40,pages=7,tags=['language:korean'])
                store.progress(work['id'],3);before=store.get_work(work['id'])
                lrr=FixtureLRR();image_hashes={k:hashlib.sha256(v).hexdigest() for k,v in lrr.images.items()}
                app=Studio(store,lrr);lookups=[]
                def search(url):
                    lookups.append(url);assert url=='https://exhentai.org/?f_search=gid%3A987654'
                    return '<a href="https://exhentai.org/g/987654/abcdef0123/">Generated exact gallery</a><a href="https://e-hentai.org/g/987654/aaaaaaaaaa/">Other host</a>'
                app.source_transport=lambda:(search,None,{})
                server=make_server('127.0.0.1',0,app);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    context=browser.new_context(http_credentials={'username':'admin','password':'generated-source-link'},viewport={'width':width,'height':960},is_mobile=width<500,has_touch=width<500,reduced_motion='reduce')
                    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto('http://127.0.0.1:'+str(server.server_port)+'/manga/L1');expect(page.locator('#detail')).to_be_visible()
                    form=page.locator('#source-form');field=form.locator('[name=url]');submit=form.get_by_role('button',name='현재 작품에 출처 연결',exact=True)
                    form.get_by_role('radio',name='Hitomi',exact=True).check();field.fill('123456')
                    expect(field).to_have_attribute('type','text');submit.click()
                    expect(page.locator('#connected-source-list a[href="https://hitomi.la/galleries/123456.html"]')).to_be_visible()
                    assert len(store.get_work(work['id'])['sources'])==1
                    form.get_by_role('radio',name='ExHentai',exact=True).check();field.fill('987654')
                    page.screenshot(path=str(output/f'source-number-form-{width}.png'))
                    assert form.evaluate('(el)=>el.scrollWidth<=el.clientWidth')
                    submit.click();expect(page.locator('#connected-source-list a[href="https://exhentai.org/g/987654/abcdef0123/"]')).to_be_visible()
                    assert len(store.get_work(work['id'])['sources'])==2
                    field.fill('987654/abcdef0123');submit.click();expect(page.locator('#source-form button[type=submit]')).to_be_enabled()
                    assert len(store.get_work(work['id'])['sources'])==2 and len(lookups)==1
                    field.fill('X987654');submit.click();expect(page.locator('#source-form button[type=submit]')).to_be_enabled()
                    assert len(store.get_work(work['id'])['sources'])==2
                    form.get_by_role('radio',name='Hitomi',exact=True).check()
                    field.fill('https://e-hentai.org/g/987654/abcdef0123/')
                    expect(form.get_by_role('radio',name='ExHentai',exact=True)).to_be_checked()
                    submit.click();expect(page.locator('#connected-source-list a[href="https://e-hentai.org/g/987654/abcdef0123/"]')).to_be_visible()
                    after=store.get_work(work['id'])
                    for key in ('id','lrr_id','title','artist','pages','bytes','progress','last_read','tags'):assert after[key]==before[key],key
                    assert store.jobs()==[] and store.list_works()['total']==1
                    assert {k:hashlib.sha256(v).hexdigest() for k,v in lrr.images.items()}==image_hashes
                    assert all(not path.endswith('/download') for path in lrr.calls)
                    page.screenshot(path=str(output/f'source-number-connected-{width}.png'))
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert not errors,errors
                    context.close()
                finally:server.shutdown();server.server_close();thread.join()
        browser.close()
    print('SOURCE_REFERENCE=PASS desktop/mobile Hitomi number, new EX number lookup, EX code, saved EX number, pasted URL auto toggle, current work/file/title/progress preserved, download_jobs=0')


if __name__=='__main__':main()
