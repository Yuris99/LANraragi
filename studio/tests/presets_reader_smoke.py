"""Generated works only: clean paths, reader choices, saved tag combinations."""
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
    output=Path(__file__).resolve().parents[2]/'work/tag-language';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-presets'}):
        store=Store(Path(directory)/'studio.db');store.set_automatic_enabled(False)
        a=store.create_work('Generated both',lrr_id='a'*40,pages=7,tags=['female:glasses','language:korean'])
        store.upsert_source(a['id'],{'url':'https://e-hentai.org/g/123/abc/'})
        store.create_work('Generated glasses only',tags=['female:glasses','language:english'])
        store.create_work('Generated Korean only',tags=['male:glasses','language:korean'])
        server=make_server('127.0.0.1',0,Studio(store,FixtureLRR()))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=os.environ.get('STUDIO_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
                for width in [1440,390]:
                    context=browser.new_context(http_credentials={'username':'admin','password':'generated-presets'},viewport={'width':width,'height':960},is_mobile=width<500,has_touch=width<500,reduced_motion='reduce')
                    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(base+'/#/E123/6');page.wait_for_url(base+'/manga/E123/6')
                    expect(page.locator('#reader-position')).to_have_text('6 / 7')
                    page.locator('#close-reader').click();expect(page.locator('#read-work')).to_contain_text('이어보기 · 6쪽')
                    expect(page.locator('#read-work-start')).to_have_text('처음부터')
                    page.locator('#read-work-start').click();page.wait_for_url(base+'/manga/E123/1')
                    expect(page.locator('#reader-position')).to_have_text('1 / 7')
                    image=page.locator('#reader-image')
                    image.click(click_count=2);page.wait_for_url(base+'/manga/E123/3')
                    assert page.evaluate('getSelection().toString()')==''
                    assert image.evaluate('(el)=>getComputedStyle(el).userSelect')=='none'
                    expect(image).to_have_attribute('draggable','false')
                    image.hover();page.mouse.wheel(0,80);page.wait_for_url(base+'/manga/E123/4')
                    page.wait_for_timeout(220);page.mouse.wheel(0,-80);page.wait_for_url(base+'/manga/E123/3')
                    page.screenshot(path=str(output/f'reader-click-wheel-{width}.png'))
                    page.locator('#reader-page').fill('1');page.locator('#reader-jump button').click();page.wait_for_url(base+'/manga/E123/1')
                    page.locator('#close-reader').click();page.locator('#read-work').click();page.wait_for_url(base+'/manga/E123/1')
                    page.goto(base+'/manga/E123/6');page.reload();expect(page.locator('#reader-position')).to_have_text('6 / 7')
                    page.goto(base+'/library');expect(page.locator('#grid .card')).to_have_count(3)
                    assert urlsplit(page.url).path=='/manga' and not urlsplit(page.url).fragment
                    expect(page.locator('#audio-studio-link')).to_have_attribute('href','/audio/')
                    page.locator('#manage-tag-presets').click()
                    page.locator('#preset-name').fill(f'Generated {width}')
                    for query,tag in [('안경','female:glasses'),('한국어','language:korean')]:
                        page.locator('#preset-tag-search').fill(query)
                        page.locator('[data-preset-add="'+tag+'"]').click()
                    page.screenshot(path=str(output/f'preset-edit-{width}.png'))
                    assert page.locator('#tag-presets').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
                    page.locator('#preset-save').click();expect(page.locator('#tag-presets')).not_to_be_visible()
                    expect(page.locator('#grid .card')).to_have_count(1)
                    tags=parse_qs(urlsplit(page.url).query)['all_tag'];assert set(tags)=={'female:glasses','language:korean'}
                    assert not urlsplit(page.url).fragment
                    saved=next(p for p in store.tag_presets() if p['name']==f'Generated {width}')
                    expect(page.locator('#active-tag-name')).to_contain_text(' + ')
                    page.reload();expect(page.locator('#grid .card')).to_have_count(1)
                    page.locator('#clear-tag').click();expect(page.locator('#grid .card')).to_have_count(3)
                    page.locator('[data-preset-tab="'+saved['id']+'"]').click();expect(page.locator('#grid .card')).to_have_count(1)
                    expect(page.locator('[data-preset-tab="'+saved['id']+'"]')).to_have_attribute('aria-selected','true')
                    page.locator('[data-preset-tab="'+saved['id']+'"]').focus();page.keyboard.press('Home');page.keyboard.press('Enter')
                    expect(page.locator('#grid .card')).to_have_count(3)
                    page.keyboard.press('End');page.keyboard.press('Enter')
                    expect(page.locator('#grid .card')).to_have_count(1)
                    page.screenshot(path=str(output/f'preset-tabs-{width}.png'))
                    page.locator('#manage-tag-presets').click()
                    page.locator('[data-preset-edit="'+saved['id']+'"]').click();page.locator('#preset-name').fill(f'Renamed {width}')
                    page.locator('#preset-save').click();expect(page.locator('#tag-presets')).not_to_be_visible()
                    other=context.new_page();other.goto(base+'/manga')
                    expect(other.locator('[data-preset-tab="'+saved['id']+'"]')).to_have_text(f'Renamed {width}')
                    other.close()
                    page.locator('#manage-tag-presets').click();page.locator('[data-preset-delete="'+saved['id']+'"]').click()
                    expect(page.locator('[data-preset-edit="'+saved['id']+'"]')).to_have_count(0)
                    page.locator('#tag-presets [data-close]').click()
                    expect(page.locator('#grid .card')).to_have_count(1)
                    assert not any(p['id']==saved['id'] for p in store.tag_presets())
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.goto(base+'/unsen');expect(page.locator('#grid .card')).to_have_count(3)
                    expect(page.locator('html')).not_to_have_class('media-masked')
                    page.reload();expect(page.locator('#grid .card')).to_have_count(3)
                    expect(page.locator('html')).not_to_have_class('media-masked')
                    page.goto(base);expect(page.locator('#grid .card')).to_have_count(3)
                    expect(page.locator('html')).to_have_class('media-masked')
                    # Audio is a normal navigation link owned by the separate service.
                    context.route(base+'/audio/',lambda route:route.fulfill(content_type='text/html',body='<p>Generated Audio studio</p>'))
                    if width<500:page.locator('#nav-toggle').click()
                    page.locator('#audio-studio-link').click();page.wait_for_url(base+'/audio/')
                    expect(page.locator('body')).to_have_text('Generated Audio studio')
                    assert not errors,errors
                    context.close()
                browser.close()
            print('PRESETS_READER=PASS clean_paths=true legacy_bookmarks=true audio_link_preserved=true resume_start=true preset_save_edit_delete=true AND_filter=true cross_page_persistence=true desktop_mobile=true')
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
