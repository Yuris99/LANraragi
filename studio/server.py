"""Authenticated Library Studio frontend/API for the LANraragi fork (stdlib only)."""
import base64
import concurrent.futures
import hmac
import hashlib
import json
import mimetypes
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from connectors import fetch_comments
from sources import parse_source
from store import Store
from uploads import Uploads,UploadError

HERE=Path(__file__).parent


class LRR:
    def __init__(self, url, key=''):
        self.url=url.rstrip('/')
        self.key=key

    def open(self, path, method='GET', form=None, headers=None):
        data=None if form is None else urllib.parse.urlencode(form).encode()
        auth={'Authorization':'Bearer '+base64.b64encode(self.key.encode()).decode()} if self.key else {}
        request=urllib.request.Request(self.url+path,data=data,method=method,headers={**auth,**(headers or {})})
        return urllib.request.urlopen(request,timeout=45)

    def json(self, path, method='GET', form=None):
        with self.open(path,method,form) as response:
            value=json.load(response)
        if isinstance(value,dict) and (value.get('error') or value.get('success')==0):
            raise ValueError(str(value.get('error') or 'LANraragi operation failed')[:500])
        return value


class Studio:
    def __init__(self, store, lrr, upload_dir=None):
        self.store=store;self.lrr=lrr;self.stop=threading.Event()
        self.sync_lock=threading.Lock();self.upload_cursor=''
        self.uploads=Uploads(store,upload_dir or os.environ.get('STUDIO_UPLOAD_DIR'),int(os.environ.get('STUDIO_MAX_UPLOAD_BYTES',512*1024*1024)))

    def sync(self):
        if not self.sync_lock.acquire(blocking=False):
            raise ValueError('동기화가 이미 진행 중입니다.')
        try:
            ids=self.lrr.json('/api/archives')
            if not isinstance(ids,list):raise ValueError('LANraragi 목록 형식 오류')
            if len(ids)>100000:raise ValueError('이번 동기화 한도를 초과했습니다.')
            archive_ids=[x.get('arcid') if isinstance(x,dict) else x for x in ids]
            valid=[x for x in archive_ids if isinstance(x,str) and re.fullmatch('[0-9a-f]{40}',x)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                metadata=list(pool.map(lambda i:self.lrr.json('/api/archives/'+i+'/metadata'),valid))
            return {'synced':self.store.sync_lrr(metadata)}
        finally:self.sync_lock.release()

    def sync_uploads(self):
        if not self.sync_lock.acquire(blocking=False):return {'synced':0,'pending':True}
        try:
            pending=self.uploads.pending(self.upload_cursor)
            if not pending:return {'synced':0}
            self.upload_cursor=pending[-1]['sha256']
            archives=self.lrr.json('/api/archives')
            if not isinstance(archives,list):raise ValueError('LANraragi 목록 형식 오류')
            indexed={item['arcid']:item for item in archives if isinstance(item,dict) and re.fullmatch('[0-9a-f]{40}',item.get('arcid',''))}
            metadata=[];links=[]
            for upload in pending:
                # The upstream ID hashes only the first 512000 bytes. Never use it
                # alone to merge an upload with a previously indexed archive.
                _,stream=self.uploads.open(upload['sha256'])
                with stream:candidate=hashlib.sha1(stream.read(512000)).hexdigest()
                if candidate not in indexed:continue
                remote=indexed[candidate];matches=Path(remote.get('filename','')).stem==upload['sha256']
                if not matches:
                    digest=hashlib.sha256();received=0
                    with self.lrr.open('/api/archives/'+candidate+'/download') as response:
                        while block:=response.read(min(256*1024,upload['bytes']+1-received)):
                            received+=len(block);digest.update(block)
                            if received>upload['bytes']:break
                    matches=received==upload['bytes'] and digest.hexdigest()==upload['sha256']
                if not matches:
                    with self.store.db() as db:db.execute("UPDATE uploads SET state='conflict' WHERE sha256=?",(upload['sha256'],))
                    continue
                metadata.append(self.lrr.json('/api/archives/'+candidate+'/metadata'))
                links.append((candidate,upload['sha256']))
            synced=self.store.sync_lrr(metadata)
            with self.store.db() as db:
                db.executemany("UPDATE uploads SET lrr_id=?,state='indexed' WHERE sha256=?",links)
                for _,sha in links:self.store.apply_upload_tags(db,sha)
            return {'synced':synced}
        finally:self.sync_lock.release()

    def fetch_metadata(self, work_id, source_id):
        work=self.store.get_work(work_id)
        source=next((s for s in work['sources'] if s['id']==source_id),None)
        if not source:raise KeyError('출처를 찾을 수 없습니다.')
        if not work['lrr_id']:raise ValueError('라이브러리에 파일을 연결한 뒤 태그를 가져오세요.')
        plugins=self.lrr.json('/api/plugins/metadata')
        namespace={'ehentai':'ehplugin','hitomi':'hitomiplugin','nhentai':'nhplugin'}[source['provider']]
        candidates=[x for x in plugins if x.get('namespace')==namespace]
        if not candidates:raise ValueError('해당 사이트의 메타데이터 플러그인이 설치되어 있지 않습니다.')
        response=self.lrr.json('/api/plugins/use','POST',{
            'id':work['lrr_id'],'plugin':candidates[0]['namespace'],'arg':source['url']})
        data=response.get('data',{})
        tags=data.get('new_tags',data.get('tags',''))
        # Fetching tags must never erase previously imported comments or local title edits.
        return self.store.upsert_source(work_id,{'url':source['url'],'tags':tags,'status':'fetched'})

    def fetch_comments(self, work_id, source_id):
        work=self.store.get_work(work_id)
        source=next((s for s in work['sources'] if s['id']==source_id),None)
        if not source:raise KeyError('출처를 찾을 수 없습니다.')
        if source['provider']=='nhentai':self.store.begin_comment_fetch(work_id,source_id)
        result=fetch_comments(source['url'])
        self.store.apply_comments(work_id,source_id,result)
        return {'status':result['status'],'message':result['message']}

    def nas_loop(self):
        while not self.stop.wait(2):
            job=self.store.claim('nas','lanraragi')
            if not job:continue
            try:
                plugins=self.lrr.json('/api/plugins/download')
                if not any(re.search(p.get('url_regex') or r'(?!)',job['url']) for p in plugins):
                    self.store.report(job['id'],job['lease'],'blocked',
                                      '이 URL을 지원하는 서버 다운로드 플러그인이 없습니다. 외부 엔진 작업자를 연결하세요.')
                    continue
                self.store.report(job['id'],job['lease'],'running','원격 다운로드 제출 중',{'submission':'pending'})
                response=self.lrr.json('/api/download_url','POST',{'url':job['url']})
                remote_id=str(response['job'])
                self.store.report(job['id'],job['lease'],'running','서버 작업 등록 완료',{'remote_job':remote_id})
                while not self.stop.wait(2):
                    status=self.lrr.json('/api/minion/'+remote_id+'/detail')
                    state=status.get('state')
                    if state=='finished':
                        self.store.report(job['id'],job['lease'],'complete','서버 다운로드 완료',{'remote_job':remote_id})
                        try:self.sync()
                        except Exception:pass  # Download success remains separate from catalog synchronization.
                        break
                    if state=='failed':
                        self.store.report(job['id'],job['lease'],'failed','서버 다운로드가 실패했습니다.',{'remote_job':remote_id})
                        break
                    self.store.report(job['id'],job['lease'],'running','서버에서 다운로드 중',{'remote_job':remote_id})
            except Exception as error:
                try:self.store.report(job['id'],job['lease'],'failed',public_error(error))
                except ValueError:pass


def public_error(error):
    if isinstance(error,urllib.error.HTTPError):
        return f'외부 서버 연결 오류 (HTTP {error.code})'
    if isinstance(error,(urllib.error.URLError,TimeoutError,OSError)):
        return '서버에 연결할 수 없습니다. 연결 설정과 실행 상태를 확인하세요.'
    if isinstance(error,(ValueError,KeyError)):
        return str(error).strip("'")[:500]
    return '작업 처리 중 오류가 발생했습니다. 서버 로그를 확인하세요.'


def image_content_type(data):
    if data.startswith(b'\xff\xd8\xff'):return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):return 'image/png'
    if data.startswith((b'GIF87a',b'GIF89a')):return 'image/gif'
    if data.startswith(b'RIFF') and data[8:12]==b'WEBP':return 'image/webp'
    if data[4:8]==b'ftyp' and (b'avif' in data[8:] or b'avis' in data[8:]):return 'image/avif'
    if data.startswith((b'\xff\x0a',b'\x00\x00\x00\x0cJXL \r\n\x87\n')):return 'image/jxl'
    return None


class Handler(BaseHTTPRequestHandler):
    server_version='LibraryStudio/0.1'

    def log_message(self, format, *args):
        # Do not log URLs, source titles, credentials, or user input.
        return

    @property
    def app(self):return self.server.app

    def worker_scope(self):
        auth=self.headers.get('Authorization','')
        for variable,target in [('STUDIO_PC_WORKER_TOKEN','pc'),('STUDIO_NAS_WORKER_TOKEN','nas'),('STUDIO_WORKER_TOKEN','*')]:
            token=os.environ.get(variable,'')
            if token and hmac.compare_digest(auth,'Bearer '+token):return target
        return None

    def authorized(self):
        auth=self.headers.get('Authorization','')
        if self.worker_scope():
            if self.command=='POST' and re.fullmatch(r'/api/worker/(claim|[0-9a-f]{32}/report)', urllib.parse.urlsplit(self.path).path):
                return True
            self.respond({'error':'Worker token is restricted to worker endpoints'},403)
            return False
        password=os.environ.get('STUDIO_PASSWORD','')
        if password:
            expected='Basic '+base64.b64encode(('admin:'+password).encode()).decode()
            if hmac.compare_digest(auth,expected):return True
        elif self.server.dev:
            host=urllib.parse.urlsplit('http://'+self.headers.get('Host','')).hostname
            if host in ('localhost','127.0.0.1','::1') and self.client_address[0] in ('127.0.0.1','::1'):
                return True
        self.send_response(401);self.send_header('WWW-Authenticate','Basic realm="Library Studio", charset="UTF-8"')
        self.send_header('Content-Length','0');self.end_headers();return False

    def respond(self, value, status=200):
        raw=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

    def body(self):
        length=int(self.headers.get('Content-Length','0'))
        if length<0 or length>4*1024*1024:raise ValueError('요청 크기 제한을 초과했습니다.')
        value=json.loads(self.rfile.read(length))
        if not isinstance(value,dict):raise ValueError('JSON 객체가 필요합니다.')
        return value

    def do_GET(self):
        if not self.authorized():return
        try:self.get()
        except Exception as error:self.respond({'error':public_error(error)},404 if isinstance(error,KeyError) else 502 if isinstance(error,(urllib.error.URLError,OSError)) else 400)

    def get(self):
        parsed=urllib.parse.urlsplit(self.path);path=parsed.path;qs=urllib.parse.parse_qs(parsed.query)
        def q(key,default=''):return qs.get(key,[default])[0]
        store=self.app.store
        if path=='/api/library/status':
            with store.db() as db:
                has_folders=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='folder_imports'").fetchone()
                folders=db.execute('SELECT count(*) FROM folder_imports').fetchone()[0] if has_folders else 0
                pending=db.execute("SELECT count(*) FROM uploads WHERE lrr_id IS NULL AND state='stored'").fetchone()[0]
            return self.respond({'folder_archives':folders,'pending_archives':pending,'folder_registration':'manual','site_downloads':'not-verified'})
        if path=='/api/health':
            try:
                info=self.app.lrr.json('/api/info');connected=True
            except Exception:info={};connected=False
            return self.respond(dict(status='ok',lanraragi_connected=connected,
                                     version=info.get('version'),targets=['nas','pc'],
                                     comment_fetch={'nhentai':'public-json-unverified-live','ehentai':'unsupported','hitomi':'unsupported'},metadata_fetch='installed-plugins',
                                     command_workers='operator-configured',uploads_enabled=self.app.uploads.root is not None,
                                     max_upload_bytes=self.app.uploads.max_bytes))
        if path=='/api/uploads':return self.respond({'items':self.app.uploads.list(),'enabled':self.app.uploads.root is not None,'max_bytes':self.app.uploads.max_bytes})
        match=re.fullmatch(r'/api/uploads/([0-9a-f]{64})/download',path)
        if match:return self.download_upload(match[1])
        if path=='/api/tags':return self.respond(store.tag_catalog(q('q')))
        if path=='/api/library/tags':return self.respond(store.library_tags(q('q')))
        match=re.fullmatch(r'/api/short/([^/]+)',path)
        if match:return self.respond(store.resolve_short_id(match[1]))
        if path=='/api/works':
            return self.respond(store.list_works(q('q'),q('sort','added'),q('direction','desc')=='desc',
                int(q('page','1')),int(q('limit','48')),q('provider'),q('favorite')=='1',q('unread')=='1',q('tag'),q('all_tag')))
        match=re.fullmatch('/api/works/([0-9a-f]{32})',path)
        if match:return self.respond(store.get_work(match[1]))
        if path=='/api/jobs':
            # Worker leases are credentials, never expose them in the browser list.
            return self.respond([store.public_job(j) for j in store.jobs()])
        if path=='/api/export':
            return self.respond(store.export())
        match=re.fullmatch(r'/api/media/([0-9a-f]{40})/(thumbnail|download|files|page)',path)
        if match:
            query='?'+parsed.query if parsed.query else ''
            if match[2]=='files':
                value=self.app.lrr.json('/api/archives/'+match[1]+'/files'+query)
                if isinstance(value.get('pages'),list):
                    with store.db() as db:
                        db.execute('UPDATE works SET pages=? WHERE lrr_id=?',(len(value['pages']),match[1]))
                return self.respond(value)
            with self.app.lrr.open('/api/archives/'+match[1]+'/'+match[2]+query,
                                   headers={'Range':self.headers['Range']} if self.headers.get('Range') else {}) as response:
                prefix=response.read(32) if response.status==200 and match[2] in ('thumbnail','page') else b''
                media_type=image_content_type(prefix)
                self.send_response(response.status)
                if media_type:self.send_header('Content-Type',media_type)
                for key in ('Content-Type','Content-Length','Content-Disposition','Accept-Ranges','Content-Range'):
                    if key=='Content-Type' and media_type:continue
                    if response.headers.get(key):self.send_header(key,response.headers[key])
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Cache-Control','private, max-age=3600' if match[2]=='thumbnail' else 'no-store')
                self.end_headers()
                if prefix:self.wfile.write(prefix)
                while block:=response.read(256*1024):self.wfile.write(block)
            return
        if path.startswith('/api/'):return self.respond({'error':'찾을 수 없습니다.'},404)
        assets={'/':'index.html','/unsen':'index.html','/unsen/':'index.html','/app.js':'app.js','/style.css':'style.css'}
        filename=assets.get(path)
        if not filename:return self.respond({'error':'찾을 수 없습니다.'},404)
        raw=(HERE/'web'/filename).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type',(mimetypes.guess_type(filename)[0] or 'application/octet-stream')+'; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers();self.wfile.write(raw)

    def download_upload(self,sha):
        row,stream=self.app.uploads.open(sha)
        with stream:
            size=row['bytes'];start=0;end=size-1;status=200
            value=self.headers.get('Range')
            if value:
                match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
                if not match or not any(match.groups()):
                    return self.respond({'error':'단일 바이트 범위만 지원합니다.'},416)
                if match[1]:start=int(match[1]);end=min(end,int(match[2])) if match[2] else end
                else:start=max(0,size-int(match[2]))
                if not 0<=start<=end<size:return self.respond({'error':'파일 범위를 초과했습니다.'},416)
                status=206
            self.send_response(status)
            self.send_header('Content-Type','application/octet-stream')
            self.send_header('Content-Disposition',"attachment; filename=download"+Path(row['original_name']).suffix+"; filename*=UTF-8''"+urllib.parse.quote(row['original_name'],safe=''))
            self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes')
            if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
            stream.seek(start);remaining=end-start+1
            while remaining:
                block=stream.read(min(256*1024,remaining))
                if not block:break
                self.wfile.write(block);remaining-=len(block)

    def do_POST(self):
        if not self.authorized():return
        origin=self.headers.get('Origin')
        if origin:
            parsed=urllib.parse.urlsplit(origin)
            if parsed.netloc!=self.headers.get('Host') or parsed.scheme not in ('http','https'):
                return self.respond({'error':'다른 사이트의 요청은 허용하지 않습니다.'},403)
        if urllib.parse.urlsplit(self.path).path=='/api/uploads':
            try:
                if self.headers.get('Transfer-Encoding'):raise UploadError('Content-Length가 있는 파일 요청이 필요합니다.',411)
                if self.headers.get_content_type()!='application/octet-stream':raise UploadError('파일 본문 형식이 올바르지 않습니다.',415)
                values=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                name=values.get('filename',[''])[0]
                tags=self.app.store.user_tag_values(json.loads(values.get('tags',['[]'])[0]))
                self.connection.settimeout(30)
                result=self.app.uploads.receive(self.rfile,int(self.headers.get('Content-Length','0')),name)
                self.app.store.annotate_upload(result['sha256'],tags)
                return self.respond(result,200 if result.get('duplicate') else 201)
            except Exception as error:
                return self.respond({'error':public_error(error)},error.status if isinstance(error,UploadError) else 400)
        if not self.headers.get('Content-Type','').startswith('application/json'):
            return self.respond({'error':'application/json 요청이 필요합니다.'},415)
        try:self.post(self.body())
        except Exception as error:self.respond({'error':public_error(error)},404 if isinstance(error,KeyError) else 502 if isinstance(error,(urllib.error.URLError,OSError)) else 400)

    def post(self, data):
        path=urllib.parse.urlsplit(self.path).path;store=self.app.store
        if path=='/api/downloads/resolve':return self.respond(store.resolve_reference(data.get('provider'),data.get('reference')))
        if path=='/api/downloads':
            return self.respond(store.request_download(data.get('provider'),data.get('reference'),data.get('target'),data.get('engine')))
        if path=='/api/tags/batch':return self.respond(store.edit_user_tags(data.get('work_ids'),data.get('add'),data.get('remove')))
        if path=='/api/tags/rename':return self.respond(store.rename_user_tag(data.get('source'),data.get('target')))
        if path=='/api/uploads/sync':return self.respond(self.app.sync_uploads())
        if path=='/api/sync':return self.respond(self.app.sync())
        if path=='/api/works':return self.respond(store.create_work(data.get('title',''),data.get('artist','')),201)
        match=re.fullmatch('/api/works/([0-9a-f]{32})',path)
        if match:return self.respond(store.update_work(match[1],data))
        match=re.fullmatch('/api/works/([0-9a-f]{32})/sources',path)
        if match:return self.respond(store.upsert_source(match[1],data))
        match=re.fullmatch('/api/works/([0-9a-f]{32})/sources/([0-9a-f]{32})/fetch',path)
        if match:return self.respond(self.app.fetch_metadata(match[1],match[2]))
        match=re.fullmatch('/api/works/([0-9a-f]{32})/sources/([0-9a-f]{32})/comments/fetch',path)
        if match:return self.respond(self.app.fetch_comments(match[1],match[2]))
        match=re.fullmatch('/api/works/([0-9a-f]{32})/progress',path)
        if match:
            store.progress(match[1],data.get('page'));return self.respond({'success':True})
        if path=='/api/jobs':
            return self.respond(store.public_job(store.queue(data.get('url'),data.get('target'),data.get('engine'),data.get('work_id'))),201)
        match=re.fullmatch('/api/jobs/([0-9a-f]{32})/retry',path)
        if match:
            store.expire_jobs()
            job=store.job(match[1]);remote=json.loads(job['result']).get('remote_job')
            if job['engine']=='lanraragi' and remote:
                if not re.fullmatch(r'[0-9]+',str(remote)):raise ValueError('잘못된 원격 작업 ID입니다.')
                status=self.app.lrr.json('/api/minion/'+str(remote)+'/detail')
                store.reconcile_remote(job['id'],remote,status.get('state'))
                if status.get('state')=='finished':return self.respond({'success':True,'reconciled':True})
            store.retry(match[1]);return self.respond({'success':True})
        if path.startswith('/api/worker/'):
            scope=self.worker_scope()
            if not scope:
                return self.respond({'error':'Worker token required'},403)
            if path=='/api/worker/claim':
                if scope!='*' and data.get('target')!=scope:return self.respond({'error':'Worker target mismatch'},403)
                return self.respond(store.claim(data.get('target'),'command'))
            match=re.fullmatch('/api/worker/([0-9a-f]{32})/report',path)
            if match:
                store.report(match[1],data.get('lease'),data.get('state'),data.get('message',''),data.get('result'),worker_target=scope)
                return self.respond({'success':True})
        return self.respond({'error':'찾을 수 없습니다.'},404)


def make_server(host,port,app,dev=False):
    if dev and host not in ('127.0.0.1','::1'):
        raise ValueError('개발용 인증 생략은 루프백에서만 가능합니다.')
    if not dev and not os.environ.get('STUDIO_PASSWORD'):
        raise ValueError('STUDIO_PASSWORD를 설정하세요.')
    server=ThreadingHTTPServer((host,port),Handler);server.app=app;server.dev=dev
    return server


if __name__=='__main__':
    app=Studio(Store(os.environ.get('STUDIO_DATABASE',str(HERE/'data'/'studio.db'))),
               LRR(os.environ.get('LRR_URL','http://127.0.0.1:43121'),os.environ.get('LRR_API_KEY','')))
    host=os.environ.get('STUDIO_HOST','127.0.0.1');port=int(os.environ.get('STUDIO_PORT','43120'))
    server=make_server(host,port,app,os.environ.get('STUDIO_DEV_MODE')=='1')
    threading.Thread(target=app.nas_loop,daemon=True).start()
    if os.environ.get('STUDIO_IMPORT_DIR'):
        from importer import Importer
        importer=Importer(app,os.environ['STUDIO_IMPORT_DIR'])
        threading.Thread(target=importer.run,daemon=True).start()
    print(f'Library Studio: http://{host}:{port}',flush=True)
    try:server.serve_forever()
    finally:app.stop.set();server.server_close()
