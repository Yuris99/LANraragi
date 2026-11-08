"""Generated metadata only: translation, touch/keyboard help, original links."""
import json
import mimetypes
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from server import Studio,make_server
from store import Store
from navigation_smoke import FixtureLRR


def main():
    mimetypes.add_type('text/javascript','.js')
    output=Path(__file__).resolve().parents[2]/'work/tag-language';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-tags'}):
        store=Store(Path(directory)/'catalog.db');store.set_automatic_enabled(False)
        work=store.create_work('Generated bilingual tags',lrr_id='a'*40,pages=7,tags=[
            'female:glasses','male:glasses','language:korean','parody:naruto','other:full color',
            'artist:unmapped artist','other:ai generated','other:ponytail','other:artbook',
            'other:a very long untranslated tag that must wrap without clipping',
            'constructor','other:<img src=x onerror=alert(1)>'])
        for provider,url in [('ehentai','https://e-hentai.org/g/123/abc/'),('exhentai','https://exhentai.org/g/123/abc/'),('hitomi','https://hitomi.la/manga/generated-456.html')]:
            store.upsert_source(work['id'],{'url':url,'tags':['female:glasses','language:korean']})
        store.upsert_source(work['id'],{'url':'https://nhentai.net/g/123/','tags':['female:glasses']})
        store.edit_user_tags([work['id']],['소장','date_added:123456','timestamp','source:generated'])
        snapshot=json.dumps(store.get_work(work['id']),sort_keys=True)
        server=make_server('127.0.0.1',0,Studio(store,FixtureLRR()))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path=os.environ.get('STUDIO_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
                for width in [1440,390]:
                    context=browser.new_context(http_credentials={'username':'admin','password':'generated-tags'},
                        viewport={'width':width,'height':960},is_mobile=width<500,has_touch=width<500,reduced_motion='reduce')
                    context.route('https://**/*',lambda route:route.fulfill(status=200,body='Generated external destination'))
                    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(base+'/manga');expect(page.locator('#grid .card')).to_have_count(1)
                    assert page.locator('[data-provider="nhentai"],[data-filter="nhentai"],option[value="nhentai"]').count()==0
                    assert page.locator('a[href*="nhentai.net"]').count()==0
                    label=page.locator('#tag-strip-list [data-tag-label="female:glasses"]')
                    expect(label).to_contain_text('안경')
                    expect(label).to_have_attribute('title','안경 · female:glasses\n인물이 안경을 착용합니다.\n여성 인물에 적용되는 태그 분류입니다.')
                    supplied=page.locator('#tag-strip-list [data-tag-label="language:korean"]')
                    expect(supplied).to_have_attribute('title','한국어 · language:korean\n한국어로 된(번역 포함) 작품.\n작품에 사용된 언어·번역 상태입니다.')
                    if width>=500:
                        before_hover=page.url
                        label.hover()
                        assert page.url==before_hover
                        expect(page.locator('#tag-explanation')).not_to_be_visible()
                    expect(page.locator('#grid .source-shortcut')).to_have_count(3)
                    for provider in ['ehentai','exhentai','hitomi']:
                        expect(page.locator('#grid use[href="#i-'+provider+'"]')).to_have_count(1)
                    page.locator('#grid .card-sources').screenshot(path=str(output/f'site-icons-{width}.png'))
                    original=page.url
                    with page.expect_popup() as popup:
                        page.locator('#grid .source-shortcut').first.click()
                    popup.value.close();assert page.url==original
                    expect(page.locator('#detail')).not_to_be_visible()
                    help=page.locator('#tag-strip-list [data-tag-info="female:glasses"]')
                    assert label.locator('.tag-value').evaluate('(el)=>parseFloat(getComputedStyle(el).fontSize)')>=14
                    if width<500:assert help.bounding_box()['height']>=44
                    if width<500:help.tap()
                    else:help.focus();page.keyboard.press('Enter')
                    expect(page.locator('#tag-explanation')).to_be_visible()
                    expect(page.locator('#tag-explanation-description')).to_have_text('인물이 안경을 착용합니다.')
                    expect(page.locator('#tag-explanation-title')).to_be_focused()
                    box=page.locator('#tag-explanation').bounding_box()
                    assert box['x']>=0 and box['x']+box['width']<=width
                    page.screenshot(path=str(output/f'explanation-{width}.png'))
                    page.locator('#tag-explanation [data-tag-language]').select_option('en')
                    expect(label).to_contain_text('glasses')
                    expect(supplied).to_contain_text('korean')
                    expect(supplied).to_have_attribute('title','한국어 · language:korean\n한국어로 된(번역 포함) 작품.\n작품에 사용된 언어·번역 상태입니다.')
                    page.locator('#close-tag-explanation').click()
                    page.reload();expect(label).to_contain_text('glasses')
                    page.locator('[data-tag-language]').first.select_option('ko')
                    page.locator('#tag-strip-search').fill('안경')
                    expect(page.locator('#tag-strip-list [data-strip-tag]')).to_have_count(2)
                    page.locator('#tag-strip-list [data-strip-tag="male:glasses"]').click()
                    expect(page.locator('#active-tag-name')).to_contain_text('안경')
                    assert 'male%3Aglasses' in page.url
                    filtered=page.url
                    page.locator('[data-tag-language]').first.select_option('en')
                    expect(page.locator('#active-tag-name')).to_contain_text('glasses')
                    assert page.url==filtered
                    page.locator('#grid .card-title').focus();page.keyboard.press('Enter')
                    expect(page.locator('#detail')).to_be_visible()
                    expect(page.locator('#combined-source-tags [data-tag-label="female:glasses"]')).to_contain_text('glasses')
                    page.locator('#combined-source-tags [data-tag-info="female:glasses"]').click()
                    page.locator('#tag-explanation [data-tag-language]').select_option('ko')
                    expect(page.locator('#detail')).to_be_visible()
                    expect(page.locator('#combined-source-tags [data-tag-label="female:glasses"]')).to_contain_text('안경')
                    page.locator('#close-tag-explanation').click()
                    page.locator('#combined-source-tags [data-tag-info="artist:unmapped artist"]').click()
                    expect(page.locator('#tag-explanation-translation')).to_contain_text('번역 미등록')
                    page.keyboard.press('Escape');expect(page.locator('#tag-explanation')).not_to_be_visible()
                    assert page.locator('#combined-source-tags img').count()==0
                    expect(page.locator('#connected-source-list .source-shortcut')).to_have_count(3)
                    assert page.locator('[data-user-filter="date_added:123456"],[data-user-filter="timestamp"],[data-user-filter="source:generated"]').count()==0
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    assert page.locator('#detail').evaluate('(el)=>el.scrollWidth <= el.clientWidth')
                    page.screenshot(path=str(output/f'detail-{width}.png'))
                    page.locator('#close-detail').click()
                    page.locator('#manage-tags').click()
                    expect(page.locator('#tag-catalog [data-manage-tag]')).to_have_count(1)
                    expect(page.locator('#tag-catalog')).not_to_contain_text('date_added')
                    page.locator('#tag-manager [data-close]').click()
                    page.locator('#tag-strip-search').fill('')
                    expect(page.locator('#tag-strip-list [data-strip-tag]')).to_have_count(13)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    for pair in page.locator('#tag-strip-list .tag-pair').all():
                        assert pair.evaluate('(el)=>el.scrollWidth <= el.clientWidth')
                    page.screenshot(path=str(output/f'library-{width}.png'),full_page=True)
                    # Display operations do not edit metadata, tags or source URLs.
                    assert json.dumps(store.get_work(work['id']),sort_keys=True)==snapshot
                    assert not errors,errors
                    context.close()
                # A dictionary failure must leave the library usable with raw tags.
                context=browser.new_context(http_credentials={'username':'admin','password':'generated-tags'})
                context.route('**/api/tag-dictionary',lambda route:route.fulfill(status=503,content_type='application/json',body='{"error":"Generated unavailable"}'))
                page=context.new_page();page.goto(base+'/manga')
                expect(page.locator('#grid .card')).to_have_count(1)
                expect(page.locator('#tag-strip-list [data-tag-label="female:glasses"]')).to_contain_text('glasses')
                context.close()
                browser.close()
            print(json.dumps({'translation':True,'ko_en_search':True,'exact_filters':True,'preference_persisted':True,
                'keyboard_touch_help':True,'source_shortcuts':3,'desktop_mobile':True,'metadata_unchanged':True}))
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
