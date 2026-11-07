"""Generated full UI: archive restore, portable JSON, image candidates and bulk refresh."""
import io
import json
import mimetypes
import os
from pathlib import Path
import sys
import tempfile
import threading
import urllib.error
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
from playwright.sync_api import sync_playwright,expect
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from server import Studio,make_server
from store import Store
from test_source_record import archive,spider,RangeLRR
from test_metadata import eh_html,hitomi_js
from navigation_smoke import FixtureLRR


class GeneratedLRR(FixtureLRR):
    def __init__(self,books):super().__init__();self.books=books
    def open(self,path,*args,headers=None,**kwargs):
        if path.endswith('/download'):
            return RangeLRR(self.books[path.split('/')[3]]).open(path,headers)
        return super().open(path,*args,**kwargs)


class GeneratedLogin:
    def call(self,data):
        assert data=={'op':'status'}
        return {'configured':True,'source_image_search':True,'active':None,'sites':[]}


def main():
    mimetypes.add_type('text/javascript','.js')
    output=Path(__file__).resolve().parents[2]/'work/source-finder-ui';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-admin'}):
        store=Store(Path(directory)/'catalog.db')
        a=store.create_work('Accepted archive title','User artist',lrr_id='a'*40,pages=6)
        b=store.create_work('Image search local title','User artist',lrr_id='b'*40,pages=6)
        c=store.create_work('Bulk restore local title','User artist',lrr_id='c'*40,pages=6)
        xml=b'<ComicInfo><Web>https://exhentai.org/g/987654/abcdefghij/</Web><Title>A Garden</Title><Writer>Fixture</Writer><Genre>artist:Fixture,language:korean,other:color</Genre><LanguageISO>ko</LanguageISO><PageCount>6</PageCount></ComicInfo>'
        books={'a'*40:archive([('.ehviewer',spider(987654,'abcdefghij',6)),('ComicInfo.xml',xml)],zip64=True),
               'b'*40:archive([('page.png',b'generated')]),'c'*40:archive([('.ehviewer',spider(222222,'abcdefghij',6))])}
        lrr=GeneratedLRR(books);app=Studio(store,lrr);app.login=GeneratedLogin();fetches=[]
        def fetch(url):
            fetches.append(url)
            if 'f_shash=' in url:
                return ''.join('<a href="https://e-hentai.org/g/'+str(i)+'/abcdefghij/">Candidate</a>' for i in range(111111,111117))
            if url.startswith('https://ltn.gold-usergeneratedcontent.net/galleries/'):return hitomi_js()
            gid=url.split('/')[4]
            if gid=='222222':raise urllib.error.HTTPError(url,404,'Generated removed gallery',{},None)
            return eh_html().replace('987654',gid).replace('abcdef','abcdefghij')+'<span id="rating_label">Average: 4.35</span><span id="rating_count">1234</span>'
        app.source_transport=lambda:(fetch,lambda artist,offset=None: {'ids':['123456'],'complete':True} if offset is not None else ['123456'],{})
        server=make_server('127.0.0.1',0,app);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=os.environ.get('STUDIO_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
                context=browser.new_context(http_credentials={'username':'admin','password':'generated-admin'},viewport={'width':1440,'height':1000})
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto('http://127.0.0.1:'+str(server.server_port))
                page.locator('#grid .card[data-id="'+a['id']+'"]').click()
                page.locator('#restore-original-source').click()
                expect(page.locator('#connected-source-list a[href="https://exhentai.org/g/987654/abcdefghij/"]')).to_be_visible()
                assert store.get_work(a['id'])['title']=='Accepted archive title'
                assert store.get_work(a['id'])['artist']=='User artist'
                expect(page.locator('#connected-source-list .source-rating')).to_have_text('출처 평점 4.35 / 5 · 1,234표')
                with page.expect_download() as download:
                    page.locator('#export-source-record').click()
                record=json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
                assert record['format']=='yuri-studio-source' and record['version']==1
                assert any('language:korean' in e.get('metadata',{}).get('tags',[]) for e in record['evidence'])
                assert record['sources'][0]['provider']=='exhentai'
                assert 'generated-excluded-secret' not in json.dumps(record)
                page.locator('#close-detail').click()
                page.locator('#grid .card[data-id="'+b['id']+'"]').click()
                page.locator('#source-find-method').select_option('image')
                page.locator('#source-find-start').click()
                expect(page.locator('#source-find-results .source-row')).to_have_count(5)
                assert store.get_work(b['id'])['sources']==[]
                app.source_search_at=0
                page.locator('#source-find-more').click()
                expect(page.locator('#source-find-results .source-row')).to_have_count(6)
                expect(page.locator('#source-find-more')).to_be_hidden()
                for width,height in ((1440,1000),(390,844)):
                    page.set_viewport_size({'width':width,'height':height})
                    page.locator('#source-finder').scroll_into_view_if_needed()
                    box=page.locator('#source-finder').bounding_box();assert box['x']>=0 and box['x']+box['width']<=width+1
                    page.screenshot(path=str(output/('desktop.png' if width>400 else 'mobile.png')))
                app.source_search_at=0
                page.locator('[data-source-hitomi="0"]').click()
                expect(page.locator('#source-find-results .source-row')).to_have_count(1)
                expect(page.locator('#source-find-note')).to_contain_text('이미지 후보의 작가·제목')
                assert store.get_work(b['id'])['sources']==[], 'Searching via an image candidate must not silently link it'
                page.locator('[data-source-finder-select="0"]').click()
                expect(page.locator('#connected-source-list [data-fetch]')).to_have_count(1)
                assert store.get_work(b['id'])['title']=='Image search local title'
                app.source_search_at=0
                page.locator('#source-find-method').select_option('image');page.locator('#source-find-start').click()
                expect(page.locator('#source-find-results .source-row')).to_have_count(5)
                page.locator('[data-source-finder-select="0"]').click()
                expect(page.locator('#connected-source-list [data-fetch]')).to_have_count(2)
                page.locator('#close-detail').click();page.set_viewport_size({'width':1440,'height':1000})
                page.locator('#refresh-metadata').click()
                expect(page.locator('#metadata-refresh-status')).to_contain_text('완료',timeout=20000)
                expect(page.locator('#metadata-refresh-status')).to_contain_text('원본 복원 1개')
                assert store.get_work(c['id'])['sources'][0]['external_id']=='222222'
                assert store.get_work(c['id'])['sources'][0]['status']=='manual'
                assert next(s for s in store.get_work(b['id'])['sources'] if s['provider']=='ehentai')['status']=='fetched'
                with store.db() as db:assert db.execute('SELECT 1 FROM source_link_jobs WHERE work_id=?',(c['id'],)).fetchone() is None
                assert store.get_work(c['id'])['title']=='Bulk restore local title'
                assert not errors,errors
                browser.close()
            print('SOURCE_FINDER_UI=PASS original_archive_restore=true portable_json=true image_candidates_and_more=true manual_eh_hitomi_connection=true bulk_removed_page_continues=true desktop_mobile=true')
        finally:server.shutdown();server.server_close();thread.join(timeout=3)


if __name__=='__main__':main()
