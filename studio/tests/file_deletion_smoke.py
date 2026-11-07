"""Browser -> admin API -> actual Linux deletion worker on generated fixtures only."""
import base64
import io
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from store import Store
from server import Studio,make_server
from test_file_deletion import FixtureLRR,archive_bytes


class BrowserLRR(FixtureLRR):
    def open(self,path,*args,**kwargs):
        if path.endswith('/thumbnail'):
            stream=io.BytesIO(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jV4kAAAAASUVORK5CYII='));stream.status=200;stream.headers={'Content-Type':'image/png'};return stream
        return super().open(path,*args)


def main():
    mimetypes.add_type('text/javascript','.js')
    code=Path(__file__).resolve().parents[1];output=code.parent/'work/file-delete';output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ['STUDIO_TEST_CHROMIUM'],headless=True,args=['--no-sandbox'])
        for width in [1440,390]:
            with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-deletion-ui'}):
                root=Path(temporary);originals=root/'originals';(originals/'manga').mkdir(parents=True);(originals/'images').mkdir();(root/'uploads').mkdir()
                lrr=BrowserLRR(archive_bytes(),f'Generated book {width}.cbz');target=originals/'manga'/lrr.name;target.write_bytes(lrr.data)
                store=Store(root/'studio.db');store.set_automatic_enabled(False)
                work=store.create_work('Generated <title> & saved metadata',artist='Generated artist',lrr_id=lrr.arcid,pages=1,tags=['language:korean'])
                store.upsert_source(work['id'],{'url':'https://hitomi.la/galleries/123.html'})
                def tick():
                    command=['docker','run','--rm','--network','none','--read-only','--user','0:0','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--cap-add','SETUID','--cap-add','SETGID','--security-opt','no-new-privileges:true',
                        '--mount',f'type=bind,source={root},target=/fixture','--mount',f'type=bind,source={code},target=/studio,readonly','--entrypoint','python','library-studio-worker:hitomi-metadata-g14-test','-B','-c',
                        "import sys;sys.path.insert(0,'/studio');from file_deletion import DeletionWorker;DeletionWorker('/fixture/studio.db','/fixture/originals','/fixture/uploads').tick()"]
                    result=subprocess.run(command,capture_output=True,text=True,timeout=40);assert result.returncode==0,result.stderr
                server=make_server('127.0.0.1',0,Studio(store,lrr));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    context=browser.new_context(http_credentials={'username':'admin','password':'generated-deletion-ui'},viewport={'width':width,'height':960},is_mobile=width<500,has_touch=width<500,reduced_motion='reduce')
                    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto('http://127.0.0.1:'+str(server.server_port)+'/manga');expect(page.locator('#grid .card')).to_have_count(1)
                    page.locator('#grid .card-title').click();expect(page.locator('#detail')).to_be_visible()
                    page.locator('#delete-work-file').click();expect(page.locator('#file-deletion-status')).to_contain_text('설치·연결')
                    expect(page.locator('#file-deletion-submit')).not_to_be_visible();assert target.exists()
                    page.locator('#file-deletion-dialog [data-close]').click();tick()
                    page.locator('#delete-work-file').click();expect(page.locator('#file-deletion-check')).to_be_visible()
                    expect(page.locator('#file-deletion-submit')).to_be_disabled();expect(page.locator('#file-deletion-name')).to_contain_text(lrr.name)
                    page.screenshot(path=str(output/f'deletion-confirm-{width}.png'))
                    assert page.locator('#file-deletion-dialog').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
                    page.locator('#file-deletion-dialog [data-close]').click();assert target.read_bytes()==lrr.data
                    assert store.get_work(work['id'])['lrr_id']==lrr.arcid
                    page.locator('#delete-work-file').click();expect(page.locator('#file-deletion-check')).to_be_visible()
                    page.locator('#file-deletion-ack').check();page.locator('#file-deletion-submit').click()
                    expect(page.locator('#file-deletion-status')).to_contain_text('대기');assert target.exists()
                    tick();expect(page.locator('#file-deletion-dialog')).not_to_be_visible(timeout=15000)
                    assert not target.exists();expect(page.locator('#read-work')).to_be_disabled()
                    expect(page.locator('#delete-work-file')).to_have_count(0)
                    assert store.get_work(work['id'])['title']==work['title'] and len(store.get_work(work['id'])['sources'])==1
                    page.screenshot(path=str(output/f'deletion-complete-{width}.png'))
                    page.locator('#close-detail').click();page.locator('#sync').click();expect(page.locator('#sync')).to_be_enabled()
                    assert store.get_work(work['id'])['lrr_id'] is None
                    assert not errors,errors
                    context.close()
                finally:server.shutdown();server.server_close();thread.join()
        browser.close()
    print('FILE_DELETE_UI=PASS desktop/mobile: unavailable worker, preview+cancel, required confirmation, queued file intact, actual Linux unlink, metadata preserved, stale sync blocked')


if __name__=='__main__':main()
