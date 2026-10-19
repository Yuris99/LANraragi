"""PC/NAS command-engine agent. Engine argv and output root are operator settings."""
import hashlib
import json
import os
import secrets
import signal
import subprocess
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path


def stop_process(process):
    if os.name=='posix':
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    elif process.poll() is None:process.terminate()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name=='posix':
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        else:process.kill()
        process.wait()
    if os.name=='posix':
        # The direct process may have exited while a child ignored SIGTERM.
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass


def run_job(job, command, root, report, heartbeat_interval=20):
    if not isinstance(command,list) or not command or any(not isinstance(x,str) for x in command):
        raise ValueError('STUDIO_DOWNLOAD_COMMAND must be a JSON argv array')
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    if not isinstance(job.get('id'),str) or len(job['id'])!=32 or any(c not in '0123456789abcdef' for c in job['id']):
        raise ValueError('Invalid job ID')
    output=(root/(job['id']+'-'+secrets.token_hex(8))).resolve()
    if output.parent!=root:raise ValueError('Output escaped configured root')
    output.mkdir(exist_ok=False)
    # No shell; URL and destination are individual arguments, never executable code.
    argv=[arg.replace('{url}',job['url']).replace('{output}',str(output)) for arg in command]
    if not any('{url}' in arg for arg in command) or not any('{output}' in arg for arg in command):
        raise ValueError('Engine command requires {url} and {output} placeholders')
    report('running','엔진 출력 폴더 준비 완료',{'directory':output.name})
    stop=threading.Event()
    heartbeat_errors=[]
    def heartbeat():
        while not stop.wait(heartbeat_interval):
            try:report('running','다운로드 엔진 실행 중')
            except Exception as error:
                heartbeat_errors.append(error)
                stop.set()
                return
    heartbeat_thread=threading.Thread(target=heartbeat,daemon=True)
    heartbeat_thread.start()
    try:
        with (output/'engine.log').open('wb') as log:
            process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,shell=False,start_new_session=(os.name=='posix'))
            deadline=time.monotonic()+3600
            try:
                while process.poll() is None:
                    if heartbeat_errors:raise RuntimeError('Worker heartbeat failed')
                    if time.monotonic()>deadline:raise TimeoutError('Engine timed out')
                    time.sleep(0.1)
            finally:
                if process.poll() is None:
                    stop_process(process)
        if heartbeat_errors:raise RuntimeError('Worker heartbeat failed')
        if process.returncode:
            report('failed',f'엔진 종료 코드 {process.returncode}');return
        files=[]
        for path in output.rglob('*'):
            if path.is_symlink():raise ValueError('Engine produced a symbolic link')
            if path.is_file() and path.name!='engine.log':
                if root not in path.resolve().parents:raise ValueError('Engine output outside configured root')
                if path.suffix.lower() not in ('.jpg','.jpeg','.png','.webp','.gif','.avif','.cbz','.zip','.cbr','.7z','.pdf'):
                    continue
                if path.stat().st_size==0:raise ValueError('Engine produced an empty file')
                h=hashlib.sha256()
                with path.open('rb') as f:
                    for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
                files.append({'file':str(path.relative_to(output)),'bytes':path.stat().st_size,'sha256':h.hexdigest()})
        if not files:
            report('blocked','엔진은 종료됐지만 다운로드 파일을 확인하지 못했습니다. GUI 전달만으로 완료 처리하지 않습니다.');return
        (output/'studio-manifest.json').write_text(json.dumps(files,ensure_ascii=False,indent=2),encoding='utf-8')
        stop.set();heartbeat_thread.join()
        if heartbeat_errors:raise RuntimeError('Worker heartbeat failed')
        archives=[x for x in files if Path(x['file']).suffix.lower()=='.cbz']
        report('complete','파일 생성 및 SHA-256 기록 완료',{'files':len(files),'bytes':sum(x['bytes'] for x in files),'directory':output.name,
                                                         'archives':archives[:10]})
    finally:
        stop.set()
        heartbeat_thread.join()


def main():
    def interrupted(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    base=os.environ['STUDIO_SERVER'].rstrip('/');token=os.environ['STUDIO_WORKER_TOKEN']
    target=os.environ.get('STUDIO_TARGET','pc')
    command=json.loads(os.environ['STUDIO_DOWNLOAD_COMMAND']);root=os.environ['STUDIO_OUTPUT']
    if target not in ('pc','nas'):raise ValueError('Invalid target')
    def request(path,body):
        req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={
            'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
    while True:
        try:job=request('/api/worker/claim',{'target':target})
        except urllib.error.HTTPError as error:
            if error.code in (401,403):raise RuntimeError('Worker authorization rejected; check target token') from None
            time.sleep(5);continue
        except (urllib.error.URLError,TimeoutError,OSError):
            time.sleep(5);continue
        if not job:time.sleep(5);continue
        def report(state,message='',result=None):
            return request('/api/worker/'+job['id']+'/report',{
                'lease':job['lease'],'state':state,'message':message,'result':result})
        try:run_job(job,command,root,report)
        except Exception:
            try:report('failed','작업자가 엔진 실행 또는 결과 검증에 실패했습니다. 작업 폴더의 로그를 확인하세요.')
            except Exception:time.sleep(5)  # Expiry blocks the job; never reclaim it automatically.


if __name__=='__main__':main()
