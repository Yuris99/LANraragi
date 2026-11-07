"""Local browser coverage of detail facets and manual series with generated books."""
import mimetypes
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
from playwright.sync_api import sync_playwright,expect
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from store import Store
from server import Studio,make_server
from navigation_smoke import FixtureLRR


def main():
    mimetypes.add_type('text/javascript','.js')
    output=Path(__file__).resolve().parents[2]/'work/tag-language/app33';output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ.get('STUDIO_TEST_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
        for width in (1440,390):
            with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-series'}):
                store=Store(Path(directory)/'catalog.db');store.set_automatic_enabled(False)
                a=store.create_work('Generated first','Fixture',lrr_id='a'*40,pages=7,tags=['parody:story','female:glasses'])
                b=store.create_work('Generated second',lrr_id='b'*40,pages=7)
                store.upsert_source(b['id'],{'url':'https://e-hentai.org/g/123/abc/','tags':['artist:Fixture','series:story','female:glasses']})
                c=store.create_work('Generated other','Fixture extra')
                server=make_server('127.0.0.1',0,Studio(store,FixtureLRR()))
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                base='http://127.0.0.1:'+str(server.server_port)
                context=browser.new_context(http_credentials={'username':'admin','password':'generated-series'},viewport={'width':width,'height':960},is_mobile=width<500,has_touch=width<500)
                try:
                    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(base+'/manga/L1');expect(page.locator('#detail-facets')).to_be_visible()
                    page.screenshot(path=str(output/f'detail-facets-{width}.png'))
                    page.locator('[data-browse-artist="Fixture"]').click()
                    expect(page.locator('#grid .card')).to_have_count(2)
                    assert parse_qs(urlsplit(page.url).query)['artist']==['Fixture']
                    page.reload();expect(page.locator('#grid .card')).to_have_count(2)
                    page.go_back();expect(page.locator('#detail[open]')).to_be_visible()
                    page.locator('#detail-facets [data-tag="parody:story"]').click()
                    expect(page.locator('#grid .card')).to_have_count(2)
                    assert parse_qs(urlsplit(page.url).query)['all_tag']==['parody:story']
                    page.goto(base+'/manga/L1');page.locator('#combined-source-tags [data-tag="female:glasses"]').click()
                    expect(page.locator('#grid .card')).to_have_count(2)
                    page.goto(base+'/manga/L1');page.locator('#work-series summary').click()
                    form=page.locator('#work-series-form');form.locator('[name="name"]').fill('Generated <story>')
                    form.locator('[type="submit"]').click()
                    expect(page.locator('.series-membership [data-browse-series]')).to_have_text('Generated <story> · 1작품')
                    series=store.list_series()[0]['id']
                    page.goto(base+'/manga/E123');page.locator('#work-series summary').click()
                    form.locator('[name="series_id"]').select_option(series)
                    expect(form.locator('[name="name"]')).not_to_be_visible()
                    form.locator('[type="submit"]').click()
                    expect(page.locator('.series-membership [data-browse-series]')).to_have_text('Generated <story> · 2작품')
                    page.locator('[data-browse-series="'+series+'"]').click()
                    expect(page.locator('#grid .card')).to_have_count(2)
                    assert page.locator('#grid .card').evaluate_all('(items)=>items.map(el=>el.dataset.id)')==[a['id'],b['id']]
                    expect(page.locator('#sort')).to_have_value('series')
                    page.reload();expect(page.locator('#grid .card')).to_have_count(2)
                    page.locator('#grid .card').first.click()
                    position=page.locator('.series-position[data-series-id="'+series+'"]')
                    position.locator('[name="position"]').fill('3');position.locator('[type="submit"]').click()
                    expect(page.locator('.series-position [name="position"]')).to_have_value('3')
                    page.screenshot(path=str(output/f'detail-series-{width}.png'))
                    assert page.locator('#detail').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
                    page.locator('[data-browse-series="'+series+'"]').click()
                    expect(page.locator('#grid .card')).to_have_count(2)
                    assert page.locator('#grid .card').evaluate_all('(items)=>items.map(el=>el.dataset.id)')==[b['id'],a['id']]
                    page.screenshot(path=str(output/f'series-list-{width}.png'))
                    page.locator('#grid .card').first.click();page.locator('[data-series-remove="'+series+'"]').click()
                    expect(page.locator('.series-membership')).to_have_count(0)
                    page.goto(base+'/manga?series='+series+'&sort=series&direction=asc')
                    expect(page.locator('#grid .card')).to_have_count(1)
                    page.locator('[data-clear-facet="series"]').click();expect(page.locator('#grid .card')).to_have_count(3)
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert store.get_work(b['id'])['sources'][0]['url']=='https://e-hentai.org/g/123/abc/'
                    assert store.get_work(a['id'])['edition']['group_id'] is None
                    assert not errors,errors
                finally:
                    context.close();server.shutdown();server.server_close();thread.join(timeout=3)
        browser.close()
    print('SERIES_UI=PASS artist/tag/parody click, exact filters, history/reload, create/join/order/remove, desktop/mobile, original sources/editions preserved')


if __name__=='__main__':main()
