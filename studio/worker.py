"""PC/NAS command-engine agent. Engine argv and output root are operator settings."""
import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path


def run_job(job, command, root, report):
    if not isinstance(command,list) or not command or any(not isinstance(x,str) for x in command):
        raise ValueError('STUDIO_DOWNLOAD_COMMAND must be a JSON argv array')
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    output=(root/job['id']).resolve()
    if output.parent!=root:raise ValueError('Output escaped configured root')
    output.mkdir(exist_ok=False)
    # No shell; URL and destination are individual arguments, never executable code.
    argv=[arg.replace('{url}',job['url']).replace('{output}',str(output)) for arg in command]
    if not any('{url}' in arg for arg in command) or not any('{output}' in arg for arg in command):
        raise ValueError('Engine command requires {url} and {output} placeholders')
    stop=threading.Event()
    def heartbeat():
        while not stop.wait(20):report('running','다운로드 엔진 실행 중')
    threading.Thread(target=heartbeat,daemon=True).start()
    try:
        with (output/'engine.log').open('wb') as log:
            process=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                   timeout=3600,check=False,shell=False)
        if process.returncode:
            report('failed',f'엔진 종료 코드 {process.returncode}');return
        files=[]
        for path in output.rglob('*'):
            if path.is_symlink():raise ValueError('Engine produced a symbolic link')
            if path.is_file() and path.name!='engine.log':
                if root not in path.resolve().parents:raise ValueError('Engine output outside configured root')
                if path.suffix.lower() not in ('.jpg','.jpeg','.png','.webp','.gif','.avif','.cbz','.zip','.cbr','.7z','.pdf'):
                    continue
                h=hashlib.sha256()
                with path.open('rb') as f:
                    for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
                files.append({'file':str(path.relative_to(output)),'bytes':path.stat().st_size,'sha256':h.hexdigest()})
        if not files:
            report('blocked','엔진은 종료됐지만 다운로드 파일을 확인하지 못했습니다. GUI 전달만으로 완료 처리하지 않습니다.');return
        (output/'studio-manifest.json').write_text(json.dumps(files,ensure_ascii=False,indent=2),encoding='utf-8')
        report('complete','파일 생성 및 SHA-256 기록 완료',{'files':len(files),'bytes':sum(x['bytes'] for x in files),'directory':job['id']})
    finally:stop.set()


def main():
    base=os.environ['STUDIO_SERVER'].rstrip('/');token=os.environ['STUDIO_WORKER_TOKEN']
    target=os.environ.get('STUDIO_TARGET','pc')
    command=json.loads(os.environ['STUDIO_DOWNLOAD_COMMAND']);root=os.environ['STUDIO_OUTPUT']
    if target not in ('pc','nas'):raise ValueError('Invalid target')
    def request(path,body):
        req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={
            'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
    while True:
        job=request('/api/worker/claim',{'target':target})
        if not job:time.sleep(5);continue
        def report(state,message='',result=None):
            return request('/api/worker/'+job['id']+'/report',{
                'lease':job['lease'],'state':state,'message':message,'result':result or {}})
        try:run_job(job,command,root,report)
        except Exception:
            report('failed','작업자가 엔진 실행 또는 결과 검증에 실패했습니다. 작업 폴더의 로그를 확인하세요.')


if __name__=='__main__':main()
