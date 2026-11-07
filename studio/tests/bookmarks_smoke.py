"""Generated works only: tag/artist bookmarks, reload and exact facet navigation."""
import mimetypes
import os
from pathlib import Path
import sys
import tempfile
import threading
from urllib.parse import urlsplit,parse_qs
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from store import Store
from server import Studio,make_server
from navigation_smoke import FixtureLRR


def main():
    mimetypes.add_type('text/javascript','.js')
    output=Path(__file__).resolve().parents[2]/'work/reader-bookmarks';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-bookmarks'}):
        store=Store(Path(directory)/'studio.db');store.set_automatic_enabled(False)
        artist='Generated <artist> & name'
        work=store.create_work('Generated both',artist=artist,tags=['language:korean'])
        store.create_work('Generated same artist',artist=artist,tags=['language:english'])
        store.create_work('Generated same tag',artist='Other artist',tags=['language:korean'])
        originals=store.export()['works']
        server=make_server('127.0.0.1',0,Studio(store,FixtureLRR()))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=os.environ.get('STUDIO_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
                for width in [1440,390]:
                    context=browser.new_context(http_credentials={'username':'admin','password':'generated-bookmarks'},viewport={'width':width,'height':960},is_mobile=width<500,has_touch=width<500,reduced_motion='reduce')
                    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(base+'/manga');expect(page.locator('#grid .card')).to_have_count(3)
                    tag=page.locator('#tag-strip-list [data-bookmark-kind="tag"][data-bookmark-value="language:korean"]')
                    expect(tag).to_have_attribute('aria-pressed','false')
                    if width<500:assert tag.bounding_box()['height']>=44
                    before=page.url;tag.click();expect(tag).to_have_attribute('aria-pressed','true');assert page.url==before
                    page.get_by_text('Generated both',exact=True).click();expect(page.locator('#detail')).to_be_visible()
                    author=page.locator('#detail-facets [data-bookmark-kind="artist"]')
                    author.click();expect(author).to_have_attribute('aria-pressed','true')
                    expect(page.locator('#detail')).to_be_visible()
                    page.screenshot(path=str(output/f'bookmark-detail-{width}.png'))
                    page.locator('#close-detail').click();page.reload();expect(tag).to_have_attribute('aria-pressed','true')
                    def open_bookmarks():
                        if width<500:page.locator('#nav-toggle').click()
                        page.locator('#bookmarks-open').click();expect(page.locator('#bookmarks-dialog')).to_be_visible()
                    open_bookmarks()
                    expect(page.locator('#bookmark-list [data-bookmark-open]')).to_have_count(2)
                    expect(page.locator('#bookmark-list [data-bookmark-open="artist"]')).to_have_text(artist)
                    page.screenshot(path=str(output/f'bookmarks-{width}.png'))
                    assert page.locator('#bookmarks-dialog').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
                    page.locator('#bookmark-list [data-bookmark-open="tag"]').click()
                    expect(page.locator('#bookmarks-dialog')).not_to_be_visible();expect(page.locator('#grid .card')).to_have_count(2)
                    assert parse_qs(urlsplit(page.url).query)['all_tag']==['language:korean']
                    open_bookmarks();page.locator('#bookmark-list [data-bookmark-open="artist"]').click()
                    expect(page.locator('#grid .card')).to_have_count(2)
                    assert parse_qs(urlsplit(page.url).query)['artist']==[artist]
                    open_bookmarks()
                    for kind in ['tag','artist']:
                        page.locator('#bookmark-list [data-bookmark-kind="'+kind+'"]').click()
                        expect(page.locator('#bookmark-list [data-bookmark-open="'+kind+'"]').first).to_have_count(0)
                    assert store.bookmarks()==[]
                    page.locator('#bookmarks-dialog [data-close]').click()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert not errors,errors
                    context.close()
                browser.close()
            assert store.export()['works']==originals
            print('BOOKMARKS=PASS desktop/mobile tag+artist save, reload, exact filters, remove, original metadata preserved')
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
