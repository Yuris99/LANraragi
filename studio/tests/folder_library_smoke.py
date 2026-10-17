"""Real Docker/LANraragi + browser test of synthetic-only image folders.

Requires the isolated library-studio-folder-check project and its ignored
work/folder-check configuration. Never point this test at a personal library.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import zipfile
from playwright.sync_api import sync_playwright


def main():
    repository=Path(__file__).resolve().parents[2]
    pilot=os.environ.get('STUDIO_SMOKE_PILOT')=='1'
    root=repository/('work/folder-pilot-check' if pilot else 'work/folder-check');source=root/'originals'
    project='library-studio-folder-pilot-check' if pilot else 'library-studio-folder-check'
    expected={'manga/Synthetic Folder/1.png','manga/Synthetic Folder/2.jpg','manga/Synthetic Folder/3.webp'}
    def snapshot():
        return {str(p.relative_to(source)):(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mode,p.stat().st_mtime_ns)
                for p in source.rglob('*') if p.is_file()}
    before=snapshot();assert set(before)==expected,'Use only the isolated synthetic fixture'
    values=dict(line.split('=',1) for line in (root/'.env.nas').read_text().splitlines() if '=' in line)
    base='http://127.0.0.1:'+values['STUDIO_PORT']
    assert values['STUDIO_PORT']==('43132' if pilot else '43130') and values['STUDIO_FOLDER_SOURCE']==str(source)
    headers={'Authorization':'Basic '+base64.b64encode(('admin:'+values['STUDIO_PASSWORD']).encode()).decode()}
    def request(path,data=None):
        req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),
                                   headers={**headers,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=45) as response:return response.read()
    docker=['docker','--host=unix:///var/run/docker.sock']
    compose=docker+['compose','--env-file',str(root/'.env.nas'),'-p',project,
                    '-f','studio/compose.nas.yaml','-f','studio/compose.cloud-runtime.yaml',
                    '-f','studio/deploy/compose.pilot.yaml','-f','studio/compose.folders.yaml']
    environment={k:v for k,v in os.environ.items() if k not in {'DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'}}
    environment['STUDIO_FOLDER_READ_GROUP']='101'  # Isolated fixture selector.
    def command(args):
        result=subprocess.run(args,cwd=repository,env=environment,capture_output=True,text=True,timeout=90)
        assert result.returncode==0,(result.stdout,result.stderr)
        return result.stdout
    assert json.loads(request('/api/health'))['lanraragi_connected']
    initial=json.loads(request('/api/uploads'))['items']
    assert len(initial)<=1 and all(row['original_name']=='Synthetic Folder.cbz' for row in initial)
    plan=json.loads(command(compose+['run','--rm','--no-deps','folder-import','--operation','plan']))
    assert plan['ready']==1 and plan['pages']==3 and plan['imported']==0 and plan['errors']==0,plan
    assert json.loads(request('/api/uploads'))['items']==initial
    check="import errno,os,socket;assert (os.getuid(),os.getgid())==(1026,100);assert [name for _,name in socket.if_nameindex()]==['lo'];\ntry: os.open('/nas-library/.write-probe',os.O_CREAT|os.O_WRONLY,0o600)\nexcept OSError as error: assert error.errno==errno.EROFS\nelse: raise AssertionError('Source is writable')"
    command(compose+['run','--rm','--no-deps','--entrypoint','python','folder-import','-c',check])
    if initial and not pilot:
        # Reproduce a crash after CBZ publication but before its receipt commit
        # in this strictly guarded, synthetic-only project's SQLite database.
        recover="import sqlite3;db=sqlite3.connect('/data/studio.db');assert db.execute(\"SELECT count(*) FROM works WHERE title!='Synthetic Folder'\").fetchone()[0]==0;db.execute(\"DELETE FROM folder_imports WHERE path='manga/Synthetic Folder'\");db.execute(\"DELETE FROM settings WHERE key LIKE 'folder-scan:%'\");db.commit()"
        command(docker+['exec',project+'-studio-1','python','-c',recover])
    operation='pilot' if pilot else 'import'
    result=json.loads(command(compose+['run','--rm','--no-deps','folder-import','--operation',operation,'--limit','1']))
    assert result['imported']==(0 if pilot and initial else 1) and result['errors']==0,result
    if pilot:assert result['fixed_selection'] and result['backup'].startswith('folder-pilot-backups/')
    uploads=json.loads(request('/api/uploads'))['items'];assert len(uploads)==1
    download=request('/api/uploads/'+uploads[0]['sha256']+'/download')
    assert hashlib.sha256(download).hexdigest()==uploads[0]['sha256']
    with zipfile.ZipFile(io.BytesIO(download)) as cbz:
        for index,suffix in [(1,'png'),(2,'jpg'),(3,'webp')]:
            assert cbz.read(f'{index:06d}.{suffix}')==(source/f'manga/Synthetic Folder/{index}.{suffix}').read_bytes()
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        request('/api/uploads/sync',{})
        records=json.loads(request('/api/uploads'))['items']
        if records[0].get('work_id'):break
        time.sleep(1)
    else:raise AssertionError('LANraragi did not index the synthetic folder archive')
    catalog=json.loads(request('/api/works'));assert catalog['total']==1
    assert 'folder:manga/Synthetic Folder' in catalog['items'][0]['user_tags']
    request('/api/works/'+catalog['items'][0]['id']+'/progress',{'page':1})
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        context=browser.new_context(http_credentials={'username':'admin','password':values['STUDIO_PASSWORD']})
        page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base);page.locator('.card').click();page.locator('#read-work').click()
        for number in range(1,4):
            if number>1:page.locator('#reader-next').click()
            page.wait_for_function('(number) => document.querySelector("#reader-position").textContent === number+" / 3"',arg=number)
            page.wait_for_function('() => document.querySelector("#reader-image").complete && document.querySelector("#reader-image").naturalWidth === 320')
        assert not errors,errors
        browser.close()
    for _ in range(2):
        again=json.loads(command(compose+['run','--rm','--no-deps','folder-import','--operation',operation]))
        assert again['imported']==0 and again['errors']==0,again
        if pilot:assert again['fixed_selection'] and again['unchanged']==1
    assert len(json.loads(request('/api/uploads'))['items'])==1
    assert snapshot()==before,'Original bytes, timestamps and permissions must be preserved'
    print(json.dumps(dict(readonly_source=True,plan_no_uploads=True,nas_uid_gid='1026:100',
                         original_bytes_metadata_preserved=True,actual_lanraragi_index=True,
                         png_jpeg_webp_reader=True,folder_tag=True,download_hash_match=True,
                         restart_duplicate_preserved=True,pinned_pilot_with_backup=pilot,page_errors=errors)))


if __name__=='__main__':main()
