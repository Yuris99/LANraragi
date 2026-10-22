"""Registration automatically connects three generated sites; no button/HTML paste."""
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from playwright.sync_api import sync_playwright
from server import Studio,make_server
from store import Store
from test_auto_sources import H,generated_fetch,generated_index
from metadata_smoke import LRR


def main():
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-auto-ui'}):
        root=Path(directory);store=Store(root/'catalog.db');work=store.create_work('Keep my local title')
        app=Studio(store,LRR(),upload_dir=root/'uploads')
        app.source_transport=lambda:(generated_fetch,generated_index,{})
        server=make_server('127.0.0.1',0,app)
        http=threading.Thread(target=server.serve_forever,daemon=True);http.start()
        worker=threading.Thread(target=app.automatic_source_loop,daemon=True);worker.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':'generated-auto-ui'})
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto('http://127.0.0.1:'+str(server.server_port))
                page.locator('.card').first.click()
                page.get_by_text('출처 연결 · 태그·댓글 가져오기',exact=True).click()
                form=page.locator('#source-form');form.locator('[name=url]').fill(H)
                form.locator('button.primary').click()
                page.locator('#auto-source-state').get_by_text('ExHentai: 연결됨',exact=False).wait_for(timeout=60000)
                page.wait_for_function("() => document.querySelectorAll('.source-header').length===3")
                self_work=store.get_work(work['id'])
                assert {s['provider'] for s in self_work['sources']}=={'ehentai','exhentai','hitomi'}
                assert self_work['title']=='Keep my local title'
                assert page.locator('[data-counterpart]').count()==0
                assert store.automatic_status(work['id'])['state']=='complete'
                page.locator('#close-detail').click()
                page.locator('#providers [data-provider=exhentai]').click()
                page.locator('#total').get_by_text('1 작품',exact=True).wait_for()
                page.locator('#settings-button').click();page.locator('#automatic-source-links').uncheck()
                page.wait_for_timeout(300)
                assert not store.automatic_enabled()
                for width in (390,1440):
                    page.set_viewport_size({'width':width,'height':900})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors,errors
                browser.close()
            print('automatic_source_UI=passed; register_one_URL_only; real_background_loop_and_pacing; EH_EX_Hitomi_connected; no_action_button_or_HTML_paste; title_preserved; Ex_filter; pause_control; mobile_desktop; page_errors=0; generated_only=true; website_verification=false; NAS_changed=false')
        finally:
            app.stop.set();worker.join(timeout=5)
            server.shutdown();server.server_close();http.join()


if __name__=='__main__':main()
