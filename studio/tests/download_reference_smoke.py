"""Browser reference entry with local synthetic metadata; no external requests."""
import json
import hashlib
import mimetypes
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import Store
from server import Studio,make_server
from playwright.sync_api import sync_playwright,expect


class FixtureLRR:
    def json(self,path,*args):
        if path=='/api/info':return {'version':'synthetic'}
        if path=='/api/archives':return []
        if path=='/api/plugins/download':return [{'url_regex':r'https://e-hentai\.org/g/[0-9]+/[0-9a-f]+/'}]
        raise ValueError('No external service in this fixture')


def main():
    mimetypes.add_type('text/javascript','.js')
    output=Path(__file__).resolve().parents[2]/'work/download-toggle';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'reference-smoke'}):
        store=Store(Path(directory)/'studio.db')
        saved=store.create_work('Synthetic saved metadata')
        store.upsert_source(saved['id'],{'url':'https://e-hentai.org/g/123/abcdef/'})
        existing=store.create_work('Synthetic existing file',lrr_id='a'*40)
        store.upsert_source(existing['id'],{'url':'https://hitomi.la/galleries/999.html'})
        app=Studio(store,FixtureLRR());server=make_server('127.0.0.1',0,app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=os.environ.get('STUDIO_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':'reference-smoke'})
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto('http://127.0.0.1:'+str(server.server_port))
                page.locator('#download-open').click();form=page.locator('#download-form')
                expect(form.get_by_role('radio')).to_have_count(2)
                expect(form.get_by_role('radio',name='익헨',exact=True)).to_be_checked()
                expect(form.locator('[name=engine]')).to_have_value('command')
                form.locator('[name=reference]').fill('456');page.locator('#download-submit').click()
                page.locator('#toast').get_by_text('전체 작품 URL',exact=False).wait_for()
                assert store.jobs()==[]
                form.locator('[name=reference]').fill('123');page.locator('#download-preview').click()
                page.locator('#download-resolution').get_by_text('저장된 원본 URL 사용',exact=False).wait_for()
                form.locator('[name=target]').select_option('pc')
                assert form.locator('[name=engine]').input_value()=='command'
                page.locator('#download-submit').click();page.locator('#jobs-view').wait_for(state='visible')
                assert len(store.jobs())==1 and store.jobs()[0]['state']=='queued'
                assert store.jobs()[0]['url']=='https://e-hentai.org/g/123/abcdef/'
                page.locator('#download-open').click();form.get_by_role('radio',name='히토미',exact=True).check()
                form.locator('[name=target]').select_option('nas')
                expect(form.locator('[name=engine]')).to_have_value('command')
                expect(page.locator('#download-method')).to_contain_text('외부 엔진')
                form.locator('[name=target]').select_option('pc')
                form.locator('[name=reference]').fill('123');page.locator('#download-submit').click()
                expect(page.locator('#download-dialog')).not_to_be_visible()
                assert len(store.jobs())==2
                page.locator('#download-open').click();form.get_by_role('radio',name='히토미',exact=True).check()
                form.locator('[name=reference]').fill('999');page.locator('#download-submit').click()
                page.locator('#detail[open]').wait_for();assert len(store.jobs())==2
                page.locator('#close-detail').click();page.locator('#download-open').click()
                ex=store.create_work('Existing EX',lrr_id='b'*40)
                store.upsert_source(ex['id'],{'url':'https://exhentai.org/g/456/abcdef/'})
                form.get_by_role('radio',name='익헨',exact=True).check();form.locator('[name=reference]').fill('X456')
                page.locator('#download-preview').click();expect(page.locator('#download-resolution')).to_contain_text('이미 보관함에 있음')
                page.locator('#download-submit').click();page.locator('#detail[open]').wait_for()
                assert len(store.jobs())==2
                page.locator('#close-detail').click();page.locator('#download-open').click()
                runtime={'adapter':'same-source-1','gallery_engine_sha256':hashlib.sha256((Path(__file__).resolve().parents[1]/'gallery_engine.py').read_bytes()).hexdigest(),'worker_sha256':'a'*64,'gallery_dl_version':'1.32.16','sessions_available':True}
                store.worker_seen('nas',runtime)
                form.get_by_role('radio',name='익헨',exact=True).check();form.locator('[name=target]').select_option('nas')
                expect(form.locator('[name=engine]')).to_have_value('command')
                form.locator('[name=reference]').fill('https://exhentai.org/g/789/0123456789/')
                page.locator('#download-submit').click();expect(page.locator('#download-dialog')).not_to_be_visible()
                assert len(store.jobs())==3 and store.jobs()[0]['url'].startswith('https://exhentai.org/')
                page.locator('#download-open').click()
                for width in [1440,390]:
                    page.set_viewport_size({'width':width,'height':900})
                    assert page.locator('#download-open').is_visible()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    form.get_by_role('radio',name='익헨',exact=True).focus();page.keyboard.press('ArrowRight')
                    expect(form.get_by_role('radio',name='히토미',exact=True)).to_be_checked()
                    expect(form.locator('[name=engine]')).to_have_value('command')
                    page.keyboard.press('ArrowLeft');expect(form.get_by_role('radio',name='익헨',exact=True)).to_be_checked()
                    assert form.locator('.download-source-options span').first.bounding_box()['height']>=44
                    page.screenshot(path=str(output/f'download-toggle-{width}.png'))
                    box=form.locator('[name=reference]').bounding_box()
                    page.mouse.move(box['x']+20,box['y']+10);page.mouse.down();page.mouse.move(2,2);page.mouse.up()
                    expect(page.locator('#download-dialog')).to_be_visible()
                    page.mouse.click(2,2);expect(page.locator('#download-dialog')).not_to_be_visible()
                    assert len(store.jobs())==3
                    page.locator('#download-open').click()
                assert not errors,errors
                browser.close()
            print(json.dumps(dict(number_entry=True,missing_token_no_queue=True,saved_url_reused=True,
                                  pc_engine_selection=True,site_ids_separate=True,existing_file_no_redownload=True,
                                  desktop_mobile=True,page_errors=errors,live_download_verified=False)))
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
