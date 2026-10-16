"""Synthetic-only browser integration against an isolated Compose stack."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from make_synthetic import create_fixture
from playwright.sync_api import sync_playwright

def main():
    env={}
    for line in (Path(__file__).resolve().parents[1]/'.env').read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            key,value=line.split('=',1);env[key]=value.strip().strip('"').strip("'")
    base='http://127.0.0.1:'+os.environ.get('STUDIO_SMOKE_PORT','43126')
    with tempfile.TemporaryDirectory() as directory:
        fixture=create_fixture(Path(directory)/'fixture')
        digest=hashlib.sha256(fixture.read_bytes()).hexdigest()
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            context=browser.new_context(http_credentials={'username':'admin','password':env['STUDIO_PASSWORD']})
            page=context.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base)
            page.locator('#upload').click()
            page.locator('#upload-files').set_input_files(str(fixture))
            page.locator('#upload-start').click()
            page.wait_for_function("() => document.querySelector('#upload-status').textContent.includes('완료')")
            page.locator('#upload-start').wait_for(state='visible')
            with page.expect_download() as event:
                page.locator('#upload-list a[download]').first.click()
            download=event.value
            assert hashlib.sha256(Path(download.path()).read_bytes()).hexdigest()==digest
            assert download.suggested_filename==fixture.name
            page.wait_for_function("() => !document.querySelector('#upload-files').disabled")
            stored_count=len(context.request.get(base+'/api/uploads').json()['items'])
            page.locator('#upload-files').set_input_files(str(fixture))
            page.locator('#upload-start').click()
            page.wait_for_function("() => document.querySelector('#upload-status').textContent.includes('이미 저장')")
            assert len(context.request.get(base+'/api/uploads').json()['items'])==stored_count
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                response=context.request.post(base+'/api/uploads/sync',data={})
                assert response.ok,response.status
                records=context.request.get(base+'/api/uploads').json()['items']
                if records and records[0].get('work_id'):break
                page.wait_for_timeout(1000)
            else:raise AssertionError('Synthetic upload was not indexed within 120 seconds')
            page.reload();page.locator('#upload').click()
            page.locator('[data-upload-work]').first.click()
            page.locator('#detail').get_by_text(fixture.stem,exact=True).first.wait_for(state='visible')
            page.locator('#read-work').click()
            page.locator('.reader-page .mosaic-layer:not([hidden])').wait_for(state='visible')
            assert page.locator('#reader-image').evaluate('(el) => getComputedStyle(el).opacity')=='0'
            for width in [390,1440]:
                page.set_viewport_size({'width':width,'height':900})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors,errors
            browser.close()
    print(json.dumps({'browser_upload':True,'duplicate_preserved':True,'download_sha256':True,
                      'actual_lanraragi_index':True,'reader_masked':True,'mobile_desktop':True,'page_errors':errors}))

if __name__=='__main__':main()
