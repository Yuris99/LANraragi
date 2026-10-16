"""NAS-local image-folder to CBZ import. Default plan never opens a database.

Sources are read-only, traversed with directory descriptors and O_NOFOLLOW.
Only generated CBZs/receipts are written to Studio's dedicated volumes.
"""
import argparse
import contextlib
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


class FolderImporter:
    def __init__(self,root,collections,uploads=None,stable_seconds=30,max_pages=2000,max_entries=10000):
        self.root=Path(root).absolute();self.collections=[];self.uploads=uploads
        self.stable_seconds=stable_seconds;self.max_pages=max_pages;self.max_entries=max_entries
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
            source=self.root.resolve();destination=uploads.root
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
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for part in relative.parts:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=child
            yield fd
        finally:os.close(fd)

    def entries(self,fd):
        result=[]
        with os.scandir(fd) as entries:
            for entry in entries:
                if len(result)>=self.max_entries:raise ValueError('한 폴더의 항목 수 한도를 초과했습니다.')
                result.append(entry.name)
        return sorted(result,key=natural_key)

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
        result=dict(directories=0,ready=0,deferred=0,imported=0,unchanged=0,errors=0,pages=0)
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
                    if not ready:result['deferred']+=1;continue
                    result['ready']+=1
                    if self.uploads:
                        if self.remembered(relative,signature):result['unchanged']+=1;continue
                        self.package(relative,fd,snapshot);result['imported']+=1
                        if result['imported']>=limit:break
            except (OSError,ValueError,KeyError):result['errors']+=1
        self.save_pending(pending)
        result['bounded']=bool(pending)
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation',choices=['plan','import'],default='plan')
    parser.add_argument('--root',default=os.environ.get('STUDIO_FOLDER_ROOT','/nas-library'))
    parser.add_argument('--collections',default=os.environ.get('STUDIO_FOLDER_COLLECTIONS','["manga","images"]'))
    parser.add_argument('--limit',type=int,default=1)
    args=parser.parse_args();uploads=None
    if args.operation=='import':
        database=os.environ.get('STUDIO_DATABASE');destination=os.environ.get('STUDIO_UPLOAD_DIR')
        if not database or not destination:parser.error('Set verified dedicated database and upload paths')
        uploads=Uploads(Store(database),destination,int(os.environ.get('STUDIO_MAX_UPLOAD_BYTES',512*1024**2)))
    result=FolderImporter(args.root,json.loads(args.collections),uploads).scan(args.limit)
    print(json.dumps({'operation':args.operation,**result},sort_keys=True))
    if result['errors']:raise SystemExit(1)


if __name__=='__main__':main()
