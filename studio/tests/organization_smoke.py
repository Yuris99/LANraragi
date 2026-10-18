"""Generated-work browser regression; remote metadata is strictly mocked."""
import os
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch
from navigation_smoke import FixtureLRR
from server import Studio, make_server
from store import Store
from test_organization import CandidateTests
from connectors import source_candidates
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ,{'STUDIO_PASSWORD':'synthetic-organization'}):
        store=Store(Path(temporary)/'studio.db')
        record=dict(arcid='a'*40,filename='[Generated Artist] Generated Title [123456].cbz',title='Generated Title',tags='')
        store.sync_lrr([record])
        app=Studio(store,FixtureLRR());server=make_server('127.0.0.1',0,app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch('server.source_candidates',side_effect=lambda number:source_candidates(number,CandidateTests.fetch)),sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':'synthetic-organization'})
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto('http://127.0.0.1:'+str(server.server_port))
                page.locator('#organize-open').click()
                page.locator('.organize-number').wait_for()
                assert page.locator('.organize-number').input_value()=='123456'
                assert page.locator('.organize-artist input').input_value()=='Generated Artist'
                assert store.list_works()['items'][0]['sources']==[]
                page.locator('#organize-artists').click()
                page.wait_for_function('()=>document.querySelector("#toast").textContent.includes("1권의 빈 작가")')
                page.locator('.organize-artist input').fill('Generated Confirmed Artist')
                page.locator('.organize-artist button').click()
                page.wait_for_function('()=>document.querySelector("#toast").textContent.includes("작가를 저장")')
                store.sync_lrr([{**record,'title':'Updated Generated Title'}])
                assert store.list_works()['items'][0]['artist']=='Generated Confirmed Artist'
                page.locator('[data-match-work]').click()
                page.locator('[data-match-select]').first.wait_for()
                assert page.locator('[data-match-select]').count()==3
                assert store.list_works()['items'][0]['sources']==[]
                page.locator('[data-match-select="1"]').click()
                page.wait_for_function('()=>document.querySelector("#toast").textContent.includes("선택한 출처")')
                work=store.list_works()['items'][0]
                assert len(work['sources'])==1 and work['sources'][0]['provider']=='hitomi'
                page.wait_for_function('()=>document.querySelector("#organize-items").textContent.includes("H123456")')
                page.locator('.organize-source input').fill('https://e-hentai.org/g/654321/testtoken/')
                page.locator('.organize-source button').click()
                page.wait_for_function('()=>document.querySelector("#toast").textContent.includes("입력한 원본 URL")')
                assert len(store.list_works()['items'][0]['sources'])==2
                for width,height in [(1440,900),(390,844)]:
                    page.set_viewport_size({'width':width,'height':height})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors,errors
                browser.close()
            print('organization_browser=passed; artist_lock; three_candidates; explicit_single_selection; filename_preview; desktop/mobile; synthetic_only=true')
        finally:server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':main()
