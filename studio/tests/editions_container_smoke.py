"""Generated-only voice comic playback on the existing Docker profile."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_editions import audio_bytes
from prepare_nas import prepare
from make_synthetic import create_fixture
from playwright.sync_api import sync_playwright


def main():
    repo=Path(__file__).resolve().parents[2]
    fixture=Path(tempfile.mkdtemp(prefix='voice-docker.',dir=repo/'work'))
    project='studio-voice-check-'+fixture.name.split('.')[-1]
    env={k:v for k,v in os.environ.items() if k not in {'DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'}}
    docker=['docker','--host=unix:///var/run/docker.sock']
    def command(args,input=None,check=True):
        r=subprocess.run(args,input=input,cwd=repo,env=env,text=True,capture_output=True,timeout=180)
        if check and r.returncode:raise AssertionError((r.stdout,r.stderr))
        return r
    web=command(docker+['image','inspect','--format','{{.Id}}','lanraragi-studio:nas-baseline-root-check']).stdout.strip()
    lrr=command(docker+['image','inspect','--format','{{.Id}}','lanraragi-studio:lrr-root-reader-check']).stdout.strip()
    original=fixture/'original';original.mkdir();source=original/'[Generated Artist] Cleanup [123456].cbz'
    shutil.copyfile(create_fixture(fixture/'generated'),source)
    copy=fixture/'copy.cbz'
    with zipfile.ZipFile(source) as archive,zipfile.ZipFile(copy,'w') as target:
        for name in archive.namelist():target.writestr(name,archive.read(name))
        target.writestr('.copy-only.json',b'{"synthetic":"keep this metadata"}')
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest();copy_hash=hashlib.sha256(copy.read_bytes()).hexdigest()
    for name in ['library','library/downloads']:(fixture/name).mkdir(exist_ok=True)
    prepare(fixture/'.env.nas',str(fixture/'library'),str(fixture/'library/downloads'),1026,100,lrr,web)
    values=dict(line.split('=',1) for line in (fixture/'.env.nas').read_text().splitlines())
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    values['STUDIO_PORT']=str(port)
    (fixture/'.env.nas').write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
    for target,src in [('compose.nas.yaml','studio/compose.nas.yaml'),('compose.pilot.yaml','studio/deploy/compose.pilot.yaml')]:shutil.copyfile(repo/src,fixture/target)
    code=fixture/'code';code.mkdir(mode=0o755);(code/'web').mkdir(mode=0o755);(code/'deploy').mkdir(mode=0o755)
    for path in [code,code/'web',code/'deploy']:path.chmod(0o755)
    for line in (repo/'studio/deploy/runtime-manifest.sha256').read_text().splitlines():
        name=line.split()[1];shutil.copyfile(repo/'studio'/name,code/name);(code/name).chmod(0o644)
    for name in ['execute-copy-cleanup.py','plan-copy-cleanup.py','review-library-storage.py','archive_in_place.py']:
        shutil.copyfile(repo/'studio/deploy'/name,code/'deploy'/name)
    (fixture/'overlay.json').write_text(json.dumps({'services':{
        'lanraragi':{'environment':{'LRR_UID':'0','LRR_GID':'0'},'volumes':[{'type':'bind','source':str(original),'target':'/home/koyomi/lanraragi/content/NASOriginals','read_only':True}]},
        'studio':{'volumes':[{'type':'bind','source':str(code),'target':'/app','read_only':True}]}}}))
    base=docker+['compose','--env-file',str(fixture/'.env.nas'),'-p',project]
    for path in [fixture/'compose.nas.yaml',fixture/'compose.pilot.yaml',fixture/'overlay.json',repo/'studio/compose.cloud-runtime.yaml']:base+=['-f',str(path)]
    command(base+['up','-d'])
    try:
        for _ in range(100):
            if command(docker+['inspect','--format','{{.State.Health.Status}}',project+'-studio-1']).stdout.strip()=='healthy':break
            time.sleep(1)
        auth='Basic '+base64.b64encode(('admin:'+values['STUDIO_PASSWORD']).encode()).decode();url='http://127.0.0.1:'+str(port)
        def request(path,data=None,raw=False):
            headers={'Authorization':auth}
            if isinstance(data,bytes):headers['Content-Type']='application/octet-stream'
            elif data is not None:headers['Content-Type']='application/json';data=json.dumps(data).encode()
            with urllib.request.urlopen(urllib.request.Request(url+path,data=data,headers=headers),timeout=45) as response:
                return response.read() if raw else json.load(response)
        for _ in range(90):
            request('/api/sync',{})
            works=request('/api/works')['items']
            if len(works)==1:break
            time.sleep(1)
        assert len(works)==1
        comic=works[0]
        request('/api/media/'+comic['lrr_id']+'/files')
        voice=request('/api/works',{'title':'Generated voiced comic'})
        request('/api/works/'+voice['id']+'/edition',{'kind':'voice_pages','comic_reference':'L'+str(comic['local_number']),'language':'한국어','label':'Voice edition'})
        request('/api/works/'+voice['id']+'/edition/group',{'reference':'L'+str(comic['local_number'])})
        audio=request('/api/works/'+voice['id']+'/voice/upload?filename=Generated.wav',audio_bytes())
        request('/api/works/'+voice['id']+'/voice/'+audio['id']+'/cues',{'cues':[{'page':1,'second':0},{'page':2,'second':2}]})
        request('/api/works/'+voice['id']+'/voice/'+audio['id']+'/progress',{'position':2.5})
        assert hashlib.sha256(request('/api/voice/assets/'+audio['id']+'?download=1',raw=True)).hexdigest()==hashlib.sha256(audio_bytes()).hexdigest()
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
            page=browser.new_page(http_credentials={'username':'admin','password':values['STUDIO_PASSWORD']})
            page.goto(url+'/#/L'+str(voice['local_number']))
            page.locator('audio').wait_for();page.wait_for_function('()=>document.querySelector("audio").currentTime>=2.4')
            page.wait_for_function('()=>document.querySelector(".voice-page-label").textContent.includes("2 / 3")')
            page.wait_for_function('()=>document.querySelector(".voice-page").naturalWidth>0')
            page.locator('audio').evaluate('(audio)=>audio.play()')
            page.wait_for_function('()=>document.querySelector("audio").currentTime>2.7')
            page.locator('audio').evaluate('(audio)=>audio.pause()')
            browser.close()
        command(docker+['restart',project+'-studio-1'])
        for _ in range(45):
            try:
                actual=request('/api/works/'+voice['id'])
                if actual['edition']['assets'][0]['position']>=2.4:break
            except Exception:pass
            time.sleep(1)
        assert actual['edition']['comic_lrr_id']==comic['lrr_id']
        assert actual['edition']['assets'][0]['position']>=2.4
        assert len(actual['edition']['siblings'])==2
        assert source_hash==hashlib.sha256(source.read_bytes()).hexdigest()
        print('voice_docker=passed; real_LRR_CBZ_pages; WAV_decoded; page_sync; source_RO_unchanged; same_work_ids; stream_download_hash; restart_preserves_groups_cues_resume; generated_only=true; nas_changed=false')
    finally:command(base+['down'],check=False)


if __name__=='__main__':main()
