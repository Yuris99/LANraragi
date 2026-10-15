"""Synthetic-only Chromium checks for default pixelation and explicit /unsen."""
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
                    # An old browser setting must never disable the default route mask.
                    page.add_init_script("localStorage.setItem('studio-view', JSON.stringify({mosaic:false}))")
                    base='http://127.0.0.1:'+str(server.server_port)
                    page.goto(base)
                    page.locator('.card .mosaic-layer:not([hidden])').wait_for(state='visible')
                    assert page.locator('.card img').evaluate('(el) => getComputedStyle(el).opacity')=='0'
                    assert page.locator('.card canvas').evaluate('(el) => el.width')==12
                    page.locator('.card').click()
                    page.locator('#detail .mosaic-layer:not([hidden])').wait_for(state='visible')
                    page.locator('#read-work').click()
                    page.locator('.reader-page .mosaic-layer:not([hidden])').wait_for(state='visible')
                    assert page.locator('#reader-image').evaluate('(el) => getComputedStyle(el).opacity')=='0'
                    page.goto(base+'/unsen')
                    page.locator('.card img').wait_for()
                    assert page.locator('.card img').evaluate('(el) => getComputedStyle(el).opacity')=='1'
                    assert not page.locator('html').evaluate('(el) => el.classList.contains("media-masked")')
                    page.locator('#privacy-route').click()
                    page.locator('.card .mosaic-layer:not([hidden])').wait_for(state='visible')
                    assert page.locator('.card img').evaluate('(el) => getComputedStyle(el).opacity')=='0'
                    for width,height in [(390,844),(1440,1000)]:
                        page.set_viewport_size({'width':width,'height':height})
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    # Rendering failure keeps the source hidden rather than revealing it.
                    failed=context.new_page();failed.add_init_script('HTMLCanvasElement.prototype.getContext = () => null')
                    failed.goto(base);failed.locator('.card img').wait_for()
                    failed.wait_for_function("() => document.querySelector('.card img').complete")
                    assert failed.locator('.card img').evaluate('(el) => getComputedStyle(el).opacity')=='0'
                    assert not errors,errors
                    browser.close()
                print(json.dumps({'default_mask':True,'legacy_setting_cannot_unmask':True,'thumbnail_detail_reader':True,
                                  'explicit_unsen':True,'return_to_default_mask':True,'canvas_failure_keeps_mask':True,
                                  'desktop_mobile':True,'page_errors':errors}))
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
