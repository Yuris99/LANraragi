"""Browser reference entry with local synthetic metadata; no external requests."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import Store
from server import Studio,make_server
from playwright.sync_api import sync_playwright


class FixtureLRR:
    def json(self,path,*args):
        if path=='/api/info':return {'version':'synthetic'}
        if path=='/api/archives':return []
        raise ValueError('No external service in this fixture')


def main():
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'reference-smoke'}):
        store=Store(Path(directory)/'studio.db')
        saved=store.create_work('Synthetic saved metadata')
        store.upsert_source(saved['id'],{'url':'https://e-hentai.org/g/123/abcdef/'})
        existing=store.create_work('Synthetic existing file',lrr_id='a'*40)
        store.upsert_source(existing['id'],{'url':'https://nhentai.net/g/999/'})
        app=Studio(store,FixtureLRR());server=make_server('127.0.0.1',0,app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':'reference-smoke'})
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto('http://127.0.0.1:'+str(server.server_port))
                page.locator('#download-open').click();form=page.locator('#download-form')
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
                page.locator('#download-open').click();form.locator('[name=provider]').select_option('hitomi')
                form.locator('[name=reference]').fill('123');page.locator('#download-submit').click()
                page.wait_for_function('() => !document.querySelector("#download-dialog").open')
                assert len(store.jobs())==2
                page.locator('#download-open').click();form.locator('[name=provider]').select_option('nhentai')
                form.locator('[name=reference]').fill('999');page.locator('#download-submit').click()
                page.locator('#detail[open]').wait_for();assert len(store.jobs())==2
                page.locator('#close-detail').click();page.locator('#download-open').click()
                for width in [1440,390]:
                    page.set_viewport_size({'width':width,'height':900})
                    assert page.locator('#download-open').is_visible()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors,errors
                browser.close()
            print(json.dumps(dict(number_entry=True,missing_token_no_queue=True,saved_url_reused=True,
                                  pc_engine_selection=True,site_ids_separate=True,existing_file_no_redownload=True,
                                  desktop_mobile=True,page_errors=errors,live_download_verified=False)))
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
