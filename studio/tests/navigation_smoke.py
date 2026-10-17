"""Actual browser history/deep-link regression with generated seven-page works."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import urllib.parse
from unittest.mock import patch
from PIL import Image
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Studio,make_server
from store import Store


class FixtureLRR:
    def __init__(self):
        self.calls=[];self.images={};self.fail_files_once=False
        for number in range(1,8):
            stream=io.BytesIO();Image.new('RGB',(320,480),(number*30,90,180)).save(stream,format='PNG');self.images[number]=stream.getvalue()
    def json(self,path,*args):
        self.calls.append(path)
        if path=='/api/info':return {'version':'synthetic-seven-pages'}
        if path.endswith('/files'):
            if self.fail_files_once:
                self.fail_files_once=False;raise ValueError('Synthetic extraction still preparing; retry')
            key=path.split('/')[3]
            return {'pages':[f'/api/archives/{key}/page?p={number}' for number in range(1,8)]}
        raise ValueError('Fixture only; no external access')
    def open(self,path,*args,**kwargs):
        number=int(urllib.parse.parse_qs(urllib.parse.urlsplit(path).query).get('p',['1'])[0]);png=self.images[number]
        response=io.BytesIO(png);response.status=200;response.headers={'Content-Type':'image/png','Content-Length':str(len(png))};return response


def main():
    with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{'STUDIO_PASSWORD':'navigation-synthetic-password'}):
        store=Store(Path(temporary)/'studio.db');lrr=FixtureLRR()
        for number in range(60):store.create_work(f'History Synthetic {number:02}',pages=7,lrr_id=f'{number:040x}')
        app=Studio(store,lrr);server=make_server('127.0.0.1',0,app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':'navigation-synthetic-password'},viewport={'width':1440,'height':900})
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base+'/#/library?q=History&sort=title&direction=asc&limit=24&page=2')
                page.wait_for_function('()=>document.querySelectorAll(".card").length===24')
                assert page.locator('#page-number').inner_text()=='2 / 3 페이지'
                assert page.locator('#search').input_value()=='History'
                work_id=page.locator('.card').first.get_attribute('data-id')
                page.locator('.card').first.scroll_into_view_if_needed();page.evaluate('window.scrollTo(0,400)');scroll=page.evaluate('scrollY')
                page.locator('.card').first.click();page.wait_for_url('**/#/works/'+work_id);page.locator('#detail[open]').wait_for()
                detail_url=page.url
                page.locator('#read-work').click();page.wait_for_url('**/read/1');page.locator('#reader[open]').wait_for()
                page.locator('#reader-page').fill('6');page.locator('#reader-jump button').click();page.wait_for_url('**/read/6')
                page.wait_for_function('()=>document.querySelector("#reader-position").textContent==="6 / 7"')
                calls=len([p for p in lrr.calls if p.endswith('/files')])
                page.locator('#reader-next').click();page.wait_for_url('**/read/7');reader_url=page.url
                page.go_back();page.wait_for_url('**/read/6');page.wait_for_function('()=>document.querySelector("#reader-position").textContent==="6 / 7"')
                assert 'p=6' in page.locator('#reader-image').get_attribute('src')
                page.go_forward();page.wait_for_url('**/read/7');page.wait_for_function('()=>document.querySelector("#reader-position").textContent==="7 / 7"')
                assert len([p for p in lrr.calls if p.endswith('/files')])==calls,'Page turns reuse the prepared file list'
                length=page.evaluate('history.length');page.locator('#reader-page').fill('7');page.locator('#reader-jump button').click()
                assert page.evaluate('history.length')==length,'Selecting the current page must not duplicate history'
                page.reload();page.locator('#reader[open]').wait_for();page.wait_for_function('()=>document.querySelector("#reader-position").textContent==="7 / 7"')
                assert page.url==reader_url
                page.locator('#close-reader').click();page.wait_for_url('**/#/works/'+work_id);page.locator('#detail[open]').wait_for()
                page.locator('#close-detail').click();page.locator('#grid').wait_for(state='visible')
                page.wait_for_function('()=>document.querySelector("#page-number").textContent==="2 / 3 페이지"')
                page.wait_for_function('(scroll)=>Math.abs(scrollY-scroll)<3',arg=scroll)
                assert page.locator('#search').input_value()=='History' and page.locator('#sort').input_value()=='title'
                # Real browser Back from detail returns to the prior list, not an app exit.
                page.locator('.card').first.click();page.locator('#detail[open]').wait_for();page.go_back()
                page.wait_for_function('()=>!document.querySelector("#detail").open')
                assert 'page=2' in page.url and 'q=History' in page.url
                direct=context.new_page();direct.on('pageerror',lambda error:errors.append(str(error)))
                direct.goto(detail_url);direct.locator('#detail[open]').wait_for();direct.reload();direct.locator('#detail[open]').wait_for()
                direct.goto(reader_url);direct.locator('#reader[open]').wait_for();direct.wait_for_function('()=>document.querySelector("#reader-position").textContent==="7 / 7"')
                direct.goto(reader_url.rsplit('/',1)[0]+'/999');direct.wait_for_url('**/read/7');direct.locator('#reader[open]').wait_for()
                for width,height in [(1440,900),(390,844)]:
                    direct.set_viewport_size({'width':width,'height':height})
                    assert direct.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert direct.locator('#reader-jump button').is_visible()
                    assert direct.locator('#reader').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
                direct.keyboard.press('ArrowLeft');direct.wait_for_url('**/read/6')
                direct.go_back();direct.wait_for_url('**/read/7')
                direct.keyboard.press('Escape');direct.locator('#detail[open]').wait_for();assert '/read/' not in direct.url
                direct.keyboard.press('Escape');direct.wait_for_function('()=>!document.querySelector("#detail").open')
                # A slow old detail response cannot reopen after going Back.
                page.goto(base+'/#/library');page.locator('.card').first.wait_for()
                old_id=page.locator('.card').first.get_attribute('data-id')
                started=threading.Event();original_get=store.get_work
                def delayed_get(work_id):
                    if work_id==old_id:started.set();time.sleep(.4)
                    return original_get(work_id)
                with patch.object(store,'get_work',side_effect=delayed_get):
                    page.locator('.card').first.click();assert started.wait(1)
                    page.go_back();page.wait_for_timeout(600)
                    assert not page.locator('#detail').is_visible() and '/works/' not in page.url
                direct.goto(base+'/#/works/not-an-id/read/7');direct.wait_for_url('**/#/library');direct.locator('.card').first.wait_for()
                lrr.fail_files_once=True
                retry=context.new_page();retry.on('pageerror',lambda error:errors.append(str(error)));retry.goto(reader_url.rsplit('/',1)[0]+'/6')
                retry.locator('#detail[open]').wait_for();assert '/read/' not in retry.url
                retry.locator('#read-work').click();retry.wait_for_url('**/read/6')
                retry.wait_for_function('()=>document.querySelector("#reader-position").textContent==="6 / 7"')
                assert not errors,errors
                browser.close()
            print(json.dumps({'page6_page7_back_forward':True,'same_page_no_duplicate_history':True,'reader_detail_reload_deep_links':True,
                              'list_query_page_scroll_restored':True,'file_list_reused_between_pages':True,'direct_page_clamped':True,
                              'keyboard_escape_mobile':True,'stale_detail_response_cancelled':True,'invalid_route_safe':True,'preparing_archive_retry_keeps_requested_page':True,'page_errors':errors}))
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
