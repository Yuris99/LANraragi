"""Export a private, self-contained NAS PILOT bundle. No registry push or NAS access."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

HERE=Path(__file__).resolve().parent
STUDIO=HERE.parent


def docker(*args,**kwargs):
    env=os.environ.copy()
    for name in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):env.pop(name,None)
    return subprocess.run(['docker','--host=unix:///var/run/docker.sock',*args],env=env,check=True,**kwargs)


def build(destination,web,lrr):
    destination=Path(destination).absolute()
    if destination.exists() or destination.with_suffix('.tar').exists():raise FileExistsError('Use a new bundle destination')
    inspected=json.loads(docker('image','inspect',web,lrr,stdout=subprocess.PIPE).stdout)
    for image in inspected:
        if (image.get('Os'),image.get('Architecture'))!=('linux','amd64'):raise ValueError('Only reviewed Linux amd64 images')
        for value in image.get('Config',{}).get('Env',[]):
            key,_,secret=value.partition('=')
            if key in ('STUDIO_PASSWORD','LRR_API_KEY','STUDIO_PC_WORKER_TOKEN','STUDIO_NAS_WORKER_TOKEN','STUDIO_WORKER_TOKEN') and secret:
                raise ValueError('Refusing an image with application credentials baked in')
    ids=[item['Id'] for item in inspected]
    destination.mkdir(mode=0o755,parents=True)
    for name in ('install-pilot.sh','compose.pilot.yaml','PILOT_GUIDE.ko.md'):
        shutil.copyfile(HERE/name,destination/name)
    for name in ('compose.nas.yaml','compose.import.yaml'):
        shutil.copyfile(STUDIO/name,destination/name)
    (destination/'images.ids').write_text('web='+ids[0]+'\nlanraragi='+ids[1]+'\n')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=STUDIO,text=True).strip()
    (destination/'provenance.json').write_text(json.dumps({'kind':'official-0.9.81-compatibility-pilot','full_fork_build_verified':False,
        'studio_source_revision':revision,'official_lrr_base':'difegue/lanraragi@sha256:6376a3de75c8a4045aadeb252eee9661ee9baf27965cec7a405a2b246d2937b3',
        'images':dict(zip(('web','lanraragi'),ids)),'includes_media_or_runtime_env':False},indent=2))
    # Docker's save stream contains image layers only, not container volumes/env.
    temporary=destination/'images.tar.gz.part'
    env=os.environ.copy()
    for name in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):env.pop(name,None)
    with subprocess.Popen(['docker','--host=unix:///var/run/docker.sock','image','save',*ids],env=env,stdout=subprocess.PIPE) as process:
        with gzip.open(temporary,'wb',compresslevel=1) as output:shutil.copyfileobj(process.stdout,output,1024*1024)
        if process.wait():raise RuntimeError('Docker image export failed')
    temporary.rename(destination/'images.tar.gz')
    manifest=[]
    for path in sorted(destination.iterdir()):
        path.chmod(0o644)
        with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        manifest.append(digest+'  '+path.name)
    (destination/'bundle.sha256').write_text('\n'.join(manifest)+'\n')
    archive=destination.with_suffix('.tar')
    with tarfile.open(archive,'x') as output:
        for path in sorted(destination.iterdir()):output.add(path,arcname=destination.name+'/'+path.name,recursive=False)
    with archive.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    archive.with_suffix('.tar.sha256').write_text(digest+'  '+archive.name+'\n')
    return {'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True);parser.add_argument('--web',required=True);parser.add_argument('--lrr',required=True)
    args=parser.parse_args();print(json.dumps(build(args.output,args.web,args.lrr)))
