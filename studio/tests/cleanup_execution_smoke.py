"""Synthetic-only full LRR/Studio cleanup rehearsal. Never use personal services."""
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
from prepare_nas import prepare
from make_synthetic import create_fixture
from playwright.sync_api import sync_playwright


def main():
    repo=Path(__file__).resolve().parents[2]
    fixture=Path(tempfile.mkdtemp(prefix='cleanup-exec.',dir=repo/'work'))
    project='studio-cleanup-check-'+fixture.name.split('.')[-1]
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
        request('/api/uploads?filename=Generated%20copy.cbz',copy.read_bytes())
        for _ in range(90):
            request('/api/sync',{})
            works=request('/api/works')['items']
            if len(works)==2:break
            time.sleep(1)
        assert len(works)==2
        old=next(w for w in works if w['archive_filename']=='Generated copy.cbz')
        survivor=next(w for w in works if w['id']!=old['id'])
        request('/api/media/'+old['lrr_id']+'/files')
        request('/api/works/'+old['id'],{'favorite':True,'rating':4})
        request('/api/works/'+old['id']+'/sources',{'url':'https://nhentai.net/g/123456/','comments':[{'id':'1','text':'Generated preserved comment'}]})
        request('/api/works/'+old['id']+'/progress',{'page':2})
        report=fixture/'reports';report.mkdir()
        def run_tool(script,args):
            run=docker+['run','--rm','--pull=never','--user','0:0','--network','none','--read-only','--memory','256m','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--cap-add','SETUID','--cap-add','SETGID','--security-opt','no-new-privileges:true']
            for mount in [f'type=bind,src={code},dst=/tools,readonly',f'type=bind,src={original},dst=/nas-library,readonly',f'type=bind,src={report},dst=/reports',f'type=volume,src={project}_studio-data,dst=/data',f'type=volume,src={project}_studio-uploads,dst=/copies']:
                run+=['--mount',mount]
            return command(run+['--entrypoint','python',web,'-B','/tools/deploy/'+script,*args])
        run_tool('review-library-storage.py',['--library-root','/nas-library','--copies-root','/copies','--report','/reports/review.json'])
        common=['--database','/data/studio.db','--library-root','/nas-library','--copies-root','/copies','--workspace','/reports','--manifest','/reports/execution.json']
        run_tool('execute-copy-cleanup.py',['prepare',*common,'--prior-report','/reports/review.json'])
        request('/api/works/'+old['id'],{'favorite':True})  # prepare must not create root-owned WAL/SHM
        request_text=command(docker+['run','--rm','--pull=never','--network','none','--user','0:0','--mount',f'type=bind,src={report},dst=/reports,readonly','--entrypoint','cat',web,'/reports/execution.request.json']).stdout
        verifier='import os,json,sys;from server import LRR,verify_cleanup_downloads;print(json.dumps(verify_cleanup_downloads(LRR(os.environ["LRR_URL"],os.environ["LRR_API_KEY"]),json.load(sys.stdin))))'
        proof=command(docker+['exec','-i',project+'-studio-1','python','-B','-c',verifier],input=request_text).stdout
        (report/'proof.json').write_text(proof);(report/'proof.json').chmod(0o600)
        before=command(docker+['inspect','--format','{{.Id}}|{{.State.StartedAt}}',project+'-lanraragi-1']).stdout
        command(docker+['stop','--time','20',project+'-studio-1'])
        result=run_tool('execute-copy-cleanup.py',['apply',*common,'--proof','/reports/proof.json','--writer-uid','1026','--writer-gid','100'])
        assert json.loads(result.stdout.splitlines()[-1])['removed']==1,result.stdout
        assert source_hash==hashlib.sha256(source.read_bytes()).hexdigest()
        assert before==command(docker+['inspect','--format','{{.Id}}|{{.State.StartedAt}}',project+'-lanraragi-1']).stdout
        command(docker+['start',project+'-studio-1'])
        for _ in range(45):
            try:
                if request('/api/works')['total']==1:break
            except Exception:pass
            time.sleep(1)
        assert request('/api/works')['total']==1
        actual=request('/api/works/'+old['id']);assert actual['id']==survivor['id'] and actual['favorite'] and actual['progress']==2
        assert actual['sources'][0]['comments'][0]['text']=='Generated preserved comment'
        assert hashlib.sha256(request('/api/media/'+actual['lrr_id']+'/download',raw=True)).hexdigest()==source_hash
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            page=browser.new_page(http_credentials={'username':'admin','password':values['STUDIO_PASSWORD']})
            page.goto(url+'/#/L'+str(old['local_number'])+'/2')
            page.wait_for_function('()=>document.querySelector("#reader-position").textContent==="2 / 3"')
            browser.close()
        print('cleanup_execution=passed; real_backend_hashes; copy_unlinked; original_unchanged; comments/favorite/progress/old_link_preserved; reader/download_passed; LRR_not_restarted; synthetic_only=true; nas_changed=false')
    finally:command(base+['down'],check=False)


if __name__=='__main__':main()
