"""Check the isolated Compose inbox fixture; never accesses a NAS."""
import base64
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

def main():
    studio=Path(__file__).resolve().parents[1]
    fixture=studio/'data/tag-inbox/Synthetic Studio Book.cbz'
    original=fixture.read_bytes();sha=hashlib.sha256(original).hexdigest()
    env=dict(line.split('=',1) for line in (studio/'.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
    base='http://127.0.0.1:'+os.environ.get('STUDIO_SMOKE_PORT','43126')
    authorization='Basic '+base64.b64encode(('admin:'+env['STUDIO_PASSWORD']).encode()).decode()
    def get(path):
        return urllib.request.urlopen(urllib.request.Request(base+path,headers={'Authorization':authorization}),timeout=10)
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        try:
            with get('/api/uploads') as response:items=json.load(response)['items']
            match=next((item for item in items if item['sha256']==sha),None)
            if match and match.get('work_id'):break
        except OSError:pass
        time.sleep(1)
    else:raise AssertionError('Inbox fixture was not automatically indexed')
    with get('/api/uploads/'+sha+'/download') as response:assert hashlib.sha256(response.read()).hexdigest()==sha
    assert fixture.read_bytes()==original
    assert sum(item['sha256']==sha for item in items)==1
    print(json.dumps({'automatic_inbox_index':True,'original_unchanged':True,'download_hash':True,'one_upload_record':True}))

if __name__=='__main__':main()
