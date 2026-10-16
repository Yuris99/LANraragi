"""Bounded, streamed uploads into a dedicated shared volume; no extraction."""
import hashlib
import os
from pathlib import Path,PurePosixPath
import stat
import struct
import tempfile
import threading
import time
import zipfile

IMAGE_SUFFIXES={'.jpg','.jpeg','.png','.webp','.gif','.avif','.jxl'}


class UploadError(ValueError):
    def __init__(self,message,status=400):super().__init__(message);self.status=status


class Uploads:
    def __init__(self,store,root=None,max_bytes=512*1024*1024):
        self.store=store;self.root=Path(root).resolve() if root else None
        self.max_bytes=int(max_bytes)
        if not 1<=self.max_bytes<=2*1024**3:raise ValueError('Upload limit must be 1 byte to 2 GiB')
        self.slot=threading.BoundedSemaphore(1)

    @staticmethod
    def filename(name):
        if not isinstance(name,str) or not name.strip() or len(name.encode('utf-8'))>255 or any(c in name for c in '/\\\r\n\0'):
            raise UploadError('파일 이름이 올바르지 않습니다.')
        name=name.strip()
        if Path(name).suffix.lower() not in ('.cbz','.zip','.pdf'):
            raise UploadError('CBZ·ZIP·PDF 파일만 업로드할 수 있습니다.',415)
        return name

    @staticmethod
    def validate(path,name):
        with path.open('rb') as stream:prefix=stream.read(8)
        if Path(name).suffix.lower()=='.pdf':
            if not prefix.startswith(b'%PDF-'):raise UploadError('PDF 파일 형식이 올바르지 않습니다.')
            with path.open('rb') as stream:
                stream.seek(max(0,path.stat().st_size-2048))
                if b'%%EOF' not in stream.read():raise UploadError('완료되지 않은 PDF 파일입니다.')
            return '.pdf'
        if not prefix.startswith(b'PK\x03\x04'):raise UploadError('CBZ·ZIP 파일 형식이 올바르지 않습니다.')
        # Bound the central directory before ZipFile materializes all entry metadata.
        with path.open('rb') as stream:
            stream.seek(max(0,path.stat().st_size-65557));tail=stream.read()
        offset=tail.rfind(b'PK\x05\x06')
        if offset<0 or len(tail)-offset<22:raise UploadError('완료되지 않은 ZIP 파일입니다.')
        record=struct.unpack_from('<4s4H2IH',tail,offset)
        if record[1] or record[2] or record[3]!=record[4] or record[4]>10000 or record[5]>8*1024**2:
            raise UploadError('분할 압축 또는 중앙 디렉터리 한도를 초과한 ZIP은 지원하지 않습니다.')
        try:
            with zipfile.ZipFile(path) as archive:
                entries=archive.infolist()
                if not entries or len(entries)>10000:raise UploadError('압축 파일 항목 수 제한을 초과했습니다.')
                expanded=0;pages=0
                for item in entries:
                    file=PurePosixPath(item.filename)
                    if file.is_absolute() or '..' in file.parts or '\\' in item.filename or ':' in item.filename or '\0' in item.filename:
                        raise UploadError('압축 파일에 안전하지 않은 경로가 있습니다.')
                    if stat.S_ISLNK(item.external_attr>>16) or item.flag_bits&1:
                        raise UploadError('심볼릭 링크·암호화 압축 파일은 지원하지 않습니다.')
                    expanded+=item.file_size
                    if expanded>1024**3 or item.file_size>64*1024**2 or item.file_size>max(1,item.compress_size)*2000:
                        raise UploadError('압축 해제 크기 제한을 초과했습니다.')
                    if not item.is_dir() and file.suffix.lower() in IMAGE_SUFFIXES:pages+=1
                if not pages:raise UploadError('압축 파일에 지원하는 이미지가 없습니다.')
                if archive.testzip() is not None:raise UploadError('손상된 압축 파일입니다.')
        except (zipfile.BadZipFile,NotImplementedError,RuntimeError,EOFError) as error:
            raise UploadError('압축 파일을 검증하지 못했습니다.') from error
        return '.cbz'

    def receive(self,stream,length,name):
        name=self.filename(name)
        if type(length) is not int or not 1<=length<=self.max_bytes:
            raise UploadError('파일 크기가 비어 있거나 업로드 한도를 초과했습니다.',413)
        if self.root is None:raise UploadError('업로드 전용 저장소가 설정되지 않았습니다.',503)
        if not self.slot.acquire(blocking=False):raise UploadError('다른 파일을 업로드 중입니다. 잠시 후 다시 시도하세요.',429)
        temporary=None
        try:
            self.root.mkdir(parents=True,exist_ok=True)
            staging=self.root/'.staging';staging.mkdir(exist_ok=True)
            if staging.is_symlink():raise UploadError('업로드 임시 저장소 설정을 확인하세요.',503)
            digest=hashlib.sha256();remaining=length
            fd,name_on_disk=tempfile.mkstemp(prefix='upload-',suffix='.part',dir=staging)
            temporary=Path(name_on_disk)
            with os.fdopen(fd,'wb') as output:
                while remaining:
                    block=stream.read(min(256*1024,remaining))
                    if not block:raise UploadError('전송이 중단됐습니다. 완료된 파일은 저장하지 않았습니다.')
                    output.write(block);digest.update(block);remaining-=len(block)
                output.flush();os.fsync(output.fileno())
            extension=self.validate(temporary,name);sha=digest.hexdigest()
            with self.store.db() as db:
                previous=db.execute('SELECT * FROM uploads WHERE sha256=?',(sha,)).fetchone()
            if previous:
                try:
                    _,existing=self.open(sha)
                    existing.close()
                    return {**dict(previous),'duplicate':True}
                except FileNotFoundError:pass  # Restore a missing data file, never replace an existing one.
            destination=self.root/(sha+extension)
            try:os.link(temporary,destination)
            except FileExistsError:
                # Recover a published file after a crash before SQLite registration.
                if destination.is_symlink():raise UploadError('업로드 저장소의 파일 충돌을 확인하세요.',409)
                with destination.open('rb') as existing:
                    if hashlib.file_digest(existing,'sha256').hexdigest()!=sha:
                        raise UploadError('업로드 저장소의 파일 충돌을 확인하세요.',409)
            if os.name=='posix':
                directory_fd=os.open(self.root,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
                try:os.fsync(directory_fd)
                finally:os.close(directory_fd)
            with self.store.db() as db:
                db.execute('INSERT OR IGNORE INTO uploads(sha256,original_name,stored_name,bytes,created) VALUES(?,?,?,?,?)',
                           (sha,name,destination.name,length,time.time()))
            return {**self.get(sha),'duplicate':False}
        finally:
            if temporary:temporary.unlink(missing_ok=True)
            self.slot.release()

    def get(self,sha):
        with self.store.db() as db:
            row=db.execute('SELECT * FROM uploads WHERE sha256=?',(sha,)).fetchone()
        if not row:raise KeyError('업로드 파일을 찾을 수 없습니다.')
        return dict(row)

    def list(self):
        with self.store.db() as db:
            return [dict(row) for row in db.execute('SELECT u.*,w.id AS work_id FROM uploads u LEFT JOIN works w ON w.lrr_id=u.lrr_id ORDER BY u.created DESC LIMIT 100')]

    def open(self,sha):
        row=self.get(sha)
        if self.root is None:raise KeyError('업로드 저장소가 연결되지 않았습니다.')
        if not re_safe_stored(row['stored_name'],sha):raise KeyError('업로드 파일 경로가 올바르지 않습니다.')
        path=self.root/row['stored_name']
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        stream=os.fdopen(fd,'rb');info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size!=row['bytes']:
            stream.close();raise KeyError('저장된 파일 상태를 확인하세요.')
        return row,stream


def re_safe_stored(name,sha):
    return name in (sha+'.cbz',sha+'.pdf')
