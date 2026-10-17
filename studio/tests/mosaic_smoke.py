"""Synthetic-only Chromium checks for thumbnail pixelation, reveal and saved toggle."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import zipfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Studio,make_server
from store import Store
from make_synthetic import create_fixture
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory() as directory:
        fixture=create_fixture(Path(directory)/'fixture')
        with zipfile.ZipFile(fixture) as archive:png=archive.read('01.png')
        class FixtureLRR:
            def json(self,path,*args):
                if path=='/api/info':return {'version':'synthetic'}
                if path=='/api/archives':return [{'arcid':'a'*40}]
                if path.endswith('/metadata'):return {'arcid':'a'*40,'title':'Synthetic mosaic fixture','pagecount':1}
                if path.endswith('/files'):return {'pages':['/api/archives/'+'a'*40+'/page?p=1']}
                raise ValueError('Unknown fixture endpoint')
            def open(self,*args,**kwargs):
                response=io.BytesIO(png);response.status=200
                response.headers={'Content-Type':'image/png','Content-Length':str(len(png))}
                return response
        with patch.dict(os.environ,{'STUDIO_PASSWORD':'synthetic-mosaic-password'}):
            app=Studio(Store(Path(directory)/'fixture.db'),FixtureLRR());app.sync()
            server=make_server('127.0.0.1',0,app)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                    context=browser.new_context(http_credentials={'username':'admin','password':'synthetic-mosaic-password'})
                    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    # Old route-only preferences cannot disable a fresh default.
                    page.add_init_script("if (!localStorage.getItem('studio-view')) localStorage.setItem('studio-view', JSON.stringify({mosaic:false}))")
                    base='http://127.0.0.1:'+str(server.server_port)
                    page.goto(base)
                    page.locator('.card .mosaic-layer:not([hidden])').wait_for(state='visible')
                    assert page.locator('.card img').evaluate('(el) => getComputedStyle(el).opacity')=='0'
                    assert page.locator('.card canvas').evaluate('(el) => el.width')==48
                    page.locator('.card').click()
                    page.wait_for_function("() => document.querySelector('#detail img')?.complete && document.querySelector('#detail img').naturalWidth > 0")
                    assert page.locator('#detail img').evaluate('(el) => getComputedStyle(el).opacity')=='1'
                    assert page.locator('#detail .mosaic-layer').count()==0
                    page.locator('#read-work').click()
                    page.wait_for_function("() => document.querySelector('#reader-image')?.complete && document.querySelector('#reader-image').naturalWidth > 0")
                    assert page.locator('#reader-image').evaluate('(el) => getComputedStyle(el).opacity')=='1'
                    assert page.locator('.reader-page .mosaic-layer').count()==0
                    page.locator('#close-reader').click();page.locator('#close-detail').click()
                    page.locator('#settings-button').click();page.locator('#thumbnail-mosaic').uncheck()
                    assert page.locator('.card img').evaluate('(el) => getComputedStyle(el).opacity')=='1'
                    page.locator('#settings [data-close]').click();page.reload();page.locator('.card').wait_for()
                    assert page.locator('.card img').evaluate('(el) => getComputedStyle(el).opacity')=='1'
                    assert page.evaluate("JSON.parse(localStorage.getItem('studio-view')).thumbnailMosaic") is False
                    page.locator('#privacy-route').click()
                    page.locator('.card .mosaic-layer:not([hidden])').wait_for(state='visible')
                    page.reload();page.locator('.card .mosaic-layer:not([hidden])').wait_for(state='visible')
                    page.goto(base+'/unsen');page.locator('.card img').wait_for()
                    assert page.locator('.card img').evaluate('(el) => getComputedStyle(el).opacity')=='1'
                    page.goto(base);page.locator('.card .mosaic-layer:not([hidden])').wait_for(state='visible')
                    for width,height in [(390,844),(1440,1000)]:
                        page.set_viewport_size({'width':width,'height':height})
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    # Thumbnail canvas failure stays masked; opening still reveals.
                    failed=context.new_page();failed.add_init_script('HTMLCanvasElement.prototype.getContext = () => null')
                    failed.goto(base);failed.locator('.card img').wait_for()
                    failed.wait_for_function("() => document.querySelector('.card img').complete")
                    assert failed.locator('.card img').evaluate('(el) => getComputedStyle(el).opacity')=='0'
                    failed.locator('.card').click()
                    assert failed.locator('#detail img').evaluate('(el) => getComputedStyle(el).opacity')=='1'
                    assert not errors,errors
                    browser.close()
                print(json.dumps({'default_thumbnail_mask':True,'mosaic_columns':48,'detail_reader_original':True,
                                  'settings_toggle_persisted':True,'explicit_unsen_compatible':True,
                                  'canvas_failure_keeps_thumbnail_mask':True,'desktop_mobile':True,'page_errors':errors}))
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
