"""Browser regression for catalog counts after direct NAS archive connection.

Generated records only; no NAS, external site or private media access.
"""
import json
import os
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch
from navigation_smoke import FixtureLRR
from server import Studio, make_server
from store import Store
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {'STUDIO_PASSWORD': 'synthetic-status-password'}):
        store = Store(Path(temporary) / 'studio.db')
        app = Studio(store, FixtureLRR())
        server = make_server('127.0.0.1', 0, app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
                context = browser.new_context(http_credentials={'username': 'admin', 'password': 'synthetic-status-password'})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                url = 'http://127.0.0.1:' + str(server.server_port)
                page.goto(url)
                page.wait_for_function('()=>document.querySelector("#library-status").textContent.includes("등록된 파일 0권")')
                for index in range(3):
                    store.create_work('Generated status book', lrr_id=str(index)*40)
                store.create_work('Generated metadata')
                with store.db() as db:
                    for index in range(2):
                        db.execute("INSERT INTO uploads(sha256,original_name,stored_name,bytes,created,lrr_id,state) VALUES(?,?,?,?,?,?,?)",
                            (str(index)*64, 'Generated.cbz', str(index)*64+'.cbz', 1, 1, '0'*40, 'indexed'))
                for width, height in [(1440, 900), (390, 844)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    page.reload()
                    page.wait_for_function('()=>document.querySelector("#library-status").textContent.includes("등록된 파일 3권")')
                    text = page.locator('#library-status').inner_text()
                    assert '업로드 기록이 연결된 파일 1권' in text and '정보만 등록 1권' in text
                    assert '추가 등록 후' not in text
                    page.locator('#folder-open').click()
                    assert '이미 연결된 NAS의 CBZ는 이 작업 없이' in page.locator('#folder-dialog').inner_text()
                    page.locator('#folder-dialog [data-close]').click()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.route('**/api/library/status', lambda route: route.fulfill(status=503, content_type='application/json', body=json.dumps({'error':'Synthetic unavailable'})))
                page.reload()
                page.wait_for_function('()=>document.querySelector("#library-status").textContent.includes("확인하지 못했습니다")')
                assert not errors, errors
                browser.close()
            print('library_status_browser=passed; empty/indexed/upload/metadata/error; desktop/mobile; synthetic_only=true')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
