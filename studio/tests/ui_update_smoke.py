"""Exercise NAS updater apply/rollback on the guarded cloud synthetic project.

Only deployment constants, NAS path guard and curl/id are fixture adapters.
All Docker operations, database backup, code mount, UI and rollback are real.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from playwright.sync_api import sync_playwright


def main():
    repository=Path(__file__).resolve().parents[2]
    fixture=repository/'work/folder-root-check'
    source=fixture/'originals'
    expected={'manga/Synthetic Folder/1.png','manga/Synthetic Folder/2.jpg','manga/Synthetic Folder/3.webp'}
    assert {str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}==expected
    project='library-studio-folder-root-check'
    root=Path(tempfile.mkdtemp(prefix='ui-update-check.',dir=repository/'work'))
    env={k:v for k,v in os.environ.items() if k not in {'DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'}}
    docker=['docker','--host=unix:///var/run/docker.sock']
    def command(args,**kwargs):
        result=subprocess.run(args,cwd=repository,env=env,capture_output=True,text=True,timeout=130,**kwargs)
        if result.returncode:raise AssertionError((result.stdout,result.stderr))
        return result.stdout
    image=command(docker+['inspect','--format','{{.Image}}',project+'-studio-1']).strip()
    lrr_started=command(docker+['inspect','--format','{{.State.StartedAt}}',project+'-lanraragi-1']).strip()
    shutil.copyfile(fixture/'.env.nas',root/'.env.nas');(root/'.env.nas').chmod(0o600)
    (root/'inbox').mkdir()
    with (root/'.env.nas').open('a') as stream:stream.write('STUDIO_INBOX='+str(root/'inbox')+'\n')
    for source_file,destination in [('studio/compose.nas.yaml','compose.nas.yaml'),('studio/compose.import.yaml','compose.import.yaml'),('studio/deploy/compose.pilot.yaml','compose.pilot.yaml')]:
        shutil.copyfile(repository/source_file,root/destination)
    manifest=repository/'studio/deploy/runtime-manifest.sha256'
    digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
    text=(repository/'studio/deploy/update-studio-ui.sh').read_text()
    text=text.replace('library-studio-nas-pilot',project)
    text=text.replace('sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0',image)
    text=text.replace('case "$root" in /volume*/docker/library-studio)', 'case "$root" in '+str(root)+')')
    text=text.replace('volume=${root%/docker/library-studio};number=${volume#/volume}', 'volume=/volume1;number=1')
    text=text.replace('revision=REPLACE_WITH_TESTED_REVISION','revision='+'1'*40)
    text=text.replace('manifest_sha=REPLACE_WITH_TESTED_MANIFEST_DIGEST','manifest_sha='+digest)
    # Also support running after the production helper has been pinned.
    import re
    text=re.sub(r'^revision=[0-9a-f]{40}$','revision='+'1'*40,text,flags=re.M)
    text=re.sub(r'^manifest_sha=[0-9a-f]{64}$','manifest_sha='+digest,text,flags=re.M)
    text=text.replace('=="43120"','=="43134"')
    helper=root/'update-fixture.sh';helper.write_text(text)
    stubs=root/'bin';stubs.mkdir()
    (stubs/'id').write_text('#!/bin/sh\n[ "$1" = -u ] && printf "0\\n"\n')
    (stubs/'id').chmod(0o755)
    (stubs/'curl').write_text('#!'+sys.executable+'\n'+
        'from pathlib import Path\nimport shutil,sys\n'+
        'args=sys.argv[1:];url=next(a for a in args if a.startswith("https://"));target=args[args.index("-o")+1]\n'+
        'prefix="https://raw.githubusercontent.com/Yuris99/LANraragi/'+('1'*40)+'/studio/"\n'+
        'assert url.startswith(prefix);relative=url[len(prefix):];assert ".." not in relative\n'+
        'shutil.copyfile(Path('+repr(str(repository/'studio'))+')/relative,target)\n'+
        'import os\nif os.environ.get("STUDIO_TEST_TAMPER")=="1" and relative=="web/app.js":\n with open(target,"a") as stream:stream.write("corrupt fixture")\n')
    (stubs/'curl').chmod(0o755)
    env['PATH']=str(stubs)+os.pathsep+env['PATH']
    values=dict(line.split('=',1) for line in (root/'.env.nas').read_text().splitlines() if '=' in line)
    assert values['STUDIO_PORT']=='43134'
    base='http://127.0.0.1:43134'
    auth='Basic '+base64.b64encode(('admin:'+values['STUDIO_PASSWORD']).encode()).decode()
    def request(path,body=None):
        req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':auth,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=20) as response:return response.read()
    before=json.loads(request('/api/uploads'))['items'];assert len(before)==1
    archive_sha=before[0]['sha256']
    assert hashlib.sha256(request('/api/uploads/'+archive_sha+'/download')).hexdigest()==archive_sha
    apply=command(['sh',str(helper),'apply',str(root)])
    assert '"studio_update": "complete"' in apply
    assert json.loads(request('/api/library/status'))['folder_archives']==1
    assert command(docker+['inspect','--format','{{.State.StartedAt}}',project+'-lanraragi-1']).strip()==lrr_started
    request('/api/sync',{});catalog=json.loads(request('/api/works'));assert catalog['total']==1
    work=catalog['items'][0];request('/api/works/'+work['id']+'/progress',{'page':1})
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        context=browser.new_context(http_credentials={'username':'admin','password':values['STUDIO_PASSWORD']})
        page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base);page.locator('.card img').wait_for()
        assert page.locator('.card img').evaluate('(el)=>getComputedStyle(el).filter')=='blur(10px)'
        assert page.locator('.card img').evaluate('(el)=>getComputedStyle(el).objectFit')=='contain'
        assert page.locator('.card canvas').count()==0
        assert 'NAS 폴더에서 1권' in page.locator('#library-status').inner_text()
        page.locator('.card').click();assert page.locator('#detail img').evaluate('(el)=>getComputedStyle(el).opacity')=='1'
        page.locator('#read-work').click()
        for number in range(1,4):
            if number>1:page.locator('#reader-next').click()
            page.wait_for_function('(n)=>document.querySelector("#reader-position").textContent===n+" / 3"',arg=number)
            page.wait_for_function('()=>document.querySelector("#reader-image").complete && document.querySelector("#reader-image").naturalWidth===320')
            assert page.locator('#reader-image').evaluate('(el)=>getComputedStyle(el).opacity')=='1'
        assert page.url.endswith('/read/3')
        page.go_back();page.wait_for_url('**/read/2')
        page.wait_for_function('()=>document.querySelector("#reader-position").textContent==="2 / 3"')
        page.go_forward();page.wait_for_url('**/read/3');page.reload()
        page.locator('#reader[open]').wait_for()
        page.wait_for_function('()=>document.querySelector("#reader-position").textContent==="3 / 3"')
        page.locator('#close-reader').click();page.locator('#detail[open]').wait_for()
        assert '/read/' not in page.url and '/works/' in page.url
        page.locator('#close-detail').click()
        page.locator('#settings-button').click();page.locator('#thumbnail-blur').uncheck()
        page.locator('#settings [data-close]').click();page.reload();page.locator('.card').wait_for()
        assert page.locator('.card img').evaluate('(el)=>getComputedStyle(el).filter')=='none'
        page.locator('#download-open').click();assert '검증 전' in page.locator('#download-support').inner_text()
        assert not errors,errors
        browser.close()
    assert hashlib.sha256(request('/api/uploads/'+archive_sha+'/download')).hexdigest()==archive_sha
    backups=[p for p in root.iterdir() if p.name.startswith('ui-update-backup.')]
    assert len(backups)==1 and json.loads((backups[0]/'sqlite-backup.json').read_text())['sha256']
    def code_mount():
        return command(docker+['inspect','--format','{{range .Mounts}}{{if eq .Destination "/app"}}{{.Source}}{{end}}{{end}}',project+'-studio-1']).strip()
    first_code=code_mount();assert first_code
    # Simulate the older installed overlay, which has no rollback metadata.
    overlay=root/'compose.ui.yaml'
    legacy='\n'.join(row for row in overlay.read_text().splitlines() if not row.startswith('# previous-ui-overlay '))+'\n'
    overlay.write_text(legacy)
    env['STUDIO_TEST_TAMPER']='1'
    tampered=subprocess.run(['sh',str(helper),'apply',str(root)],cwd=repository,env=env,capture_output=True,text=True,timeout=130)
    env.pop('STUDIO_TEST_TAMPER')
    assert tampered.returncode!=0 and 'FAILED' in tampered.stdout
    assert overlay.read_text()==legacy and code_mount()==first_code
    assert len(list(root.glob('ui-update-backup.*')))==1
    assert hashlib.sha256(request('/api/uploads/'+archive_sha+'/download')).hexdigest()==archive_sha
    upgrade=command(['sh',str(helper),'apply',str(root)])
    assert '"studio_update": "complete"' in upgrade and code_mount()!=first_code
    assert len(list(root.glob('ui-update-backup.*')))==2
    assert hashlib.sha256(request('/api/uploads/'+archive_sha+'/download')).hexdigest()==archive_sha
    rolled=command(['sh',str(helper),'rollback',str(root)]);assert 'rolled back' in rolled
    assert code_mount()==first_code and overlay.read_text()==legacy
    for _ in range(30):
        try:
            if json.loads(request('/api/library/status'))['folder_archives']==1:break
        except Exception:pass
        time.sleep(1)
    else:raise AssertionError('First rollback must restore the previous reviewed UI')
    rolled=command(['sh',str(helper),'rollback',str(root)]);assert 'rolled back' in rolled
    assert not code_mount() and not overlay.exists()
    for _ in range(30):
        try:
            if json.loads(request('/api/health'))['lanraragi_connected']:break
        except Exception:pass
        time.sleep(1)
    assert hashlib.sha256(request('/api/uploads/'+archive_sha+'/download')).hexdigest()==archive_sha
    try:request('/api/library/status')
    except urllib.error.HTTPError as error:assert error.code==404
    else:raise AssertionError('Rollback must restore the old server code')
    assert command(docker+['inspect','--format','{{.State.StartedAt}}',project+'-lanraragi-1']).strip()==lrr_started
    print(json.dumps({'real_apply_and_rollback':True,'prior_sqlite_backup':True,'legacy_image_reused':True,
                      'lrr_not_restarted':True,'data_download_hash_preserved':True,'thumbnail_blur':True,'cover_fit_contain':True,
                      'reader_history_reload_and_detail_url':True,'existing_overlay_upgrade':True,'two_step_code_rollback':True,'hash_failure_preserves_existing_ui':True,
                      'detail_reader_original':True,'settings_persisted':True,'nas_folder_count':True,'page_errors':errors}))


if __name__=='__main__':main()
