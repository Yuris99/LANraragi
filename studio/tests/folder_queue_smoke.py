"""Independent real Studio/LRR + root queue + browser; generated media only."""
import base64
import hashlib
import io
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from PIL import Image
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_nas import prepare


def main():
    repo=Path(__file__).resolve().parents[2]
    root=Path(tempfile.mkdtemp(prefix='folder-queue-check.',dir=repo/'work'))
    project='library-studio-folder-queue-check'
    suffix=os.environ.get('STUDIO_FOLDER_QUEUE_RUN','')
    assert not suffix or re.fullmatch('[a-z0-9]{1,12}',suffix)
    if suffix:project+='-'+suffix
    env={k:v for k,v in os.environ.items() if k not in {'DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'}}
    docker=['docker','--host=unix:///var/run/docker.sock']
    def command(args,check=True,timeout=180):
        r=subprocess.run(args,cwd=repo,env=env,text=True,capture_output=True,timeout=timeout)
        if check and r.returncode:raise AssertionError((r.stdout,r.stderr))
        return r
    assert not command(docker+['ps','-aq','--filter','label=com.docker.compose.project='+project]).stdout.strip(),'Preserve an existing synthetic run; inspect first'
    def image(service):return command(docker+['inspect','--format','{{.Image}}','library-studio-folder-root-check-'+service+'-1']).stdout.strip()
    web_image=image('studio');lrr_image=image('lanraragi')
    source=root/'originals';source.mkdir(mode=0o700)
    (source/'manga').mkdir(mode=0o700);(source/'images').mkdir(mode=0o700)
    for number in range(12):
        book=source/'manga'/f'Generated Book {number:02}';book.mkdir(mode=0o700)
        for page,fmt,ext in [(1,'PNG','png'),(2,'JPEG','jpg'),(3,'WEBP','webp')]:
            output=io.BytesIO();Image.new('RGB',(320,480),(number*15,page*60,90)).save(output,format=fmt)
            path=book/f'{page}.{ext}';path.write_bytes(output.getvalue());path.chmod(0o600)
    for p in [source,*source.rglob('*')]:os.utime(p,(time.time()-120,)*2)
    def snapshot():return {str(p.relative_to(source)):(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mode,p.stat().st_uid,p.stat().st_gid,p.stat().st_mtime_ns) for p in source.rglob('*') if p.is_file()}
    original=snapshot();assert len(original)==36
    for name in ['library','inbox','library/downloads']:
        (root/name).mkdir(exist_ok=True);(root/name).chmod(0o755)
    prepare(root/'.env.nas',str(root/'library'),str(root/'library/downloads'),1026,100,lrr_image,web_image)
    values=dict(line.split('=',1) for line in (root/'.env.nas').read_text().splitlines())
    values['STUDIO_PORT']='43136';values['STUDIO_INBOX']=str(root/'inbox')
    (root/'.env.nas').write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
    control=root/'library-studio-folders';control.mkdir(mode=0o700)
    code=control/'code';code.mkdir(mode=0o755);(code/'web').mkdir(mode=0o755);code.chmod(0o755);(code/'web').chmod(0o755)
    manifest=repo/'studio/deploy/runtime-manifest.sha256'
    shutil.copyfile(manifest,code/'runtime-manifest.sha256')
    for line in manifest.read_text().splitlines():
        digest,name=line.split('  ',1);data=(repo/'studio'/name).read_bytes()
        assert hashlib.sha256(data).hexdigest()==digest
        (code/name).write_bytes(data);(code/name).chmod(0o644)
    overlay=root/'compose.code.json';overlay.write_text(json.dumps({'services':{'studio':{'volumes':[{'type':'bind','source':str(code),'target':'/app','read_only':True}]}}}))
    compose=docker+['compose','--env-file',str(root/'.env.nas'),'-p',project]
    for f in ['studio/compose.nas.yaml','studio/compose.cloud-runtime.yaml','studio/compose.import.yaml','studio/deploy/compose.pilot.yaml',str(overlay)]:compose+=['-f',f]
    command(compose+['up','-d'],timeout=180)
    def health(service):return command(docker+['inspect','--format','{{.State.Health.Status}}',project+'-'+service+'-1']).stdout.strip()
    for _ in range(60):
        if health('studio')=='healthy':break
        time.sleep(1)
    assert health('studio')=='healthy'
    started=command(docker+['inspect','--format','{{.State.StartedAt}}',project+'-lanraragi-1']).stdout
    text=(repo/'studio/deploy/tick-folder-queue.sh').read_text()
    text=text.replace('library-studio-folder-queue',project+'-queue')
    text=text.replace('case "$control" in /volume*/docker/library-studio-folders)','case "$control" in '+str(control)+')')
    text=text.replace('= 0:700 ]','= '+str(os.getuid())+':700 ]')
    text=text.replace('project=library-studio-nas-pilot','project='+project)
    text=text.replace('sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0',web_image)
    (control/'tick.sh').write_text(text)
    (control/'source.path').write_text(str(source)+'\n');(control/'writer').write_text('1026:100\n')
    (control/'controller.sha256').write_text(''.join(hashlib.sha256((control/p).read_bytes()).hexdigest()+'  '+p+'\n' for p in ['tick.sh','source.path','writer']))
    stubs=root/'bin';stubs.mkdir();(stubs/'id').write_text('#!/bin/sh\n[ "$1" = -u ] && printf "0\\n"\n');(stubs/'id').chmod(0o755)
    env['PATH']=str(stubs)+os.pathsep+env['PATH']
    def tick():return json.loads(command(['sh',str(control/'tick.sh')]).stdout.strip())
    base='http://127.0.0.1:43136'
    auth='Basic '+base64.b64encode(('admin:'+values['STUDIO_PASSWORD']).encode()).decode()
    def request(path,data=None):
        req=urllib.request.Request(base+path,headers={'Authorization':auth,'Content-Type':'application/json'},data=None if data is None else json.dumps(data).encode())
        with urllib.request.urlopen(req,timeout=30) as r:return r.read()
    denied=command(docker+['run','--rm','--pull=never','--network','none','--user','1026:100','--read-only',
        '--mount',f'type=bind,src={source},dst=/nas-library,readonly','--mount',f'type=bind,src={code},dst=/app,readonly',
        '--entrypoint','python',web_image,'/app/folder_importer.py','--operation','plan'],check=False)
    assert denied.returncode!=0
    errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        context=browser.new_context(http_credentials={'username':'admin','password':values['STUDIO_PASSWORD']},viewport={'width':1440,'height':1000})
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base);page.locator('#folder-open').click();page.wait_for_function('()=>document.querySelector("#folder-worker-status").textContent.includes("아직 연결")')
        assert page.locator('#folder-start').is_disabled()
        assert tick()['worker']=='ready'
        page.locator('#folder-refresh').click();page.wait_for_function('()=>!document.querySelector("#folder-start").disabled')
        page.locator('#folder-start').click();page.wait_for_function('()=>document.querySelector("#folder-jobs").textContent.includes("대기 중")')
        assert page.locator('#folder-start').is_disabled()
        assert tick()['worker']=='complete'
        page.locator('#folder-refresh').click();page.wait_for_function('()=>document.querySelector("#folder-jobs").textContent.includes("10권 추가")')
        assert len(json.loads(request('/api/uploads'))['items'])==10
        page.reload();page.locator('#folder-open').click();page.wait_for_function('()=>!document.querySelector("#folder-start").disabled')
        page.locator('#folder-start').click();page.locator('[data-folder-cancel]').wait_for();page.locator('[data-folder-cancel]').click()
        page.wait_for_function('()=>document.querySelector("#folder-jobs").textContent.includes("취소됨")')
        page.locator('#folder-start').click();page.locator('[data-folder-cancel]').wait_for();assert tick()['worker']=='complete'
        page.locator('#folder-refresh').click();page.wait_for_function('()=>document.querySelector("#folder-jobs").textContent.includes("2권 추가")')
        assert len(json.loads(request('/api/uploads'))['items'])==12
        page.locator('#folder-dialog [data-close]').click()
        # Real LANraragi indexing can lag the queue; drive only normal sync API.
        for _ in range(180):
            request('/api/uploads/sync',{})
            if json.loads(request('/api/works'))['total']==12:break
            time.sleep(1)
        assert json.loads(request('/api/works'))['total']==12
        page.reload();page.locator('.card').first.wait_for();assert page.locator('.card').count()==12
        page.locator('.card').first.click();page.locator('#read-work').click()
        page.wait_for_function('()=>document.querySelector("#reader-image").naturalWidth===320')
        page.locator('#reader-next').click();page.wait_for_function('()=>location.hash.endsWith("/2")')
        page.go_back();page.wait_for_function('()=>location.hash.endsWith("/1")')
        page.locator('#close-reader').click();page.locator('#close-detail').click()
        page.set_viewport_size({'width':390,'height':844});page.locator('#folder-open').click()
        assert page.locator('#folder-dialog').is_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        browser.close()
    uploads=json.loads(request('/api/uploads'))['items']
    for row in uploads:assert hashlib.sha256(request('/api/uploads/'+row['sha256']+'/download')).hexdigest()==row['sha256']
    assert snapshot()==original
    assert command(docker+['inspect','--format','{{.State.StartedAt}}',project+'-lanraragi-1']).stdout==started
    ownership=command(docker+['exec',project+'-studio-1','python','-c',"from pathlib import Path;assert all((p.stat().st_uid,p.stat().st_gid)==(1026,100) for d in ['/data','/uploads'] for p in [Path(d),*Path(d).rglob('*')]);print('outputs=1026:100')"]).stdout.strip()
    print(json.dumps({'folder_queue':'passed','root_reader':'actual RO/network-none container','copies':[10,2],
        'originals_unchanged':True,'downloads_verified':12,'reader_history':True,'desktop_mobile':True,
        'queue_cancel_reload':True,'ownership':ownership,'lrr_restarted':False,'page_errors':errors,'nas_deployment':False}))
    command(compose+['stop','studio','lanraragi'])


if __name__=='__main__':main()
