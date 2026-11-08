"""Confirmed single-file deletion. Web has no NAS write access; fixed worker does."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import sqlite3
import stat
import time
import uuid

MAX_BYTES=2*1024**3
SCHEMA='''CREATE TABLE IF NOT EXISTS file_deletions (
 id TEXT PRIMARY KEY,work_id TEXT NOT NULL,lrr_id TEXT NOT NULL,
 filename TEXT NOT NULL,sha256 TEXT NOT NULL,bytes INTEGER NOT NULL,
 state TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,
 target TEXT,error TEXT NOT NULL DEFAULT '');
 CREATE UNIQUE INDEX IF NOT EXISTS file_deletions_active ON file_deletions((1))
 WHERE state IN ('queued','deleting');'''
ERRORS={'file_changed':'파일이 변경되어 삭제를 중단했습니다. 다시 확인하세요.',
        'file_missing':'삭제할 파일을 찾지 못했습니다.',
        'file_ambiguous':'같은 파일이 여러 위치에 있어 삭제하지 않았습니다.',
        'work_changed':'작품 연결이 바뀌어 삭제를 중단했습니다.',
        'download_active':'이 작품의 다운로드가 진행 중입니다.',
        'storage_error':'저장소 접근에 실패했습니다. 파일 삭제 상태를 확인하세요.'}


class CpuThrottle:
    """Pace verification around half a CPU; cpuset remains the kernel ceiling."""
    def __init__(self):
        self.cpu=time.process_time();self.wall=time.monotonic()

    def pause(self):
        delay=2*(time.process_time()-self.cpu)-(time.monotonic()-self.wall)
        if delay>0:time.sleep(delay)
        self.cpu=time.process_time();self.wall=time.monotonic()


class WorkerIdentity:
    """Permanently non-root, with DAC only for files and no DAC during SQLite."""
    def __init__(self,uid,gid):
        import ctypes
        import resource
        if os.name!='posix' or os.getuid()!=0 or uid<=0 or gid<=0:raise ValueError('nonroot_worker_bootstrap_required')
        self.uid=uid;self.gid=gid;self.ctypes=ctypes
        class Header(ctypes.Structure):_fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
        class Caps(ctypes.Structure):_fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
        self.Header=Header;self.Caps=Caps;self.libc=ctypes.CDLL(None,use_errno=True)
        resource.setrlimit(resource.RLIMIT_NPROC,(32,32))
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_NICE,(0,0))
        os.nice(19)
        if self.libc.prctl(38,1,0,0,0) or self.libc.prctl(8,1,0,0,0):raise OSError('worker_privilege_setup_failed')
        os.setgroups([]);os.setresgid(gid,gid,gid);os.setresuid(uid,uid,uid)
        self.set_effective(2)
        if self.libc.prctl(8,0,0,0,0):raise OSError('worker_privilege_setup_failed')
        if os.getresuid()!=(uid,uid,uid) or os.getresgid()!=(gid,gid,gid):raise ValueError('worker_identity_mismatch')
        try:os.setuid(0)
        except PermissionError:pass
        else:raise ValueError('worker_root_recovery_not_blocked')
        self.snapshot()

    def set_effective(self,value):
        caps=(self.Caps*2)();caps[0].effective=value;caps[0].permitted=2
        if self.libc.capset(self.ctypes.byref(self.Header(0x20080522,0)),self.ctypes.byref(caps)):
            raise OSError(self.ctypes.get_errno(),'worker_capability_transition_failed')

    @contextlib.contextmanager
    def database_mode(self):
        self.set_effective(0)
        try:yield
        finally:self.set_effective(2)

    def snapshot(self):
        import resource
        caps=(self.Caps*2)()
        if self.libc.capget(self.ctypes.byref(self.Header(0x20080522,0)),self.ctypes.byref(caps)):raise OSError('worker_capability_read_failed')
        if caps[0].permitted!=2 or caps[0].effective!=2 or caps[0].inheritable or caps[1].permitted or caps[1].effective or caps[1].inheritable:raise ValueError('worker_capability_mismatch')
        if resource.getrlimit(resource.RLIMIT_NPROC)!=(32,32) or os.getpriority(os.PRIO_PROCESS,0)!=19:raise ValueError('worker_limit_mismatch')
        if os.getresuid()!=(self.uid,)*3 or os.getresgid()!=(self.gid,)*3:raise ValueError('worker_identity_mismatch')
        if self.libc.prctl(39,0,0,0,0)!=1 or os.getgroups():raise ValueError('worker_privilege_mismatch')
        if sorted(os.sched_getaffinity(0))!=[0]:raise ValueError('worker_cpu_affinity_mismatch')
        return {'mode':'nonroot-rlimit-v2','uid':self.uid,'gid':self.gid,'permitted_caps':2,'file_effective_caps':2,
                'nproc':list(resource.getrlimit(resource.RLIMIT_NPROC)),'nice':19,'no_new_privileges':True,'cpu_affinity':[0],'hash_cpu_target':0.5}


def blocked(db,arcid):
    return db.execute("SELECT 1 FROM file_deletions WHERE lrr_id=? AND state IN ('queued','deleting','complete')",(arcid,)).fetchone() is not None


def restore(db,sha):
    db.execute("UPDATE file_deletions SET state='restored',updated=? WHERE sha256=? AND state='complete'",(time.time(),sha))


class FileDeletion:
    def __init__(self,store,lrr):self.store=store;self.lrr=lrr

    def ready(self):
        with self.store.db() as db:row=db.execute("SELECT value FROM settings WHERE key='file-deletion-worker'").fetchone()
        try:
            info=json.loads(row[0]) if row else {}
            return info.get('code_sha256')==hashlib.sha256(Path(__file__).read_bytes()).hexdigest() and 0<=time.time()-info.get('seen',0)<30
        except (ValueError,TypeError):return False

    def status(self,work_id):
        work=self.store.get_work(work_id)
        with self.store.db() as db:row=db.execute("SELECT * FROM file_deletions WHERE work_id=? ORDER BY CASE WHEN state IN ('queued','deleting','complete') THEN 0 ELSE 1 END,created DESC LIMIT 1",(work['id'],)).fetchone()
        item={key:row[key] for key in ('id','filename','bytes','state','created','updated')} if row else None
        if item:item['message']=ERRORS.get(row['error'],'')
        return {'ready':self.ready(),'request':item}

    def preview(self,work_id):
        if not self.ready():raise ValueError('NAS 파일 삭제 작업자 설치·연결이 필요합니다. 현재 파일은 그대로입니다.')
        work=self.store.get_work(work_id);arcid=work['lrr_id']
        if not arcid or not self.lrr:raise ValueError('라이브러리에 연결된 만화 파일이 없습니다.')
        with self.store.db() as db:
            if blocked(db,arcid):raise ValueError('이 파일의 삭제가 진행 중이거나 이미 완료됐습니다.')
        metadata=self.lrr.json('/api/archives/'+arcid+'/metadata')
        name=Path(str(metadata.get('filename','')).replace('\\','/')).name
        if not name or len(name)>1000 or Path(name).suffix.lower() not in ('.cbz','.zip','.pdf') or any(ord(c)<32 for c in name):
            raise ValueError('실제 만화 파일 이름을 확인할 수 없습니다.')
        digest=hashlib.sha256();prefix=bytearray();size=0
        with self.lrr.open('/api/archives/'+arcid+'/download') as stream:
            while block:=stream.read(256*1024):
                size+=len(block)
                if size>MAX_BYTES:raise ValueError('삭제 확인은 2GiB 이하 파일만 지원합니다.')
                digest.update(block)
                if len(prefix)<512000:prefix.extend(block[:512000-len(prefix)])
        if not size or hashlib.sha1(prefix).hexdigest()!=arcid:raise ValueError('파일과 작품 번호가 일치하지 않습니다.')
        now=time.time();request_id=uuid.uuid4().hex
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT lrr_id FROM works WHERE id=?',(work['id'],)).fetchone()
            if not current or current['lrr_id']!=arcid:raise ValueError('작품 연결이 변경됐습니다. 다시 확인하세요.')
            if blocked(db,arcid):raise ValueError('이 파일의 삭제가 진행 중입니다.')
            db.execute('INSERT INTO file_deletions(id,work_id,lrr_id,filename,sha256,bytes,state,created,updated) VALUES(?,?,?,?,?,?,?, ?,?)',
                       (request_id,work['id'],arcid,name,digest.hexdigest(),size,'preview',now,now))
        return self.status(work['id'])

    def confirm(self,work_id,request_id,filename):
        if not self.ready():raise ValueError('파일 삭제 작업자가 연결되지 않았습니다. 파일은 그대로입니다.')
        work=self.store.get_work(work_id)
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM file_deletions WHERE id=? AND work_id=?',(request_id,work['id'])).fetchone()
            if not row or row['filename']!=filename:raise ValueError('삭제 확인 대상이 일치하지 않습니다.')
            if row['state'] in ('queued','deleting','complete'):return self.status(work['id'])
            if row['state']!='preview' or time.time()-row['created']>300 or work['lrr_id']!=row['lrr_id']:
                raise ValueError('삭제 확인이 만료되었거나 작품이 변경됐습니다. 다시 확인하세요.')
            if db.execute("SELECT 1 FROM file_deletions WHERE state IN ('queued','deleting')").fetchone():raise ValueError('다른 파일의 삭제가 진행 중입니다.')
            if db.execute("SELECT 1 FROM jobs WHERE work_id=? AND state IN ('queued','running')",(work['id'],)).fetchone():raise ValueError(ERRORS['download_active'])
            db.execute("UPDATE file_deletions SET state='queued',updated=? WHERE id=?",(time.time(),request_id))
        return self.status(work['id'])


@contextlib.contextmanager
def directory(path):
    path=Path(path)
    if not path.is_absolute():raise ValueError('storage_error')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=new
        yield fd
    finally:os.close(fd)


def stamp(info):return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns]


class DeletionWorker:
    def __init__(self,database,originals,uploads,uid=None,gid=None,identity=None):
        self.database=Path(database);self.roots={'originals':Path(originals),'uploads':Path(uploads)}
        self.code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.identity=identity;self.throttle=CpuThrottle()
        self.uid=os.geteuid() if uid is None else uid;self.gid=os.getegid() if gid is None else gid
        for root in self.roots.values():
            if root==Path('/') or root.is_symlink():raise ValueError('storage_error')
            with directory(root):pass
        a,b=[p.resolve() for p in self.roots.values()]
        if a.is_relative_to(b) or b.is_relative_to(a):raise ValueError('storage_error')
        self.unlinked=False

    @contextlib.contextmanager
    def db(self):
        old_uid,old_gid=os.geteuid(),os.getegid();db=None
        try:
            if old_uid==0:os.setegid(self.gid);os.seteuid(self.uid)
            if self.identity:self.identity.set_effective(0)
            info=self.database.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.uid:raise ValueError('storage_error')
            db=sqlite3.connect(self.database,timeout=15);db.row_factory=sqlite3.Row
            db.execute('PRAGMA trusted_schema=OFF')
            with db:yield db
        finally:
            if db:db.close()
            if self.identity:self.identity.set_effective(2)
            if old_uid==0:os.seteuid(old_uid);os.setegid(old_gid)

    def check_work(self,db,row):
        if not re.fullmatch('[0-9a-f]{32}',row['work_id']) or not re.fullmatch('[0-9a-f]{40}',row['lrr_id']) or not re.fullmatch('[0-9a-f]{64}',row['sha256']) or type(row['bytes']) is not int or not 0<row['bytes']<=MAX_BYTES or Path(row['filename']).name!=row['filename'] or len(row['filename'])>1000:raise ValueError('storage_error')
        current=db.execute('SELECT lrr_id FROM works WHERE id=?',(row['work_id'],)).fetchone()
        if not current or current['lrr_id']!=row['lrr_id']:raise ValueError('work_changed')
        if db.execute("SELECT 1 FROM jobs WHERE work_id=? AND state IN ('queued','running')",(row['work_id'],)).fetchone():raise ValueError('download_active')

    def inspect(self,parent,name,row):
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size!=row['bytes'] or not 0<info.st_size<=MAX_BYTES:raise ValueError('file_changed')
            digest=hashlib.sha256();received=0
            while block:=stream.read(256*1024):
                received+=len(block)
                if received>row['bytes']:raise ValueError('file_changed')
                digest.update(block);self.throttle.pause()
            if received!=row['bytes'] or digest.hexdigest()!=row['sha256'] or stamp(info)!=stamp(os.fstat(stream.fileno())):raise ValueError('file_changed')
            return stamp(info)

    def find(self,row):
        matches=[];visited=0
        with self.db() as db:upload=db.execute('SELECT stored_name FROM uploads WHERE lrr_id=? AND sha256=?',(row['lrr_id'],row['sha256'])).fetchone()
        # Upload filenames are content-addressed; original files keep their real name.
        names={'originals':row['filename'],'uploads':row['sha256']+Path(row['filename']).suffix.lower()}
        if upload:
            if upload['stored_name'] not in (row['sha256']+'.cbz',row['sha256']+'.pdf'):raise ValueError('file_changed')
            names['uploads']=upload['stored_name']
        for label,root in self.roots.items():
            for current,dirs,files,parent in os.fwalk(root,follow_symlinks=False):
                self.throttle.pause()
                visited+=1
                if visited>20000 or len(Path(current).relative_to(root).parts)>16:raise ValueError('storage_error')
                relative=Path(current).relative_to(root)
                if label=='originals' and not relative.parts:dirs[:]=[d for d in dirs if d in ('manga','images')]
                else:dirs[:]=[d for d in dirs if not d.startswith(('@','#','.'))]
                if names[label] not in files:continue
                try:identity=self.inspect(parent,names[label],row)
                except (ValueError,OSError):continue
                matches.append({'root':label,'path':(relative/names[label]).as_posix(),'stamp':identity})
        if len(matches)!=1:raise ValueError('file_ambiguous' if matches else 'file_missing')
        return matches[0]

    def remove(self,row,target):
        path=PurePosixPath(target['path']);label=target['root']
        if label not in self.roots or path.is_absolute() or any(p in ('','.','..') for p in path.parts):raise ValueError('storage_error')
        if label=='originals' and (len(path.parts)<2 or path.parts[0] not in ('manga','images')):raise ValueError('storage_error')
        if any(p.startswith(('@','#','.')) for p in path.parts):raise ValueError('storage_error')
        if label=='uploads' and (len(path.parts)!=1 or path.name not in (row['sha256']+'.cbz',row['sha256']+'.pdf')):raise ValueError('storage_error')
        with directory(self.roots[label]/path.parent) as parent:
            try:current=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError:self.unlinked=True;return  # Resume the durable unlink intent after a crash.
            if stamp(current)!=target['stamp'] or self.inspect(parent,path.name,row)!=target['stamp']:raise ValueError('file_changed')
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE');self.check_work(db,row)
            # db() restores the worker's file-access identity before the unlink.
            if stamp(os.stat(path.name,dir_fd=parent,follow_symlinks=False))!=target['stamp']:raise ValueError('file_changed')
            os.unlink(path.name,dir_fd=parent);self.unlinked=True;os.fsync(parent)

    def tick(self):
        self.unlinked=False
        runtime=self.identity.snapshot() if self.identity else None
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            value={'seen':time.time(),'code_sha256':self.code_sha256}
            if runtime:value['runtime']=runtime
            db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('file-deletion-worker',?)",(json.dumps(value),))
            row=db.execute("SELECT * FROM file_deletions WHERE state IN ('queued','deleting') ORDER BY created LIMIT 1").fetchone()
            if not row:return False
            row=dict(row);db.execute("UPDATE file_deletions SET state='deleting',updated=? WHERE id=?",(time.time(),row['id']))
        try:
            with self.db() as db:self.check_work(db,row)
            target=json.loads(row['target']) if row['target'] else self.find(row)
            with self.db() as db:
                self.check_work(db,row)
                db.execute('UPDATE file_deletions SET target=?,updated=? WHERE id=?',(json.dumps(target),time.time(),row['id']))
            self.remove(row,target)
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE');self.check_work(db,row)
                db.execute('UPDATE works SET lrr_id=NULL,pages=0,bytes=0 WHERE id=?',(row['work_id'],))
                db.execute("UPDATE uploads SET lrr_id=NULL,state='retired' WHERE lrr_id=? AND sha256=?",(row['lrr_id'],row['sha256']))
                db.execute("UPDATE file_deletions SET state='complete',updated=?,error='' WHERE id=?",(time.time(),row['id']))
        except Exception as error:
            if self.unlinked:raise  # Keep the intent for recovery; never attempt a second path.
            with self.db() as db:db.execute("UPDATE file_deletions SET state='failed',updated=?,error=? WHERE id=?",(time.time(),str(error) if str(error) in ERRORS else 'storage_error',row['id']))
        return True


def probe_limits(uid,gid):
    """Disposable kernel test; called without any media or catalog mounts."""
    import errno
    import tempfile
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
        root=Path(temporary);root.chmod(0o711)
        source=root/'generated-root-only';source.write_bytes(b'Generated deletion worker fixture');source.chmod(0)
        dbdir=root/'database';dbdir.mkdir(mode=0o777);dbdir.chmod(0o777)
        identity=WorkerIdentity(uid,gid)
        assert source.read_bytes()==b'Generated deletion worker fixture'
        with identity.database_mode():
            try:source.read_bytes()
            except PermissionError:pass
            else:raise ValueError('database_capability_not_dropped')
            with sqlite3.connect(dbdir/'generated.db') as db:db.execute('CREATE TABLE fixture(value)')
            if (dbdir/'generated.db').stat().st_uid!=uid:raise ValueError('database_owner_mismatch')
        children=[];limited=False;readfd,writefd=os.pipe()
        try:
            for _ in range(40):
                try:child=os.fork()
                except OSError as error:
                    if error.errno!=errno.EAGAIN:raise
                    limited=True;break
                if child==0:
                    os.close(writefd);os.read(readfd,1);os._exit(0)
                children.append(child)
        finally:
            os.close(writefd);os.close(readfd)
            for child in children:os.waitpid(child,0)
        if not limited or len(children)>31:raise ValueError('nproc_kernel_limit_not_observed')
        result={**identity.snapshot(),'kernel_nproc_block_observed':True,'children_started':len(children),
                'database_owner_preserved':True,'database_dac_disabled':True,'root_recovery_blocked':True}
        print(json.dumps(result),flush=True)


def main():
    import fcntl
    parser=argparse.ArgumentParser();parser.add_argument('--database');parser.add_argument('--originals');parser.add_argument('--uploads')
    parser.add_argument('--writer-uid',type=int,required=True);parser.add_argument('--writer-gid',type=int,required=True);parser.add_argument('--once',action='store_true')
    parser.add_argument('--probe-limits',action='store_true')
    args=parser.parse_args()
    if args.writer_uid<=0 or args.writer_gid<=0:raise SystemExit('Non-root catalog owner required')
    if args.probe_limits:
        if args.database or args.originals or args.uploads:parser.error('Limit probe must not receive production paths')
        return probe_limits(args.writer_uid,args.writer_gid)
    if not all((args.database,args.originals,args.uploads)):parser.error('Database and media roots are required')
    identity=WorkerIdentity(args.writer_uid,args.writer_gid)
    worker=DeletionWorker(args.database,args.originals,args.uploads,args.writer_uid,args.writer_gid,identity)
    with worker.db():
        lock=os.open(str(args.database)+'.file-deletion.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(lock,'w') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            try:worker.tick()
            except (OSError,ValueError,sqlite3.Error):pass  # Durable intents resume; paths and private names are never logged.
            if args.once:return
            time.sleep(1)


if __name__=='__main__':main()
