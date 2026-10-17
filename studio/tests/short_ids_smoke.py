"""Short source routes + favorite/exact-tag flows; all media is generated locally."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import Store
from server import Studio,make_server
from navigation_smoke import FixtureLRR


def main():
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'short-ui-synthetic'}):
        store=Store(Path(directory)/'studio.db');lrr=FixtureLRR()
        h=store.create_work('Hitomi fixture',lrr_id='a'*40,pages=7,tags=['theme:blue'])
        e=store.create_work('E fixture',lrr_id='b'*40,pages=7)
        n=store.create_work('N fixture',lrr_id='c'*40,pages=7,tags=['theme:bluebird'])
        local=store.create_work('Local fixture',lrr_id='d'*40,pages=7)
        for work,url,tags in [(h,'https://hitomi.la/galleries/123.html',[]),(h,'https://e-hentai.org/g/999/token/',[]),
                              (e,'https://e-hentai.org/g/123/token/',['theme:blue']),(n,'https://nhentai.net/g/123/',[])]:
            store.upsert_source(work['id'],{'url':url,'tags':tags})
        store.edit_user_tags([e['id'],local['id']],['theme:blue'])
        for work in [h,n]:store.update_work(work['id'],{'favorite':True})
        app=Studio(store,lrr);server=make_server('127.0.0.1',0,app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base='http://127.0.0.1:'+str(server.server_port)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':'short-ui-synthetic'},viewport={'width':1440,'height':1000})
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base);page.locator('.card').first.wait_for()
                assert page.locator('[data-view=unread]').count()==0
                page.locator('#open-number').click();page.locator('#short-form [name=number]').fill('123');page.locator('#short-form .primary').click()
                page.wait_for_url('**/#/123');page.locator('#detail[open]').wait_for();assert 'Hitomi fixture' in page.locator('#detail h2').inner_text()
                for ref,title in [('E123','E fixture'),('N123','N fixture'),(local['short_id'],'Local fixture')]:
                    page.goto(base+'/#/'+ref);page.locator('#detail[open]').wait_for();assert page.locator('#detail h2').inner_text()==title
                    assert page.url.endswith('/'+ref)
                page.goto(base+'/#/E999/6');page.wait_for_url('**/#/123/6');page.locator('#reader[open]').wait_for()
                page.locator('#reader-next').click();page.wait_for_url('**/#/123/7');page.go_back();page.wait_for_url('**/#/123/6')
                page.reload();page.locator('#reader[open]').wait_for();assert page.locator('#reader-position').inner_text()=='6 / 7'
                page.goto(base+'/#/works/'+local['id']+'/read/7');page.wait_for_url('**/#/'+local['short_id']+'/7');page.locator('#reader[open]').wait_for()
                page.goto(base+'/#/library');page.locator('.card').first.wait_for()
                page.locator('#filter-tags-nav').click()
                tag=page.locator('[data-filter-tag="theme:blue"]');tag.wait_for();assert tag.inner_text()=='theme:blue · 3'
                tag.click();page.wait_for_function('()=>document.querySelectorAll(".card").length===3')
                assert 'all_tag=theme%3Ablue' in page.url and 'theme:blue' in page.locator('#active-tag-name').inner_text()
                assert page.locator('.card').filter(has_text='N fixture').count()==0
                page.locator('[data-view=favorite]').click();page.wait_for_function('()=>document.querySelectorAll(".card").length===1')
                page.locator('.card').click();page.locator('#detail[open]').wait_for();page.go_back()
                page.wait_for_function('()=>!document.querySelector("#detail").open&&document.querySelectorAll(".card").length===1')
                assert 'view=favorite' in page.url and 'all_tag=' in page.url
                page.locator('#clear-tag').click();page.wait_for_function('()=>document.querySelectorAll(".card").length===2')
                assert not page.locator('#active-tag').is_visible()
                page.goto(base+'/#/123');page.locator('#detail[open]').wait_for()
                page.locator('[data-tag="theme:blue"]').click();page.wait_for_function('()=>document.querySelectorAll(".card").length===1')
                assert 'all_tag=' in page.url and 'view=favorite' in page.url
                page.goto(base+'/#/library?view=unread');page.wait_for_url('**/#/library');page.locator('.card').first.wait_for()
                for width,height in [(1440,1000),(390,844)]:
                    page.set_viewport_size({'width':width,'height':height})
                    assert page.locator('#open-number').is_visible()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.locator('#filter-tags-nav').click();page.locator('[data-filter-tag="theme:blue"]').wait_for()
                    assert page.locator('#tag-filter').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
                    page.locator('#tag-filter [data-close]').click()
                page.goto(base+'/#/456');page.wait_for_url('**/#/library');page.locator('.card').first.wait_for()
                assert store.jobs()==[] and store.list_works()['total']==4
                assert store.get_work(e['id'])['sources'][0]['url']=='https://e-hentai.org/g/123/token/'
                assert not errors,errors
                browser.close()
            print(json.dumps({'hitomi_default_e_n_namespaces':True,'linked_alias_redirect_keeps_page':True,'local_alias_and_uuid_bookmarks':True,
                              'history_reload':True,'exact_source_and_user_tag_counts':True,'favorites_combined_filter':True,
                              'unread_menu_removed':True,'desktop_mobile':True,'no_auto_download_or_merge':True,'page_errors':errors}))
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
