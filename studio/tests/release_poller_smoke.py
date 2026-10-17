"""Real fixed-controller Docker rehearsal; synthetic media only, never a NAS.

Adapt NAS constants/root identity to the pre-existing guarded cloud fixture.
Only HTTPS downloads are fixture copies. JSON parsing, backup, code validation,
Studio recreation, health, duplicate suppression and rollback use real Docker.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request


def main():
    repo=Path(__file__).resolve().parents[2]
    fixture=repo/'work/folder-root-check'
    originals=fixture/'originals'
    expected={'manga/Synthetic Folder/1.png','manga/Synthetic Folder/2.jpg','manga/Synthetic Folder/3.webp'}
    assert {str(p.relative_to(originals)) for p in originals.rglob('*') if p.is_file()}==expected
    before_originals={str(p.relative_to(originals)):hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in originals.rglob('*') if p.is_file()}
    base=Path(tempfile.mkdtemp(prefix='release-poller-check.',dir=repo/'work'))
    root=base/'library-studio';root.mkdir()
    control=base/'library-studio-deploy';control.mkdir(mode=0o700)
    stubs=base/'bin';stubs.mkdir()
    env={k:v for k,v in os.environ.items() if k not in {'DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'}}
    docker=['docker','--host=unix:///var/run/docker.sock']
    project='library-studio-folder-root-check'
    def command(args,check=True):
        r=subprocess.run(args,env=env,capture_output=True,text=True,timeout=150)
        if check and r.returncode:raise AssertionError((r.stdout,r.stderr))
        return r
    def inspect(fmt,service='studio'):
        return command(docker+['inspect','--format',fmt,project+'-'+service+'-1']).stdout.strip()
    image=inspect('{{.Image}}')
    lrr_started=inspect('{{.State.StartedAt}}','lanraragi')
    initial_started=inspect('{{.State.StartedAt}}')
    assert inspect('{{range .Mounts}}{{if eq .Destination "/app"}}{{.Source}}{{end}}{{end}}')==''
    shutil.copyfile(fixture/'.env.nas',root/'.env.nas');(root/'.env.nas').chmod(0o600)
    (root/'inbox').mkdir()
    with (root/'.env.nas').open('a') as f:f.write('STUDIO_INBOX='+str(root/'inbox')+'\n')
    for src,name in [('studio/compose.nas.yaml','compose.nas.yaml'),('studio/compose.import.yaml','compose.import.yaml'),('studio/deploy/compose.pilot.yaml','compose.pilot.yaml')]:
        shutil.copyfile(repo/src,root/name)
    manifest_sha=hashlib.sha256((repo/'studio/deploy/runtime-manifest.sha256').read_bytes()).hexdigest()
    text=(repo/'studio/deploy/update-studio-ui.sh').read_text()
    text=text.replace('case "$root" in /volume*/docker/library-studio)','case "$root" in '+str(root)+')')
    text=text.replace('volume=${root%/docker/library-studio};number=${volume#/volume}','volume=/volume1;number=1')
    text=text.replace('library-studio-nas-pilot',project)
    text=text.replace('sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0',image)
    text=text.replace('=="43120"','=="43134"')
    (control/'update-studio-ui.sh').write_text(text)
    text=(repo/'studio/deploy/poll-studio-release.sh').read_text()
    text=text.replace('case "$control" in /volume*/docker/library-studio-deploy)','case "$control" in '+str(control)+')')
    text=text.replace('volume=${root%/docker/library-studio};number=${volume#/volume}','volume=/volume1;number=1')
    text=text.replace('= 0:700 ]','= '+str(os.getuid())+':700 ]')
    text=text.replace('sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0',image)
    (control/'poll.sh').write_text(text)
    (control/'controller.sha256').write_text(''.join(hashlib.sha256((control/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in ['poll.sh','update-studio-ui.sh']))
    (control/'configs.sha256').write_text(''.join(hashlib.sha256((root/n).read_bytes()).hexdigest()+'  '+str(root/n)+'\n' for n in ['compose.nas.yaml','compose.import.yaml','compose.pilot.yaml','.env.nas']))
    (control/'enabled').touch()
    release=base/'release.json'
    request=dict(schema=1,enabled=False,generation=1,revision='1'*40,manifest_sha256=manifest_sha)
    def publish(**changes):
        request.update(changes);release.write_text(json.dumps(request))
    publish()
    (stubs/'id').write_text('#!/bin/sh\n[ "$1" = -u ] && printf "0\\n"\n');(stubs/'id').chmod(0o755)
    (stubs/'curl').write_text('#!'+sys.executable+'\n'+'''
import os,shutil,sys
from pathlib import Path
a=sys.argv[1:];url=next(x for x in a if x.startswith('https://'));target=a[a.index('-o')+1]
if url.endswith('/nas-release.json'):
 shutil.copyfile(os.environ['FIXTURE_RELEASE'],target)
else:
 prefix='https://raw.githubusercontent.com/Yuris99/LANraragi/'+('1'*40)+'/studio/'
 assert url.startswith(prefix);relative=url[len(prefix):];assert '..' not in relative
 shutil.copyfile(Path(os.environ['FIXTURE_SOURCE'])/relative,target)
 if os.environ.get('FIXTURE_TAMPER')=='1' and relative=='web/app.js':
  with open(target,'a') as f:f.write('corrupt fixture')
''');(stubs/'curl').chmod(0o755)
    env.update(PATH=str(stubs)+os.pathsep+env['PATH'],FIXTURE_RELEASE=str(release),FIXTURE_SOURCE=str(repo/'studio'))
    values=dict(x.split('=',1) for x in (root/'.env.nas').read_text().splitlines() if '=' in x)
    assert values['STUDIO_PORT']=='43134'
    auth='Basic '+base64.b64encode(('admin:'+values['STUDIO_PASSWORD']).encode()).decode()
    def get(path):
        req=urllib.request.Request('http://127.0.0.1:43134'+path,headers={'Authorization':auth})
        with urllib.request.urlopen(req,timeout=15) as r:return r.read()
    archive=json.loads(get('/api/uploads'))['items'][0]['sha256']
    assert hashlib.sha256(get('/api/uploads/'+archive+'/download')).hexdigest()==archive
    def poll(*args,check=True):return command(['sh',str(control/'poll.sh'),*args],check)
    assert 'release=disabled' in poll('tick').stdout
    assert inspect('{{.State.StartedAt}}')==initial_started
    publish(enabled=True)
    assert 'deployment=healthy' in poll('tick').stdout
    assert json.loads(get('/api/library/status'))['folder_archives']==1
    assert isinstance(json.loads(get('/api/library/tags')),list)
    first_code=inspect('{{range .Mounts}}{{if eq .Destination "/app"}}{{.Source}}{{end}}{{end}}')
    first_started=inspect('{{.State.StartedAt}}')
    assert first_code.startswith(str(root)+'/studio-runtime.')
    assert len(list(root.glob('ui-update-backup.*')))==1
    assert 'already_attempted' in poll('tick').stdout
    assert inspect('{{.State.StartedAt}}')==first_started
    publish(generation=2);env['FIXTURE_TAMPER']='1'
    assert poll('tick',check=False).returncode!=0
    assert 'failed_or_interrupted' in poll('status').stdout
    assert inspect('{{.State.StartedAt}}')==first_started
    assert len(list(root.glob('ui-update-backup.*')))==1
    assert 'already_attempted' in poll('tick').stdout
    env.pop('FIXTURE_TAMPER');publish(generation=3)
    assert 'deployment=healthy' in poll('tick').stdout
    assert len(list(root.glob('ui-update-backup.*')))==2
    assert inspect('{{.State.StartedAt}}')!=first_started
    poll('rollback')
    assert inspect('{{range .Mounts}}{{if eq .Destination "/app"}}{{.Source}}{{end}}{{end}}')==first_code
    # The fixed rollback intentionally leaves health asynchronous; wait locally.
    for _ in range(30):
        if inspect('{{.State.Health.Status}}')=='healthy':break
        import time;time.sleep(1)
    assert inspect('{{.State.Health.Status}}')=='healthy'
    poll('disable');publish(generation=4)
    after_rollback=inspect('{{.State.StartedAt}}')
    assert 'local_updates=disabled' in poll('tick').stdout
    assert inspect('{{.State.StartedAt}}')==after_rollback
    assert hashlib.sha256(get('/api/uploads/'+archive+'/download')).hexdigest()==archive
    assert inspect('{{.State.StartedAt}}','lanraragi')==lrr_started
    assert {str(p.relative_to(originals)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in originals.rglob('*') if p.is_file()}==before_originals
    # Leave the pre-existing synthetic stack on its original image code.
    command(['sh',str(control/'update-studio-ui.sh'),'rollback',str(root)])
    assert inspect('{{range .Mounts}}{{if eq .Destination "/app"}}{{.Source}}{{end}}{{end}}')==''
    print(json.dumps(dict(release_poller='passed',json_parser='real_nonroot_container',apply='healthy',
                          backups=2,duplicate_restart=False,checksum_failure='quarantined',
                          rollback='previous_overlay_then_original',revocation='local',
                          archive_sha256_preserved=True,originals_unchanged=True,lrr_restarted=False,
                          nas_deployment=False)))


if __name__=='__main__':main()
