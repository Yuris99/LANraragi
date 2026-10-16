"""Opt-in read-only inbox copier. Never moves or deletes source files."""
import os
from pathlib import Path
import stat
import time
from uploads import UploadError

class Snapshot:
    def __init__(self,stream,info):self.stream=stream;self.info=info;self.remaining=info.st_size
    def read(self,length):
        block=self.stream.read(min(length,self.remaining));self.remaining-=len(block)
        if self.remaining==0:
            now=os.fstat(self.stream.fileno())
            if (now.st_size,now.st_mtime_ns,now.st_ctime_ns)!=(self.info.st_size,self.info.st_mtime_ns,self.info.st_ctime_ns):
                raise UploadError('가져오기 중 원본이 변경되어 다음 검사로 미룹니다.')
        return block

class Importer:
    def __init__(self,app,root,stable_seconds=30):
        self.app=app;self.root=Path(root).absolute();self.stable_seconds=stable_seconds;self.failed={};self.offset=0
        if self.root.is_symlink() or not self.root.is_dir():raise ValueError('전용 가져오기 폴더를 확인하세요.')
        if app.uploads.root and (self.root.resolve()==app.uploads.root or app.uploads.root.is_relative_to(self.root.resolve()) or self.root.resolve().is_relative_to(app.uploads.root)):
            raise ValueError('가져오기 폴더와 업로드 저장소는 분리하세요.')

    def open_file(self,path):
        # Anchor every component to directory descriptors; a renamed/symlinked
        # source directory must not escape the dedicated inbox during a scan.
        directory=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            parts=path.relative_to(self.root).parts
            for part in parts[:-1]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
                os.close(directory);directory=child
            return os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        finally:os.close(directory)

    def scan(self):
        imported=0;examined=0
        for parent,dirs,names in os.walk(self.root,followlinks=False):
            dirs[:]=sorted(d for d in dirs if not d.startswith('.') and not (Path(parent)/d).is_symlink())
            for name in sorted(names):
                examined+=1
                if examined<=self.offset:continue
                if examined>self.offset+1000:
                    self.offset=examined-1;return imported
                path=Path(parent)/name
                if path.suffix.lower() not in ('.cbz','.zip','.pdf') or name.startswith('.'):continue
                key=None;signature=None
                try:
                    fd=self.open_file(path)
                    with os.fdopen(fd,'rb') as stream:
                        info=os.fstat(stream.fileno())
                        if not stat.S_ISREG(info.st_mode) or time.time()-info.st_mtime<self.stable_seconds:continue
                        key=str(path.relative_to(self.root));signature=(info.st_size,info.st_mtime_ns)
                        if self.failed.get(key)==signature:continue
                        with self.app.store.db() as db:prior=db.execute('SELECT bytes,mtime FROM imports WHERE path=?',(key,)).fetchone()
                        if prior and tuple(prior)==signature:continue
                        result=self.app.uploads.receive(Snapshot(stream,info),info.st_size,name)
                        with self.app.store.db() as db:
                            db.execute('INSERT OR REPLACE INTO imports(path,bytes,mtime,sha256) VALUES(?,?,?,?)',(key,*signature,result['sha256']))
                        imported+=1
                except UploadError as error:
                    # Busy/store outages retry; invalid unchanged files wait for modification/restart.
                    if error.status in (400,413,415) and key is not None:self.failed[key]=signature
                    continue
                except (OSError,ValueError,KeyError):continue
        self.offset=0
        if len(self.failed)>1000:self.failed.clear()
        return imported

    def run(self):
        while not self.app.stop.is_set():
            try:
                self.scan();self.app.sync_uploads()
            except Exception:
                print('Inbox scan/index failed; saved files remain available. Check dedicated mount permissions and service health.',flush=True)
            self.app.stop.wait(10)
