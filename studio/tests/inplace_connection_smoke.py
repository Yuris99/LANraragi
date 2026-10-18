"""Synthetic-only rehearsal: original-path CBZ + NAS metadata + LRR root connection."""
import base64, hashlib, io, json, os
from pathlib import Path
import shutil, subprocess, sys, tempfile, time, urllib.request, zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy'))
from prepare_nas import prepare
from archive_in_place import convert
from make_synthetic import create_fixture

def main():
    repo=Path(__file__).resolve().parents[2]
    fixture=Path(tempfile.mkdtemp(prefix='inplace-connect.',dir=repo/'work'))
    root=fixture/'library-studio';root.mkdir()
    project='library-studio-inplace-check-'+fixture.name.split('.')[-1]
    env={k:v for k,v in os.environ.items() if k not in {'DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'}}
    docker=['docker','--host=unix:///var/run/docker.sock']
    def command(args,check=True,timeout=240):
        result=subprocess.run(args,cwd=repo,env=env,text=True,capture_output=True,timeout=timeout)
        if check and result.returncode:raise AssertionError((result.stdout,result.stderr))
        return result
    def image(tag):return command(docker+['image','inspect','--format','{{.Id}}',tag]).stdout.strip()
    web=image('lanraragi-studio:nas-baseline-root-check');lrr=image('lanraragi-studio:lrr-root-reader-check')
    original=fixture/'originals';(original/'manga'/'Generated').mkdir(parents=True)
    (original/'images').mkdir()
    book=original/'manga'/'Generated'
    expected={}
    with zipfile.ZipFile(create_fixture(fixture/'generated')) as archive:
        for name in archive.namelist():
            expected[name]=archive.read(name);(book/name).write_bytes(expected[name])
    (book/'@eaDir').mkdir();(book/'@eaDir'/'cache.png').write_bytes(expected['01.png'])
    for p in [original,*original.rglob('*')]:
        p.chmod(0o700 if p.is_dir() else 0o600);os.utime(p,(time.time()-120,)*2)
    converted=convert(book,apply=True,delete_source=True,preserve_system=True)
    assert converted['source_removed']
    cbz=Path(str(book)+'.cbz');archive_hash=hashlib.sha256(cbz.read_bytes()).hexdigest()
    for name in ['library','library/downloads','inbox']:
        (root/name).mkdir(exist_ok=True);(root/name).chmod(0o755)
    prepare(root/'.env.nas',str(root/'library'),str(root/'library/downloads'),1026,100,lrr,web)
    values=dict(line.split('=',1) for line in (root/'.env.nas').read_text().splitlines())
    values.update(STUDIO_PORT='43138',STUDIO_INBOX=str(root/'inbox'))
    (root/'.env.nas').write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
    for name,source in [('compose.nas.yaml','studio/compose.nas.yaml'),('compose.import.yaml','studio/compose.import.yaml'),('compose.pilot.yaml','studio/deploy/compose.pilot.yaml')]:
        shutil.copyfile(repo/source,root/name)
    # Only the cloud fixture needs platform proxy/CA mounts.
    code=root/'code';code.mkdir(mode=0o755);(code/'web').mkdir(mode=0o755)
    for line in (repo/'studio/deploy/runtime-manifest.sha256').read_text().splitlines():
        _,name=line.split('  ',1);shutil.copyfile(repo/'studio'/name,code/name);(code/name).chmod(0o644)
    code.chmod(0o755);(code/'web').chmod(0o755)
    (root/'compose.ui.yaml').write_text(json.dumps({'services':{'studio':{'volumes':[{'type':'bind','source':str(code),'target':'/app','read_only':True}]}}}))
    # CPU CFS quotas unsupported on the target too; no quotas in fixture.
    base=docker+['compose','--env-file',str(root/'.env.nas'),'-p',project]
    for f in ['compose.nas.yaml','compose.import.yaml','compose.pilot.yaml','compose.ui.yaml']:base+=['-f',str(root/f)]
    base+=['-f',str(repo/'studio/compose.cloud-runtime.yaml')]
    command(base+['up','-d'])
    try:
        for _ in range(120):
            if command(docker+['inspect','--format','{{.State.Health.Status}}',project+'-studio-1']).stdout.strip()=='healthy':break
            time.sleep(1)
        assert command(docker+['inspect','--format','{{.State.Health.Status}}',project+'-studio-1']).stdout.strip()=='healthy'
        control=Path(str(root)+'-deploy');control.mkdir(mode=0o700);control.chmod(0o700)
        for name in ['poll.sh','update-studio-ui.sh']:(control/name).write_text('# synthetic controller fixture\n')
        (control/'controller.sha256').write_text(''.join(hashlib.sha256((control/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in ['poll.sh','update-studio-ui.sh']))
        (control/'configs.sha256').write_text(''.join(hashlib.sha256((root/n).read_bytes()).hexdigest()+'  '+str(root/n)+'\n' for n in ['compose.nas.yaml','compose.import.yaml','compose.pilot.yaml','.env.nas']))
        (control/'enabled').touch()
        pending=os.environ.get('STUDIO_INPLACE_PENDING')=='1'
        if pending:
            (control/'enabled').unlink()
            (root/'compose.archive.yaml').write_text(json.dumps({'services':{'lanraragi':{'environment':{'LRR_UID':'0','LRR_GID':'0'},'volumes':[{'type':'bind','source':str(original),'target':'/home/koyomi/lanraragi/content/NASOriginals','read_only':True,'bind':{'create_host_path':False}}]}}}))
            (root/'compose.archive.yaml').chmod(0o600)
        stubs=fixture/'bin';stubs.mkdir()
        (stubs/'id').write_text('#!/bin/sh\n[ "$1" = -u ] && printf "0\\n"\n');(stubs/'id').chmod(0o755)
        env['PATH']=str(stubs)+os.pathsep+env['PATH']
        text=(repo/'studio/deploy/connect-inplace-library.sh').read_text()
        text=text.replace('root=/volume1/docker/library-studio','root='+str(root))
        text=text.replace('project=library-studio-nas-pilot','project='+project)
        text=text.replace('case "$source" in /volume[0-9]*/*)','case "$source" in '+str(original)+')')
        text=text.replace('number=${source#/volume};number=${number%%/*}','number=1')
        text=text.replace('= 0:700 ]','= '+str(os.getuid())+':700 ]')
        text=text.replace('= 0:600 ]','= '+str(os.getuid())+':600 ]')
        text=text.replace('"$(stat -c \'%u\' "$overlay")" = 0','"$(stat -c \'%u\' "$overlay")" = '+str(os.getuid()))
        text=text.replace('sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0',web)
        text=text.replace('sha256:b76c792a43846f0755d0dadf98c8dd46123e8d244045e2f9b6834d9b45988957',lrr)
        # Include only the fixture CA/proxy overlay in this synthetic lifecycle.
        text=text.replace('-f "$root/compose.ui.yaml" "$@"','-f "$root/compose.ui.yaml" -f '+str(repo/'studio/compose.cloud-runtime.yaml')+' "$@"')
        helper=root/'connect.sh';helper.write_text(text)
        result=command(['sh',str(helper),'apply',str(original)])
        assert 'connection=healthy' in result.stdout,result.stdout
        if pending:
            assert 'pending_overlay=verified_unapplied' in result.stdout
            assert len(list(root.glob('archive-connection.*/compose.archive.unapplied.yaml')))==1
        assert (control/'enabled').exists()
        assert str(root/'compose.archive.yaml') in (control/'configs.sha256').read_text()
        # Authentication stays in memory. Never print credentials or env/configs.
        auth='Basic '+base64.b64encode(('admin:'+values['STUDIO_PASSWORD']).encode()).decode()
        def request(path,data=None):
            req=urllib.request.Request('http://127.0.0.1:43138'+path,headers={'Authorization':auth,'Content-Type':'application/json'},data=None if data is None else json.dumps(data).encode())
            with urllib.request.urlopen(req,timeout=30) as response:return response.read()
        for _ in range(120):
            request('/api/sync',{})
            works=json.loads(request('/api/works'))
            if works['total']==1:break
            time.sleep(1)
        assert works['total']==1,works
        work=works['items'][0];archive_id=work['lrr_id']
        files=json.loads(request('/api/media/'+archive_id+'/files'))
        assert len(files['pages'])==3,files
        assert hashlib.sha256(request('/api/media/'+archive_id+'/download')).hexdigest()==archive_hash
        assert hashlib.sha256(cbz.read_bytes()).hexdigest()==archive_hash
        assert not book.exists()
        assert not list(root.glob('archive-connection.*/before.json'))
        assert not list(root.glob('archive-connection.*/after.json'))
        # The fixed deployment task uses base Compose with --no-deps studio.
        # Its model need not include the separate LRR connection overlay.
        lrr_started=command(docker+['inspect','--format','{{.Id}}|{{.State.StartedAt}}',project+'-lanraragi-1']).stdout
        command(base+['up','-d','--no-deps','--force-recreate','studio'])
        assert command(docker+['inspect','--format','{{.Id}}|{{.State.StartedAt}}',project+'-lanraragi-1']).stdout==lrr_started
        assert command(docker+['exec',project+'-lanraragi-1','s6-setuidgid','koyomi','id','-u']).stdout.strip()=='0'
        print(json.dumps({'connection':'passed','lrr_uid_gid':'0:0','source':'read_only','source_folder_removed':True,
                          'archive_download_hash':True,'reader_pages':3,'nas_metadata_preserved':True,
                          'connector_preserved_studio':True,'studio_update_preserved_lrr':True,'pending_recovery':pending,
                          'auto_update_baseline':'extra overlay frozen','nas_changed':False}))
    finally:
        command(base+['stop','studio','lanraragi'],check=False)

if __name__=='__main__':main()

