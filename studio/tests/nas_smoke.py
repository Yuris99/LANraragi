"""Check the synthetic NAS candidate's ACTUAL Studio image over HTTP.

Only use a new isolated project containing the single generated synthetic CBZ.
"""
from concurrent.futures import ThreadPoolExecutor
import base64
import hashlib
import json
import os
from pathlib import Path
import statistics
import time
import urllib.request
from playwright.sync_api import sync_playwright


def main():
    root=Path(__file__).resolve().parents[1]
    env=dict(line.split('=',1) for line in (root/'.env').read_text().splitlines() if '=' in line)
    base='http://127.0.0.1:'+str(int(os.environ.get('STUDIO_SMOKE_PORT','43120')))
    auth='Basic '+base64.b64encode(('admin:'+env['STUDIO_PASSWORD']).encode()).decode()
    def request(path,body=None):
        headers={'Authorization':auth}
        if body is not None:headers['Content-Type']='application/json'
        req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        with urllib.request.urlopen(req,timeout=20) as response:return response.read()
    assert json.loads(request('/api/health'))['lanraragi_connected']
    request('/api/sync',{})
    catalog=json.loads(request('/api/works'))
    assert catalog['total']==1 and catalog['items'][0]['title']=='Synthetic Studio Book'
    work=catalog['items'][0];arcid=work['lrr_id']
    request('/api/works/'+work['id']+'/progress',{'page':1})
    data=request('/api/media/'+arcid+'/download')
    assert hashlib.sha256(data).digest()==hashlib.sha256((root/'data/library/Synthetic Studio Book.cbz').read_bytes()).digest()
    thumbnail='/api/media/'+arcid+'/thumbnail'
    def timing(_):
        start=time.perf_counter();data=request(thumbnail)
        assert len(data)>0
        return (time.perf_counter()-start)*1000
    cold=timing(0)
    with ThreadPoolExecutor(max_workers=4) as pool:samples=list(pool.map(timing,range(48)))
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        context=browser.new_context(http_credentials={'username':'admin','password':env['STUDIO_PASSWORD']})
        page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base);page.locator('.card').click();page.locator('#read-work').click()
        page.locator('#reader[open]').wait_for(state='visible')
        page.wait_for_function("() => document.querySelector('#reader-image').complete && document.querySelector('#reader-image').naturalWidth > 0")
        page.locator('#reader-next').click()
        page.wait_for_function("() => document.querySelector('#reader-position').textContent === '2 / 3'")
        for _ in range(30):
            if json.loads(request('/api/works/'+work['id']))['progress']==2:break
            page.wait_for_timeout(100)
        assert json.loads(request('/api/works/'+work['id']))['progress']==2
        page.locator('#close-reader').click();page.locator('#close-detail').click()
        page.locator('#settings-button').click();page.locator('#card-size').select_option('small')
        page.locator('#settings [data-close]').click();page.locator('#layout').click()
        page.reload();page.locator('#grid.list').wait_for()
        assert page.locator('#card-size').input_value()=='small'
        page.locator('#sort').select_option('title')
        for width,height in [(1440,1000),(390,844)]:
            page.set_viewport_size({'width':width,'height':height})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors,errors
        browser.close()
    print(json.dumps({'actual_studio_image':True,'synthetic_works':1,'download_hash_match':True,
          'reader_progress':2,'settings_persisted':True,'desktop_mobile':True,'page_errors':errors,
          'thumbnail_cold_ms':round(cold,2),'thumbnail_48_four_threads_median_ms':round(statistics.median(samples),2),
          'thumbnail_48_four_threads_p95_ms':round(sorted(samples)[45],2)}))


if __name__=='__main__':main()
