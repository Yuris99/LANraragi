"""Isolated Docker NAS profile, synthetic login/download, actual LANraragi.

No real site, NAS, account, cookies or private media. The external engine fixture
replaces network extraction only; real worker leases, hashes, CBZ publication,
LRR indexing, source attachment and browser image run in their actual containers.
"""
import base64
import hashlib
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
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from make_synthetic import create_fixture
from prepare_nas import prepare
from site_login_smoke import FORM


def main():
    repo=Path(__file__).resolve().parents[2]
    temporary=Path(tempfile.mkdtemp(prefix='login-docker.',dir=repo/'work'));temporary.chmod(0o755)
    project='studio-login-check-'+temporary.name.split('.')[-1];sideproject=project+'-login'
    env={k:v for k,v in os.environ.items() if k not in {'DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'}}
    docker=['docker','--host=unix:///var/run/docker.sock']
    def command(args,check=True):
        r=subprocess.run(args,cwd=repo,env=env,text=True,capture_output=True,timeout=240)
        if check and r.returncode:raise AssertionError((r.stdout,r.stderr))
        return r
    def image(tag):return command(docker+['image','inspect','--format','{{.Id}}',tag]).stdout.strip()
    web=image('lanraragi-studio:nas-baseline-root-check');lrr=image('lanraragi-studio:lrr-root-reader-check')
    login=image('lanraragi-studio:login-candidate');worker=image('lanraragi-studio:session-worker-candidate')
    (temporary/'library/downloads').mkdir(parents=True)
    fixture=create_fixture(temporary/'generated');fixture.chmod(0o644)
    prepare(temporary/'.env.nas',str(temporary/'library'),str(temporary/'library/downloads'),os.getuid(),os.getgid(),lrr,web,worker)
    values=dict(line.split('=',1) for line in (temporary/'.env.nas').read_text().splitlines())
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    values.update(STUDIO_PORT=str(port),STUDIO_LOGIN_IMAGE=login,STUDIO_DATA_VOLUME=project+'_studio-data',STUDIO_APP_NETWORK=project+'_default')
    (temporary/'.env.nas').write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
    # Mount generated fixtures only. Network extraction is never performed.
    login_fixture=temporary/'login_fixture.py'
    login_fixture.write_text('''import os,sys
sys.path.insert(0,'/app')
from login_service import BrowserActor,make_login_server
from site_sessions import CookieVault,read_service_token
FORM = '''+repr(FORM)+'''
def fixture(route):
    if route.request.method=='POST':
        assert route.request.post_data=='user=generated-user&password=generated-password'
        route.fulfill(status=200,content_type='text/html',headers={'Set-Cookie':'fixture_session=generated-cookie; Domain=.e-hentai.org; Path=/; Secure; HttpOnly'},body='<p>Generated login completed</p>')
    else:route.fulfill(status=200,content_type='text/html',body=FORM)
actor=BrowserActor(CookieVault('/sessions'),fixture)
server=make_login_server('0.0.0.0',8091,actor,read_service_token('/run/studio-login/token'))
server.serve_forever()
''');login_fixture.chmod(0o644)
    engine_fixture=temporary/'engine_fixture.py'
    engine_fixture.write_text('''import argparse,zipfile,sys
sys.path.insert(0,'/app')
from pathlib import Path
from gallery_engine import cookie_snapshot,package_images
from sources import parse_source
p=argparse.ArgumentParser();p.add_argument('--url');p.add_argument('--output');a=p.parse_args()
with cookie_snapshot(a.url) as cookies:assert 'generated-cookie' in Path(cookies).read_text()
root=Path(a.output)
with zipfile.ZipFile('/generated.cbz') as z:
    for name in z.namelist():(root/name).write_bytes(z.read(name))
package_images(root,parse_source(a.url))
''');engine_fixture.chmod(0o644)
    code=repo/'studio'
    base_override=temporary/'base.json';base_override.write_text(json.dumps({'services':{'studio':{
        'environment':{'NO_PROXY':'localhost,127.0.0.1,lanraragi,site-login','no_proxy':'localhost,127.0.0.1,lanraragi,site-login'},
        'volumes':[{'type':'bind','source':str(code),'target':'/app','read_only':True}]}}}))
    side_override=temporary/'side.json';side_override.write_text(json.dumps({'services':{
        'site-login':{'entrypoint':['python','/login_fixture.py'],'volumes':[{'type':'bind','source':str(login_fixture),'target':'/login_fixture.py','read_only':True}]},
        'worker':{'environment':{'STUDIO_DOWNLOAD_COMMAND':json.dumps(['python','/engine_fixture.py','--url','{url}','--output','{output}'])},'volumes':[
            {'type':'bind','source':str(engine_fixture),'target':'/engine_fixture.py','read_only':True},
            {'type':'bind','source':str(fixture),'target':'/generated.cbz','read_only':True}]}}}))
    base=docker+['compose','--env-file',str(temporary/'.env.nas'),'-p',project,'-f',str(repo/'studio/compose.nas.yaml'),'-f',str(repo/'studio/deploy/compose.pilot.yaml'),'-f',str(base_override),'-f',str(repo/'studio/compose.cloud-runtime.yaml')]
    side=docker+['compose','--env-file',str(temporary/'.env.nas'),'-p',sideproject,'-f',str(repo/'studio/compose.login.yaml'),'-f',str(repo/'studio/compose.worker-sessions.yaml'),'-f',str(side_override)]
    auth='Basic '+base64.b64encode(('admin:'+values['STUDIO_PASSWORD']).encode()).decode()
    url='http://127.0.0.1:'+str(port)
    def request(path,data=None):
        headers={'Authorization':auth}
        if data is not None:headers['Content-Type']='application/json';data=json.dumps(data).encode()
        with urllib.request.urlopen(urllib.request.Request(url+path,data=data,headers=headers),timeout=45) as response:return json.load(response)
    def wait(fn,seconds=120):
        last=None
        for _ in range(seconds):
            try:
                last=fn()
                if last:return last
            except Exception:pass
            time.sleep(1)
        raise AssertionError('Generated container condition timed out')
    try:
        print('phase=base_start',flush=True)
        command(base+['up','-d'])
        wait(lambda:command(docker+['inspect','--format','{{.State.Health.Status}}',project+'-studio-1']).stdout.strip()=='healthy')
        print('phase=login_start',flush=True)
        command(side+['up','-d','login-init','site-login'])
        wait(lambda:request('/api/site-connections').get('configured'))
        print('phase=login_flow',flush=True)
        frame=request('/api/site-connections',{'op':'start','provider':'ehentai'});session=frame['session']
        assert frame['image'].startswith('data:image/png;base64,')
        def rpc(op,**data):return request('/api/site-connections',{'op':op,'session':session,**data})
        rpc('click',x=100,y=75);rpc('text',text='generated-user')
        rpc('click',x=100,y=135);rpc('text',text='generated-password');rpc('click',x=100,y=195)
        wait(lambda:'synthetic-login' in rpc('frame')['location'],20)
        assert rpc('save')['state']=='saved_unverified'
        command(side+['restart','site-login'])
        wait(lambda:any(s['provider']=='ehentai' and s['state']=='saved_unverified' for s in request('/api/site-connections')['sites']))
        before=request('/api/works')['total'];assert before==0
        result=request('/api/downloads',{'provider':'ehentai','reference':'https://e-hentai.org/g/123/abc123/','target':'nas','engine':'command'})
        job_id=result['job']['id']
        print('phase=worker_download',flush=True)
        command(side+['--profile','downloads','up','-d','worker'])
        wait(lambda:request('/api/downloads/status')['command_workers']['nas'])
        print('phase=waiting_catalog',flush=True)
        job=wait(lambda:next((j for j in request('/api/jobs') if j['id']==job_id and j['state']=='complete' and json.loads(j['result']).get('catalog_indexed')),None),150)
        work_id=json.loads(job['result'])['catalog_work_id'];work=request('/api/works/'+work_id)
        assert work['sources'][0]['url']=='https://e-hentai.org/g/123/abc123/'
        assert work['pages']==3 and request('/api/works')['total']==1
        manifest=list((temporary/'library/downloads').glob('*/studio-manifest.json'));assert len(manifest)==1
        files=json.loads(manifest[0].read_text());archive=next(f for f in files if f['file']=='ehentai-123.cbz')
        assert archive['sha256']==hashlib.sha256((manifest[0].parent/archive['file']).read_bytes()).hexdigest()
        connection=request('/api/site-connections');assert all(not s['site_verified'] for s in connection['sites'])
        # Ordinary Studio recreation retains login discovery and session volume.
        command(base+['up','-d','--no-deps','--force-recreate','studio'])
        wait(lambda:request('/api/site-connections')['configured'])
        assert request('/api/works')['total']==1
        print('site_login_docker=passed; nonroot_browser_readonly_root; private_volume_init; synthetic_login_saved; gateway_restart; real_worker_lease_cookie_snapshot; atomic_CBZ; real_LRR_index; full_hash_source_link; Studio_recreate_retains_discovery; generated_only=true; nas_changed=false')
    finally:
        command(side+['--profile','downloads','down','-v'],check=False)
        command(base+['down','-v'],check=False)


if __name__=='__main__':main()
