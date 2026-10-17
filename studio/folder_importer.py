"""NAS-local image-folder to CBZ import. Default plan never opens a database.

Sources are read-only, traversed with directory descriptors and O_NOFOLLOW.
Only generated CBZs/receipts are written to Studio's dedicated volumes.
"""
import argparse
import contextlib
import functools
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import time
import zipfile

from backup import copy_database
from server import image_content_type
from store import Store
from uploads import Uploads, UploadError

SUFFIXES={'.jpg','.jpeg','.png','.webp','.gif','.avif','.jxl'}
IGNORED={'@eaDir','@tmp','#recycle'}


def natural_key(name):
    return tuple((1,int(part)) if part.isascii() and part.isdigit() else (0,part.casefold())
                 for part in re.split(r'([0-9]+)',name))+( (0,name), )


def allowed_name(name):
    return not name.startswith('.') and name not in IGNORED


def access_error(error):
    # OSError text may contain a personal filename. Return only its standard
    # errno description; validation messages here are our own fixed strings.
    if isinstance(error,OSError):
        return {'code':'filesystem_error','errno':error.errno,
                'message':os.strerror(error.errno) if error.errno else 'Filesystem access failed'}
    return {'code':'validation_failed','message':str(error)[:160] if isinstance(error,ValueError) else 'Stored record unavailable'}


def source_access(method):
    @functools.wraps(method)
    def call(self,*args,**kwargs):
        with self.source_identity():return method(self,*args,**kwargs)
    return call


class FolderImporter:
    def __init__(self,root,collections,uploads=None,stable_seconds=30,max_pages=2000,max_entries=10000,source_identity=None):
        self.root=Path(root).absolute();self.collections=[];self.uploads=uploads
        self.source_identity=source_identity or contextlib.nullcontext
        self.stable_seconds=stable_seconds;self.max_pages=max_pages;self.max_entries=max_entries
        with self.source_identity():
            if self.root.is_symlink() or not self.root.is_dir():raise ValueError('확인된 읽기 전용 원본 폴더가 필요합니다.')
        if not isinstance(collections,list) or not 1<=len(collections)<=32:raise ValueError('가져올 하위 폴더를 1~32개 지정하세요.')
        for name in collections:
            if not isinstance(name,str) or not name or len(name)>100 or any(c in name for c in '\\\r\n\0'):
                raise ValueError('하위 폴더 이름이 올바르지 않습니다.')
            path=PurePosixPath(name)
            if path.is_absolute() or any(p in ('','.','..') or not allowed_name(p) for p in name.split('/')):
                raise ValueError('하위 폴더는 원본 루트 안의 상대 경로여야 합니다.')
            if any(path==prior or path in prior.parents or prior in path.parents for prior in self.collections):
                raise ValueError('중복되거나 겹치는 하위 폴더는 분리하세요.')
            self.collections.append(path)
        if uploads:
            if uploads.root is None:raise ValueError('전용 업로드 저장소가 필요합니다.')
            with self.source_identity():source=self.root.resolve()
            destination=uploads.root
            if source==destination or source in destination.parents or destination in source.parents:
                raise ValueError('원본과 전용 저장소는 분리하세요.')
            with uploads.store.db() as db:
                db.execute('''CREATE TABLE IF NOT EXISTS folder_imports (
                    root TEXT NOT NULL,path TEXT NOT NULL,snapshot TEXT NOT NULL,
                    sha256 TEXT NOT NULL REFERENCES uploads(sha256),PRIMARY KEY(root,path))''')
        self.root_id=hashlib.sha256(str(self.root).encode()).hexdigest()
        self.cursor_key='folder-scan:'+self.root_id+':'+hashlib.sha256(json.dumps(collections).encode()).hexdigest()

    @contextlib.contextmanager
    def directory(self,relative):
        with self.source_identity():fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            with self.source_identity():
                for part in relative.parts:
                    child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                    os.close(fd);fd=child
            # Never yield with source privileges: callers may write the DB.
            yield fd
        finally:os.close(fd)

    @source_access
    def entries(self,fd):
        result=[]
        with os.scandir(fd) as entries:
            for entry in entries:
                if len(result)>=self.max_entries:raise ValueError('한 폴더의 항목 수 한도를 초과했습니다.')
                result.append(entry.name)
        return sorted(result,key=natural_key)

    @source_access
    def snapshot(self,fd):
        pages=[];children=[];ready=True
        for name in self.entries(fd):
            if not allowed_name(name):continue
            info=os.stat(name,dir_fd=fd,follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):children.append(name)
            if not stat.S_ISREG(info.st_mode) or Path(name).suffix.lower() not in SUFFIXES:continue
            if not 1<=info.st_size<=64*1024**2:raise ValueError('이미지 크기 한도(64 MiB)를 확인하세요.')
            if len(pages)>=self.max_pages:raise ValueError('폴더당 이미지 수 한도를 초과했습니다.')
            pages.append((name,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_dev,info.st_ino))
            ready=ready and time.time()-info.st_mtime>=self.stable_seconds
        directory=os.fstat(fd)
        ready=ready and time.time()-directory.st_mtime>=self.stable_seconds
        identity=(directory.st_dev,directory.st_ino)
        signature=hashlib.sha256(json.dumps([identity,pages],ensure_ascii=False).encode()).hexdigest()
        return pages,children,ready,signature,identity

    def remembered(self,relative,signature):
        with self.uploads.store.db() as db:
            row=db.execute('SELECT sha256 FROM folder_imports WHERE root=? AND path=? AND snapshot=?',
                           (self.root_id,str(relative),signature)).fetchone()
        if row:
            try:
                _,stream=self.uploads.open(row[0]);stream.close();return True
            except (FileNotFoundError,KeyError):pass
        return False

    def package(self,relative,fd,snapshot):
        pages,_,ready,signature,identity=snapshot
        if not ready:raise ValueError('원본 복사 완료와 30초 안정화를 기다립니다.')
        total=sum(p[1] for p in pages)
        # Room for the generated archive plus Uploads.receive's validated copy.
        bound=total+len(pages)*256+16384
        if bound>self.uploads.max_bytes:raise UploadError('폴더가 CBZ 크기 한도를 초과합니다.',413)
        self.uploads.root.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(self.uploads.root).free<2*bound+64*1024**2:
            raise UploadError('CBZ 생성과 저장을 위한 여유 공간이 부족합니다.',503)
        staging=self.uploads.root/'.staging';staging.mkdir(exist_ok=True)
        if staging.is_symlink():raise ValueError('전용 임시 저장소를 확인하세요.')
        with tempfile.TemporaryDirectory(prefix='folder-',dir=staging) as temporary:
            # LANraragi watches this shared volume recursively. A final archive
            # extension here could expose a partially written CBZ to its indexer.
            archive=Path(temporary)/'book.part'
            with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_STORED) as cbz:
                # Unique prefix also prevents upstream's partial-file ID from
                # conflating books with a shared large first page.
                provenance={'format':1,'folder':str(relative),'snapshot':signature,
                            'pages':[p[0] for p in pages]}
                entry=zipfile.ZipInfo('studio-folder.json');entry.external_attr=0o100644<<16
                cbz.writestr(entry,json.dumps(provenance,ensure_ascii=False))
                for index,page in enumerate(pages,1):
                    name,size,*_=page
                    with self.source_identity():
                        image_fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
                    with os.fdopen(image_fd,'rb') as source:
                        info=os.fstat(source.fileno())
                        observed=(name,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_dev,info.st_ino)
                        if not stat.S_ISREG(info.st_mode) or observed!=page:raise ValueError('읽기 전 원본이 변경됐습니다.')
                        prefix=source.read(32)
                        if not image_content_type(prefix):raise ValueError('지원하는 이미지 형식이 아닙니다.')
                        entry=zipfile.ZipInfo(f'{index:06d}'+Path(name).suffix.lower())
                        entry.external_attr=0o100644<<16
                        with cbz.open(entry,'w') as target:
                            target.write(prefix);remaining=size-len(prefix)
                            while remaining:
                                block=source.read(min(256*1024,remaining))
                                if not block:raise ValueError('읽는 중 원본이 변경됐습니다.')
                                target.write(block);remaining-=len(block)
                        after=os.fstat(source.fileno())
                        if observed!=(name,after.st_size,after.st_mtime_ns,after.st_ctime_ns,after.st_dev,after.st_ino):
                            raise ValueError('읽는 중 원본이 변경됐습니다.')
            with self.directory(relative) as current:
                after=self.snapshot(current)
                if after[3]!=signature or after[4]!=identity:raise ValueError('가져오기 중 원본 폴더가 변경됐습니다.')
            title=relative.name
            safe=''.join(c if c not in '/\\\r\n\0' else '_' for c in title)
            while len((safe+'.cbz').encode())>255:safe=safe[:-1]
            with archive.open('rb') as stream:
                result=self.uploads.receive(stream,archive.stat().st_size,(safe or 'image-folder')+'.cbz')
            tag='folder:'+str(relative)
            if len(tag)>120:
                tag='folder:'+str(next(p for p in self.collections if p==relative or p in relative.parents))
            self.uploads.store.annotate_upload(result['sha256'],[tag])
            with self.uploads.store.db() as db:
                db.execute('INSERT OR REPLACE INTO folder_imports VALUES(?,?,?,?)',
                           (self.root_id,str(relative),signature,result['sha256']))
            return result

    def scan(self,limit=1,max_directories=1000):
        if not 1<=limit<=100 or not 1<=max_directories<=10000:raise ValueError('검사 한도를 확인하세요.')
        result=dict(directories=0,ready=0,deferred=0,imported=0,unchanged=0,errors=0,pages=0,source_bytes=0,estimated_archive_bytes=0,issues=[])
        pending=self.pending()
        while pending and result['directories']<max_directories:
            relative=pending.pop();result['directories']+=1
            if len(relative.parts)>32:result['errors']+=1;continue
            try:
                with self.directory(relative) as fd:
                    snapshot=self.snapshot(fd);pages,children,ready,signature,_=snapshot
                    if len(pending)+len(children)>20000:raise ValueError('범위가 너무 큽니다. 하위 폴더를 나눠 지정하세요.')
                    pending.extend(relative/name for name in reversed(children))
                    if not pages:continue
                    result['pages']+=len(pages)
                    total=sum(page[1] for page in pages)
                    result['source_bytes']+=total
                    result['estimated_archive_bytes']+=total+len(pages)*256+16384
                    if not ready:result['deferred']+=1;continue
                    result['ready']+=1
                    if self.uploads:
                        if self.remembered(relative,signature):result['unchanged']+=1;continue
                        self.package(relative,fd,snapshot);result['imported']+=1
                        if result['imported']>=limit:break
            except (OSError,ValueError,KeyError) as error:
                result['errors']+=1
                if len(result['issues'])<20:
                    # Collection names are explicitly configured, unlike private
                    # descendant book/image names. Never include the latter.
                    collection=next(p for p in self.collections if p==relative or p in relative.parents)
                    issue={'collection':str(collection),**access_error(error)}
                    if issue not in result['issues']:result['issues'].append(issue)
        self.save_pending(pending)
        result['bounded']=bool(pending)
        return result

    def diagnose(self):
        result={'uid':os.getuid(),'gid':os.getgid(),'groups':os.getgroups(),'paths':[],'errors':0}
        for label,relative in [('source',PurePosixPath('.'))]+[(str(p),p) for p in self.collections]:
            item={'label':label};result['paths'].append(item)
            try:
                if relative.parts:
                    with self.directory(relative.parent) as parent:
                        info=os.stat(relative.name,dir_fd=parent,follow_symlinks=False)
                else:info=self.root.lstat()
                item.update(uid=info.st_uid,gid=info.st_gid,mode=oct(stat.S_IMODE(info.st_mode)),
                            symlink=stat.S_ISLNK(info.st_mode))
                with self.directory(relative) as fd:
                    item['opened']=True
                    item['read_only_mount']=bool(os.fstatvfs(fd).f_flag&os.ST_RDONLY)
                    if relative.parts:
                        pages,children,stable,_,_=self.snapshot(fd)
                        item.update(direct_images=len(pages),child_directories=len(children),stable=stable)
                    else:
                        wanted={p.parts[0].casefold() for p in self.collections}
                        item['matching_collection_names']=[name for name in self.entries(fd) if name.casefold() in wanted]
            except (OSError,ValueError) as error:
                item['error']=access_error(error);result['errors']+=1
        mapping=Path('/proc/self/uid_map')
        if mapping.is_file():result['uid_map']=mapping.read_text().strip()
        return result

    def pending(self):
        if self.uploads:
            with self.uploads.store.db() as db:
                row=db.execute('SELECT value FROM settings WHERE key=?',(self.cursor_key,)).fetchone()
            if row:
                values=json.loads(row[0])
                if not isinstance(values,list) or len(values)>20000:raise ValueError('가져오기 검사 상태를 확인하세요.')
                paths=[]
                for name in values:
                    if not isinstance(name,str):raise ValueError('가져오기 검사 경로가 올바르지 않습니다.')
                    path=PurePosixPath(name)
                    if path.is_absolute() or any(p in ('','.','..') or not allowed_name(p) for p in name.split('/')) or not any(p==path or p in path.parents for p in self.collections):
                        raise ValueError('가져오기 검사 경로가 원본 범위를 벗어납니다.')
                    paths.append(path)
                if paths:return paths
        return list(reversed(self.collections))

    def save_pending(self,pending):
        if self.uploads:
            with self.uploads.store.db() as db:
                if pending:
                    db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',
                               (self.cursor_key,json.dumps([str(p) for p in pending],ensure_ascii=False)))
                else:db.execute('DELETE FROM settings WHERE key=?',(self.cursor_key,))

    def choose_pilot(self,max_bytes,max_directories=1000):
        """Choose one small, stable folder locally without emitting its name."""
        pending=list(reversed(self.collections));examined=0
        while pending and examined<max_directories:
            relative=pending.pop();examined+=1
            if len(relative.parts)>32:raise ValueError('시험 폴더의 깊이 한도를 초과했습니다.')
            with self.directory(relative) as fd:
                pages,children,stable,signature,_=self.snapshot(fd)
                if len(pending)+len(children)>20000:raise ValueError('선택한 시험 범위를 줄이세요.')
                pending.extend(relative/name for name in reversed(children))
                bound=sum(p[1] for p in pages)+len(pages)*256+16384
                if pages and stable and bound<=max_bytes:return str(relative),signature
        raise ValueError('시험 크기 한도 안의 안정된 이미지 폴더를 찾지 못했습니다.')


def pilot_import(root,collections,database,destination,max_bytes=128*1024**2,require_read_only=True,source_identity=None):
    """Back up first, then import the same one pinned folder on every retry.

    Selection/lock/backups remain in the dedicated NAS data volume. This never
    advances the bulk cursor or prints the selected private folder's name.
    """
    import fcntl
    database=Path(database).absolute()
    if database.is_symlink() or not database.is_file():raise ValueError('기존 Studio 전용 DB를 확인하세요.')
    if not 1<=max_bytes<=512*1024**2:raise ValueError('시험 파일 크기 한도를 확인하세요.')
    inspector=FolderImporter(root,collections,source_identity=source_identity)
    with inspector.directory(PurePosixPath('.')) as fd:
        info=os.fstat(fd)
        if require_read_only and not os.fstatvfs(fd).f_flag&os.ST_RDONLY:
            raise ValueError('시험 원본은 읽기 전용 mount여야 합니다.')
        identity=[info.st_dev,info.st_ino]
    state=database.parent/'folder-pilot.json'
    lock=database.parent/'folder-pilot.lock'
    lock_fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):raise ValueError('시험 잠금 파일을 확인하세요.')
        try:fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('다른 한 폴더 시험 작업이 실행 중입니다.') from None
        if state.exists() or state.is_symlink():
            state_fd=os.open(state,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(state_fd,'rb') as stream:
                data=stream.read(65537)
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or len(data)>65536:
                    raise ValueError('시험 선택 기록을 확인하세요.')
            saved=json.loads(data)
            if not isinstance(saved,dict) or saved.get('format')!=1 or saved.get('source')!=identity or saved.get('collections')!=collections:
                raise ValueError('시험 원본 또는 컬렉션이 이전 선택과 다릅니다. 자동으로 다른 폴더를 선택하지 않습니다.')
            name=saved.get('relative');signature=saved.get('snapshot')
            if not isinstance(name,str) or not isinstance(signature,str) or not re.fullmatch('[0-9a-f]{64}',signature):
                raise ValueError('시험 선택 기록 형식이 올바르지 않습니다.')
            relative=PurePosixPath(name)
            if relative.is_absolute() or any(p in ('','.','..') or not allowed_name(p) for p in name.split('/')) or not any(p==relative or p in relative.parents for p in inspector.collections):
                raise ValueError('시험 선택이 원본 범위를 벗어납니다.')
        else:
            name,signature=inspector.choose_pilot(max_bytes)
            relative=PurePosixPath(name)
            saved={'format':1,'source':identity,'collections':collections,'relative':name,'snapshot':signature}
            temporary=None
            try:
                fd,path=tempfile.mkstemp(prefix='.folder-selection-',dir=database.parent)
                temporary=Path(path)
                with os.fdopen(fd,'w',encoding='utf-8') as stream:
                    json.dump(saved,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
                os.link(temporary,state)
                directory_fd=os.open(database.parent,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(directory_fd)
                finally:os.close(directory_fd)
            finally:
                if temporary:temporary.unlink(missing_ok=True)
        with inspector.directory(relative) as fd:
            snapshot=inspector.snapshot(fd)
            if snapshot[3]!=signature or not snapshot[2]:
                raise ValueError('고정한 시험 폴더가 변경됐거나 안정화 대기 중입니다. 기존 선택을 보존하고 중단합니다.')
        # Store() can migrate tables. Snapshot the live WAL database before any
        # such initialization or archive publication.
        backups=database.parent/'folder-pilot-backups'
        if backups.is_symlink():raise ValueError('전용 시험 백업 경로를 확인하세요.')
        backups.mkdir(mode=0o700,exist_ok=True)
        backup=backups/('before-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+os.urandom(8).hex()+'.db')
        verification=copy_database(database,backup)
        uploads=Uploads(Store(database),destination,max_bytes)
        importer=FolderImporter(root,collections,uploads,source_identity=source_identity)
        with importer.directory(relative) as fd:
            current=importer.snapshot(fd)
            if current[3]!=signature or not current[2]:raise ValueError('백업 중 원본이 변경됐습니다. 시험 등록을 중단합니다.')
            unchanged=importer.remembered(relative,signature)
            if not unchanged:importer.package(relative,fd,current)
        return {'errors':0,'imported':0 if unchanged else 1,'unchanged':1 if unchanged else 0,
                'pages':len(current[0]),'fixed_selection':True,
                'backup':backup.relative_to(database.parent).as_posix(),'backup_sha256':verification['sha256']}
    finally:os.close(lock_fd)


class RootSourceIdentity:
    """Single-threaded root reader; all destination operations use the app UID.

    Real/saved UID remains root in this explicitly invoked disposable worker.
    Effective IDs are elevated only for source traversal/open/stat. Open source
    descriptors remain readable after dropping back to the output identity.
    """
    @contextlib.contextmanager
    def source(self):
        uid,gid=os.geteuid(),os.getegid()
        os.seteuid(0)
        try:
            os.setegid(0)
            yield
        finally:
            os.setegid(gid);os.seteuid(uid)

    @contextlib.contextmanager
    def output(self,uid,gid):
        groups=os.getgroups()
        os.setgroups([])
        try:
            os.setegid(gid);os.seteuid(uid)
            yield
        finally:
            os.seteuid(0);os.setegid(0);os.setgroups(groups)


@contextlib.contextmanager
def root_app_writer(database,destination,output_uid,output_gid):
    if not hasattr(os,'geteuid') or os.getuid()!=0 or os.geteuid()!=0:
        raise ValueError('root 원본 읽기 시험은 명시적으로 UID0으로 실행해야 합니다.')
    for value in (output_uid,output_gid):
        if type(value) is not int or not 1<=value<=2147483647:
            raise ValueError('현재 앱의 확인된 비루트 출력 UID/GID가 필요합니다.')
    database=Path(database).absolute();destination=Path(destination).absolute()
    # Only the previously initialized dedicated app volumes may be written.
    for path,name in ((database.parent,'studio'),(destination,'uploads')):
        if path.is_symlink() or not path.is_dir() or path.resolve()!=path:
            raise ValueError('확인된 앱 전용 볼륨 경로가 필요합니다.')
        info=path.stat()
        if (info.st_uid,info.st_gid)!=(output_uid,output_gid):
            raise ValueError('앱 전용 볼륨의 소유 ID가 예상과 다릅니다.')
        fd=os.open(path/'.studio-volume.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('앱 전용 볼륨 식별 기록을 확인하세요.')
            marker=stream.read(4097)
            if len(marker)>4096:
                raise ValueError('앱 전용 볼륨 식별 기록을 확인하세요.')
        if json.loads(marker)!={'format':1,'name':name,'uid':output_uid,'gid':output_gid}:
            raise ValueError('앱 전용 볼륨 식별자 또는 출력 ID가 다릅니다.')
    info=database.lstat()
    if not stat.S_ISREG(info.st_mode) or (info.st_uid,info.st_gid)!=(output_uid,output_gid):
        raise ValueError('기존 앱 DB의 형식과 소유 ID를 확인하세요.')
    identity=RootSourceIdentity()
    with identity.output(output_uid,output_gid):
        yield identity


def root_pilot_import(root,collections,database,destination,output_uid,output_gid):
    with root_app_writer(database,destination,output_uid,output_gid) as identity:
        result=pilot_import(root,collections,database,destination,source_identity=identity.source)
        return {**result,'root_source_reader':True,'output_uid':os.geteuid(),'output_gid':os.getegid()}


def batch_import(root,collections,database,destination,limit=10,source_identity=None,require_read_only=True):
    """Continue a bounded scan, backing up first and keeping prior receipts."""
    import fcntl
    if type(limit) is not int or not 1<=limit<=10:raise ValueError('한 번에 1~10개 폴더만 등록하세요.')
    database=Path(database).absolute()
    if database.is_symlink() or not database.is_file():raise ValueError('기존 Studio 전용 DB를 확인하세요.')
    inspector=FolderImporter(root,collections,source_identity=source_identity)
    with inspector.directory(PurePosixPath('.')) as fd:
        if require_read_only and not os.fstatvfs(fd).f_flag&os.ST_RDONLY:raise ValueError('등록 원본은 읽기 전용 mount여야 합니다.')
    lock_fd=os.open(database.parent/'folder-pilot.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):raise ValueError('등록 잠금 파일을 확인하세요.')
        try:fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('다른 폴더 등록 작업이 실행 중입니다.') from None
        backups=database.parent/'folder-import-backups'
        if backups.is_symlink():raise ValueError('전용 백업 경로를 확인하세요.')
        backups.mkdir(mode=0o700,exist_ok=True)
        backup=backups/('before-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+os.urandom(8).hex()+'.db')
        verification=copy_database(database,backup)
        uploads=Uploads(Store(database),destination,512*1024**2)
        result=FolderImporter(root,collections,uploads,source_identity=source_identity).scan(limit)
        return {**result,'batch_limit':limit,'backup':backup.relative_to(database.parent).as_posix(),'backup_sha256':verification['sha256']}
    finally:os.close(lock_fd)


def root_batch_import(root,collections,database,destination,output_uid,output_gid,limit=10):
    with root_app_writer(database,destination,output_uid,output_gid) as identity:
        result=batch_import(root,collections,database,destination,limit,source_identity=identity.source)
        return {**result,'root_source_reader':True,'output_uid':os.geteuid(),'output_gid':os.getegid()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation',choices=['plan','diagnose','import','pilot','root-pilot','root-plan','root-batch'],default='plan')
    parser.add_argument('--root',default=os.environ.get('STUDIO_FOLDER_ROOT','/nas-library'))
    parser.add_argument('--collections',default=os.environ.get('STUDIO_FOLDER_COLLECTIONS','["manga","images"]'))
    parser.add_argument('--limit',type=int,default=1)
    args=parser.parse_args();uploads=None
    if args.operation=='root-plan':
        try:
            if os.geteuid()!=0:raise ValueError('root 원본 검사는 UID0으로 실행하세요.')
            inspector=FolderImporter(args.root,json.loads(args.collections))
            with inspector.directory(PurePosixPath('.')) as fd:
                if not os.fstatvfs(fd).f_flag&os.ST_RDONLY:raise ValueError('검사 원본은 읽기 전용 mount여야 합니다.')
            result=inspector.scan()
        except Exception as error:
            print(json.dumps({'operation':args.operation,'errors':1,'error':access_error(error)},ensure_ascii=False));raise SystemExit(1) from None
        print(json.dumps({'operation':args.operation,**result},sort_keys=True))
        if result['errors']:raise SystemExit(1)
        return
    if args.operation in ('pilot','root-pilot','root-batch'):
        database=os.environ.get('STUDIO_DATABASE');destination=os.environ.get('STUDIO_UPLOAD_DIR')
        if not database or not destination:parser.error('Set verified dedicated database and upload paths')
        try:
            if args.operation in ('root-pilot','root-batch'):
                method=root_pilot_import if args.operation=='root-pilot' else root_batch_import
                options={} if args.operation=='root-pilot' else {'limit':args.limit}
                result=method(args.root,json.loads(args.collections),database,destination,
                    int(os.environ['STUDIO_FOLDER_OUTPUT_UID']),int(os.environ['STUDIO_FOLDER_OUTPUT_GID']),**options)
            else:result=pilot_import(args.root,json.loads(args.collections),database,destination)
        except Exception as error:
            print(json.dumps({'operation':args.operation,'errors':1,'error':access_error(error)},ensure_ascii=False))
            raise SystemExit(1) from None
        print(json.dumps({'operation':args.operation,**result},sort_keys=True))
        if result['errors']:raise SystemExit(1)
        return
    if args.operation=='import':
        database=os.environ.get('STUDIO_DATABASE');destination=os.environ.get('STUDIO_UPLOAD_DIR')
        if not database or not destination:parser.error('Set verified dedicated database and upload paths')
        uploads=Uploads(Store(database),destination,int(os.environ.get('STUDIO_MAX_UPLOAD_BYTES',512*1024**2)))
    importer=FolderImporter(args.root,json.loads(args.collections),uploads)
    result=importer.diagnose() if args.operation=='diagnose' else importer.scan(args.limit)
    print(json.dumps({'operation':args.operation,**result},sort_keys=True))
    if result['errors']:raise SystemExit(1)


if __name__=='__main__':main()
