"""Real reader layout with generated tall pages; no personal files or external sites."""
import io
import json
import mimetypes
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
from PIL import Image
from playwright.sync_api import sync_playwright,expect
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from server import Studio,make_server
from store import Store
from navigation_smoke import FixtureLRR


def main():
    mimetypes.add_type('text/javascript','.js')
    output=Path(__file__).resolve().parents[2]/'work/reader-bookmarks';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-reader'}):
        store=Store(Path(temporary)/'catalog.db');store.set_automatic_enabled(False)
        work=store.create_work('Generated tall pages',lrr_id='a'*40,pages=7)
        lrr=FixtureLRR()
        for number in range(1,8):
            stream=io.BytesIO();Image.new('RGB',(1200,2400),(number*30,90,180)).save(stream,format='PNG');lrr.images[number]=stream.getvalue()
        server=make_server('127.0.0.1',0,Studio(store,lrr));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=os.environ['STUDIO_TEST_CHROMIUM'],headless=True,args=['--no-sandbox'])
                for width,height in [(1440,900),(390,844),(1440,160)]:
                    context=browser.new_context(http_credentials={'username':'admin','password':'generated-reader'},viewport={'width':width,'height':height})
                    page=context.new_page();page.goto('http://127.0.0.1:'+str(server.server_port)+'/manga/L'+str(work['local_number'])+'/2')
                    image=page.locator('#reader-image');expect(image).to_be_visible()
                    page.wait_for_function('document.querySelector("#reader-image").complete && document.querySelector("#reader-image").naturalHeight>0')
                    metrics=page.locator('#reader').evaluate('(el)=>({height:el.clientHeight,scroll:el.scrollHeight,canvas:el.querySelector(".reader-canvas").getBoundingClientRect().height,image:el.querySelector("img").getBoundingClientRect().height})')
                    print(json.dumps({'viewport':[width,height],**metrics}),flush=True)
                    assert metrics['scroll']<=metrics['height']+1,metrics
                    image.hover();page.mouse.wheel(0,80);expect(page.locator('#reader-position')).to_have_text('3 / 7')
                    assert page.locator('#reader').evaluate('(el)=>el.scrollTop')==0
                    page.wait_for_timeout(220);page.mouse.wheel(0,-80);expect(page.locator('#reader-position')).to_have_text('2 / 7')
                    page.screenshot(path=str(output/f'reader-{width}-{height}.png'))
                    context.close()
                browser.close()
            print('READER_WHEEL=PASS tall_pages_fit=true first_wheel_turns=true viewport_scroll_absent=true')
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
