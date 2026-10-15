"""Optional synthetic-only real LANraragi + Chromium smoke test.

Run after starting an isolated LANraragi with a three-page synthetic CBZ:
python studio/tests/browser_smoke.py
Requires Playwright and a Chromium executable; never point at a personal library.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import LRR, Studio, make_server
from store import Store
from playwright.sync_api import sync_playwright


def main():
    root=Path(__file__).resolve().parents[1]
    # Generated development credentials stay local and are never printed.
    for line in (root/'.env').read_text().splitlines():
        if '=' in line:
            key,value=line.split('=',1)
            if key in ('LRR_API_KEY','STUDIO_PASSWORD','STUDIO_WORKER_TOKEN'):os.environ[key]=value
    (root/'test-results').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root/'test-results') as temp:
        app=Studio(Store(Path(temp)/'smoke.db'),LRR('http://127.0.0.1:43121',os.environ['LRR_API_KEY']))
        for attempt in range(30):
            try:
                app.sync()
                works=app.store.list_works()['items']
                if works:break
            except Exception:
                if attempt==29:raise
            time.sleep(1)
        assert len(works)==1 and works[0]['title'].startswith('Synthetic'), 'Expected isolated synthetic library only'
        server=make_server('127.0.0.1',0,app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':os.environ['STUDIO_PASSWORD']},accept_downloads=True)
                page=context.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto('http://127.0.0.1:'+str(server.server_port))
                page.locator('.card').wait_for()
                page.locator('.card').click()
                page.locator('#read-work').click()
                page.locator('#reader[open]').wait_for(state='visible')
                page.wait_for_function("() => document.querySelector('#reader-image').naturalWidth > 0")
                page.locator('#reader-next').click()
                page.wait_for_function("() => document.querySelector('#reader-position').textContent === '2 / 3'")
                page.wait_for_function("() => document.querySelector('#reader-image').naturalWidth > 0")
                for _ in range(30):
                    if app.store.get_work(works[0]['id'])['progress']==2:break
                    page.wait_for_timeout(100)
                assert app.store.get_work(works[0]['id'])['progress']==2
                page.locator('#close-reader').click()
                page.locator('#read-work').click()
                page.locator('#reader[open]').wait_for(state='visible')
                page.wait_for_function("() => document.querySelector('#reader-position').textContent === '2 / 3'")
                page.locator('#close-reader').click()
                with page.expect_download() as info:page.locator('#detail a[download]').click()
                download=info.value
                actual=hashlib.sha256(Path(download.path()).read_bytes()).hexdigest()
                expected=hashlib.sha256((root/'data/library/Synthetic Studio Book.cbz').read_bytes()).hexdigest()
                assert actual==expected
                for width,height in [(1440,1000),(390,844)]:
                    page.set_viewport_size({'width':width,'height':height})
                    page.locator('#close-detail').click()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
                    screenshots=root/'test-results'/'browser-smoke'
                    screenshots.mkdir(exist_ok=True)
                    page.screenshot(path=str(screenshots/f'library-{width}.png'))
                    image=page.locator('.card img')
                    page.wait_for_function("() => document.querySelector('.card img').naturalWidth > 0")
                    page.locator('.card').click()
                assert not errors, errors
                browser.close()
            print(json.dumps({'lanraragi_version':app.lrr.json('/api/info').get('version'),'synthetic_works':len(works),'reader_pages':3,'progress':2,'download_sha256_match':True,'desktop_mobile':True,'page_errors':errors}))
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
