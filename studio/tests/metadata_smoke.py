"""Generated-only browser integration for metadata, candidates and tag suggestions."""
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
from metadata import parse_html,compare_metadata
from test_metadata import H,E,hitomi_html,eh_html


class LRR:
    def json(self,path,*args):
        if path=='/api/info':return {'version':'generated'}
        if path=='/api/archives':return []
        raise ValueError('No remote service in generated test')


def main():
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-metadata-ui'}):
        root=Path(directory);store=Store(root/'catalog.db')
        work=store.create_work('Keep my title','',tags=['date_added:123','timestamp:456'])
        store.edit_user_tags([work['id']],['keep-user-tag'])
        app=Studio(store,LRR(),upload_dir=root/'uploads');server=make_server('127.0.0.1',0,app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':'generated-metadata-ui'})
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto('http://127.0.0.1:'+str(server.server_port))
                page.locator('.card').first.wait_for()
                assert page.locator('#folder-open').count()==0
                page.locator('.card').first.click()
                page.get_by_text('출처 연결 · 태그·댓글 가져오기',exact=True).click()
                form=page.locator('#html-metadata-form')
                form.locator('[name=url]').fill(H)
                (root/'generated.html').write_text(hitomi_html())
                form.locator('#metadata-file').set_input_files(str(root/'generated.html'))
                page.wait_for_function("() => document.querySelector('#html-metadata-form [name=html]').value.includes('gallery-brand')")
                page.locator('#metadata-preview').click()
                page.locator('#metadata-preview-result').get_by_text('A Garden',exact=False).wait_for()
                assert page.locator('#metadata-save').is_enabled()
                form.locator('[name=url]').fill(H.replace('123456','999999'))
                assert page.locator('#metadata-save').is_disabled()
                form.locator('[name=url]').fill(H)
                page.locator('#metadata-preview').click()
                page.wait_for_function("() => !document.querySelector('#metadata-save').disabled")
                page.locator('#metadata-save').click()
                page.wait_for_function("() => document.querySelectorAll('.source-header').length===1")
                assert store.get_work(work['id'])['title']=='Keep my title'
                assert 'date_added:' not in page.locator('#detail').inner_text()
                h=store.get_work(work['id'])['sources'][0]['metadata'];e=parse_html(E,eh_html())
                candidate={'metadata':e,'comparison':compare_metadata(h,e)}
                job=store.claim_automatic()
                store.finish_automatic(job,{'sites':[{'provider':'ehentai','status':'review','items':[candidate]}],'connected':[]},'review')
                page.locator('[data-counterpart-select="0"]').wait_for()
                page.locator('[data-counterpart-select="0"]').click()
                page.wait_for_function("() => document.querySelectorAll('.source-header').length===2")
                assert len(store.get_work(work['id'])['sources'])==2
                assert next(s for s in store.get_work(work['id'])['sources'] if s['provider']=='ehentai')['comments'][0]['text']=='A & B'
                assert store.get_work(work['id'])['user_tags']==['keep-user-tag']
                page.locator('#close-detail').click()
                page.locator('#search').fill('parody:')
                page.wait_for_function("() => document.querySelector('#library-tag-suggestions option[value=\"parody:original\"]')")
                assert not page.locator('#library-tag-suggestions option[value^="date_added:"]').count()
                for width in (390,1440):
                    page.set_viewport_size({'width':width,'height':900})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert errors==[],errors
                browser.close()
            print('metadata_UI=passed; generated_HTML_preview_and_edit_gate; source_candidate_selection; original_title_and_user_tags_preserved; tag_autocomplete; internal_tags_hidden; folder_copy_menu_removed; mobile_desktop; no_page_errors; live_site_verified=false; NAS_changed=false')
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
