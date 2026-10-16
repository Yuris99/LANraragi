"""Synthetic browser test: user tags, bulk edit, rename/merge and file/folder upload."""
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
from make_synthetic import create_fixture
from playwright.sync_api import sync_playwright

class FixtureLRR:
    def json(self,path,*args):
        if path=='/api/info':return {'version':'synthetic'}
        if path=='/api/archives':return []
        raise ValueError('No remote service in this fixture')

def main():
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'synthetic-tags-only'}):
        root=Path(directory);store=Store(root/'studio.db')
        first=store.create_work('Synthetic one');store.create_work('Synthetic two')
        source=store.upsert_source(first['id'],{'url':'https://e-hentai.org/g/123/abcdef/','tags':['remote-original']})
        fixture=create_fixture(root/'folder')
        app=Studio(store,FixtureLRR(),upload_dir=root/'uploads');server=make_server('127.0.0.1',0,app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':'synthetic-tags-only'})
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto('http://127.0.0.1:'+str(server.server_port))
                page.locator('.card').first.wait_for()
                page.locator('#select-page').check();page.locator('#batch-tags').click()
                page.locator('#tag-form [name=add]').fill('소장, old')
                page.locator('#tag-form button.primary').click()
                page.wait_for_function("() => !document.querySelector('#tag-dialog').open")
                assert store.tag_catalog('소장')==[{'tag':'소장','count':2}]
                page.locator('#manage-tags').click()
                page.locator('#rename-tag-form [name=source]').fill('old')
                page.locator('#rename-tag-form [name=target]').fill('소장')
                page.locator('#rename-tag-form button.primary').click()
                page.locator('#rename-confirm').wait_for(state='visible');page.locator('#rename-apply').click()
                page.wait_for_function("() => !document.querySelector('#rename-confirm').open")
                assert store.tag_catalog('old')==[]
                page.locator('#tag-manager [data-close]').click()
                page.locator('.card').first.click()
                page.locator('#edit-user-tags').click()
                page.locator('#tag-form [name=add]').fill('소')
                page.wait_for_function("() => document.querySelector('#tag-suggestions option[value=\"소장\"]')")
                page.locator('#tag-form [name=add]').fill('single')
                page.locator('#tag-form button.primary').click()
                page.locator('[data-remove-user-tag=single]').click()
                page.locator('[data-user-filter="소장"]').click()
                page.locator('#total').get_by_text('2 작품',exact=True).wait_for()
                assert store.get_work(first['id'])['sources'][0]['tags']==['remote-original']
                page.locator('#upload').click();page.locator('#upload-tags').fill('uploaded')
                page.locator('#upload-folder').set_input_files(str(root/'folder'))
                page.locator('#upload-start').click()
                page.wait_for_function("() => document.querySelector('#upload-status').textContent.includes('완료')")
                records=app.uploads.list();assert len(records)==1
                with store.db() as db:assert db.execute('SELECT tag FROM upload_tags').fetchone()[0]=='uploaded'
                page.wait_for_function("() => !document.querySelector('#upload-files').disabled")
                page.locator('#upload-tags').fill('dragged')
                page.locator('#upload-drop').evaluate("(el, bytes) => { const data=new DataTransfer(); data.items.add(new File([new Uint8Array(bytes)], 'drag.cbz')); el.dispatchEvent(new DragEvent('drop', {dataTransfer:data,bubbles:true,cancelable:true})); }",list(fixture.read_bytes()))
                with page.expect_response(lambda response: response.request.method=='POST' and '/api/uploads?' in response.url):
                    page.locator('#upload-start').click()
                with store.db() as db:assert db.execute("SELECT count(*) FROM upload_tags WHERE tag='dragged'").fetchone()[0]==1
                assert len(app.uploads.list())==1
                for width in [390,1440]:
                    page.set_viewport_size({'width':width,'height':900})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors,errors
                browser.close()
            print(json.dumps({'bulk_tags':True,'merge':True,'autocomplete':True,'single_add_remove':True,'source_preserved':True,'folder_upload_tags':True,'mobile_desktop':True,'page_errors':errors}))
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':main()
