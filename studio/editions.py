"""Independent editions, local voice assets and local-only visual fingerprints."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import time
import uuid

SCHEMA='''
CREATE TABLE IF NOT EXISTS edition_groups(id TEXT PRIMARY KEY,title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS editions(work_id TEXT PRIMARY KEY REFERENCES works(id),
 group_id TEXT REFERENCES edition_groups(id),kind TEXT NOT NULL DEFAULT 'comic',
 language TEXT NOT NULL DEFAULT '',label TEXT NOT NULL DEFAULT '',translator TEXT NOT NULL DEFAULT '',
 comic_work_id TEXT REFERENCES works(id),cover_asset_id TEXT REFERENCES voice_assets(id));
CREATE INDEX IF NOT EXISTS editions_group ON editions(group_id);
CREATE TABLE IF NOT EXISTS voice_assets(id TEXT PRIMARY KEY,work_id TEXT NOT NULL REFERENCES works(id),
 sha256 TEXT NOT NULL,extension TEXT NOT NULL,kind TEXT NOT NULL,mime TEXT NOT NULL,
 name TEXT NOT NULL,bytes INTEGER NOT NULL,created REAL NOT NULL,UNIQUE(work_id,sha256,kind));
CREATE INDEX IF NOT EXISTS voice_assets_work ON voice_assets(work_id);
CREATE TABLE IF NOT EXISTS voice_progress(asset_id TEXT PRIMARY KEY REFERENCES voice_assets(id),
 position REAL NOT NULL,updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS voice_cues(asset_id TEXT NOT NULL REFERENCES voice_assets(id),
 page INTEGER NOT NULL,second REAL NOT NULL,PRIMARY KEY(asset_id,page),UNIQUE(asset_id,second));
CREATE TABLE IF NOT EXISTS visual_signatures(work_id TEXT PRIMARY KEY REFERENCES works(id),
 fingerprint TEXT NOT NULL,updated REAL NOT NULL);
'''


def number(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=7*86400:
        raise ValueError('재생 시간은 0~7일 범위의 초 단위 숫자여야 합니다.')
    return float(value)


class EditionCatalog:
    def edition_details(self,work):
        with self.db() as db:
            row=db.execute('SELECT * FROM editions WHERE work_id=?',(work['id'],)).fetchone()
            result=dict(row) if row else {'work_id':work['id'],'group_id':None,'kind':'comic','language':'','label':'','translator':'','comic_work_id':None,'cover_asset_id':None}
            comic=result['comic_work_id'] or (work['id'] if work['lrr_id'] else None)
            linked=db.execute('SELECT w.lrr_id,w.pages,n.number AS local_number FROM works w JOIN work_numbers n ON n.work_id=w.id WHERE w.id=? AND w.merged_into IS NULL',(comic,)).fetchone()
            result.update(comic_lrr_id=linked['lrr_id'] if linked else None,comic_pages=linked['pages'] if linked else 0,comic_local_number=linked['local_number'] if linked else None)
            siblings=db.execute('''SELECT w.id,w.title,w.artist,n.number AS local_number,e.kind,e.language,e.label,e.translator
                FROM editions e JOIN works w ON w.id=e.work_id JOIN work_numbers n ON n.work_id=w.id
                WHERE e.group_id=? AND w.merged_into IS NULL ORDER BY n.number''',(result['group_id'],)).fetchall() if result['group_id'] else []
            result['siblings']=[dict(r) for r in siblings]
            result['assets']=[dict(r) for r in db.execute('''SELECT a.id,a.kind,a.mime,a.name,a.bytes,COALESCE(p.position,0) AS position
                FROM voice_assets a LEFT JOIN voice_progress p ON p.asset_id=a.id WHERE a.work_id=? ORDER BY a.created,a.id''',(work['id'],))]
            for asset in result['assets']:
                asset['cues']=[dict(r) for r in db.execute('SELECT page,second FROM voice_cues WHERE asset_id=? ORDER BY second',(asset['id'],))]
        return result

    def configure_edition(self,work_id,data):
        work=self.get_work(work_id);work_id=work['id']
        allowed={'kind','language','label','translator','comic_reference'}
        if set(data)-allowed:raise ValueError('판본 설정 필드를 확인하세요.')
        current=work['edition'];values={key:data.get(key,current[key]) for key in ('kind','language','label','translator')}
        if values['kind'] not in ('comic','voice_video','voice_pages'):raise ValueError('만화 또는 보이스코믹 판본을 선택하세요.')
        for key in ('language','label','translator'):
            if not isinstance(values[key],str) or len(values[key])>200:raise ValueError('판본 설명은 200자 이내로 입력하세요.')
            values[key]=values[key].strip()
        comic=current['comic_work_id']
        if 'comic_reference' in data:
            reference=data['comic_reference']
            if not isinstance(reference,str):raise ValueError('만화 판본 번호를 입력하세요.')
            linked=self.resolve_short_id(reference) if reference.strip() else None
            if linked and not linked['lrr_id']:raise ValueError('만화 파일이 연결된 판본을 선택하세요.')
            comic=linked['id'] if linked else None
        if values['kind']!='voice_pages':comic=None
        with self.db() as db:
            if comic:db.execute('INSERT OR IGNORE INTO editions(work_id) VALUES(?)',(comic,))
            db.execute('''INSERT INTO editions(work_id,kind,language,label,translator,comic_work_id) VALUES(?,?,?,?,?,?)
                ON CONFLICT(work_id) DO UPDATE SET kind=excluded.kind,language=excluded.language,label=excluded.label,
                translator=excluded.translator,comic_work_id=excluded.comic_work_id''',
                (work_id,*values.values(),comic))
        return self.get_work(work_id)

    def group_edition(self,work_id,reference):
        current=self.get_work(work_id);other=self.resolve_short_id(reference)
        if current['id']==other['id']:raise ValueError('다른 판본의 번호를 입력하세요.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            groups=[]
            for work in (current,other):
                db.execute('INSERT OR IGNORE INTO editions(work_id) VALUES(?)',(work['id'],))
                groups.append(db.execute('SELECT group_id FROM editions WHERE work_id=?',(work['id'],)).fetchone()[0])
            if groups[0] and groups[1] and groups[0]!=groups[1]:raise ValueError('서로 다른 기존 작품 묶음입니다. 판본을 먼저 분리하세요.')
            group=groups[0] or groups[1] or uuid.uuid4().hex
            db.execute('INSERT OR IGNORE INTO edition_groups VALUES(?,?)',(group,current['title']))
            db.execute('UPDATE editions SET group_id=? WHERE work_id IN (?,?)',(group,current['id'],other['id']))
        return self.get_work(current['id'])

    def ungroup_edition(self,work_id):
        work_id=self.get_work(work_id)['id']
        with self.db() as db:db.execute('UPDATE editions SET group_id=NULL WHERE work_id=?',(work_id,))
        return self.get_work(work_id)

    def save_voice_progress(self,work_id,asset_id,position):
        work_id=self.get_work(work_id)['id'];position=number(position)
        with self.db() as db:
            if not db.execute("SELECT 1 FROM voice_assets WHERE id=? AND work_id=? AND kind IN ('audio','video')",(asset_id,work_id)).fetchone():raise KeyError('이 판본의 재생 파일을 찾을 수 없습니다.')
            now=time.time()
            db.execute('INSERT INTO voice_progress VALUES(?,?,?) ON CONFLICT(asset_id) DO UPDATE SET position=excluded.position,updated=excluded.updated',(asset_id,position,now))
            db.execute('UPDATE works SET last_read=? WHERE id=?',(now,work_id))
        return {'position':position}

    def save_voice_cues(self,work_id,asset_id,cues):
        work=self.get_work(work_id);pages=work['edition']['comic_pages']
        if work['edition']['kind']!='voice_pages' or pages<1:raise ValueError('만화 파일과 연결한 음성형 보이스코믹에서 사용하세요.')
        if not isinstance(cues,list) or len(cues)>20000:raise ValueError('페이지 연결 목록을 확인하세요.')
        checked=[]
        for cue in cues:
            if not isinstance(cue,dict) or set(cue)!={'page','second'} or type(cue['page']) is not int or not 1<=cue['page']<=pages:raise ValueError('연결할 페이지 범위를 확인하세요.')
            checked.append((cue['page'],number(cue['second'])))
        ordered=sorted(checked)
        if len({p for p,t in ordered})!=len(ordered) or any(a[1]>=b[1] for a,b in zip(ordered,ordered[1:])):raise ValueError('페이지와 시작 시간은 중복 없이 증가해야 합니다.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute("SELECT 1 FROM voice_assets WHERE id=? AND work_id=? AND kind='audio'",(asset_id,work['id'])).fetchone():raise KeyError('이 판본의 음성 파일을 찾을 수 없습니다.')
            db.execute('DELETE FROM voice_cues WHERE asset_id=?',(asset_id,))
            db.executemany('INSERT INTO voice_cues VALUES(?,?,?)',[(asset_id,p,t) for p,t in ordered])
        return {'saved':len(checked)}

    def index_visual(self,items):
        if not isinstance(items,list) or not 1<=len(items)<=120:raise ValueError('한 번에 표지 1~120개를 색인하세요.')
        checked=[]
        for item in items:
            if not isinstance(item,dict) or set(item)!={'work_id','fingerprint'} or not re.fullmatch('[0-9a-f]{16}',str(item['fingerprint'])):raise ValueError('표지 지문 형식을 확인하세요.')
            work=self.get_work(item['work_id']);checked.append((work['id'],item['fingerprint'],time.time()))
        with self.db() as db:db.executemany('INSERT INTO visual_signatures VALUES(?,?,?) ON CONFLICT(work_id) DO UPDATE SET fingerprint=excluded.fingerprint,updated=excluded.updated',checked)
        return {'indexed':len(checked)}

    def visual_search(self,fingerprint):
        if not isinstance(fingerprint,str) or not re.fullmatch('[0-9a-f]{16}',fingerprint):raise ValueError('검색할 이미지 지문을 확인하세요.')
        query=int(fingerprint,16)
        with self.db() as db:
            rows=db.execute('SELECT v.* FROM visual_signatures v JOIN works w ON w.id=v.work_id WHERE w.merged_into IS NULL').fetchall()
        best=sorted(((query^int(r['fingerprint'],16)).bit_count(),r['work_id']) for r in rows)[:40]
        return {'indexed':len(rows),'items':[{'distance':distance,'work':self.get_work(work_id)} for distance,work_id in best if distance<=20]}


FORMATS={'.mp4':('video','video/mp4'),'.webm':('video','video/webm'),'.mp3':('audio','audio/mpeg'),
 '.m4a':('audio','audio/mp4'),'.wav':('audio','audio/wav'),'.flac':('audio','audio/flac'),'.ogg':('audio','audio/ogg'),
 '.png':('cover','image/png'),'.jpg':('cover','image/jpeg'),'.jpeg':('cover','image/jpeg'),'.webp':('cover','image/webp')}


class VoiceAssets:
    def __init__(self,store,root,max_bytes):
        self.store=store;self.root=Path(root)/'.voice-assets' if root else None;self.max_bytes=max_bytes
        self.slot=threading.BoundedSemaphore(1)

    @staticmethod
    def validate(path,name):
        extension=Path(name).suffix.lower()
        if extension not in FORMATS:raise ValueError('MP4·WebM, 음성 또는 JPG·PNG·WebP 표지를 선택하세요.')
        with path.open('rb') as f:header=f.read(32)
        good={'.mp4':header[4:8]==b'ftyp','.m4a':header[4:8]==b'ftyp','.webm':header.startswith(b'\x1aE\xdf\xa3'),
         '.mp3':header.startswith(b'ID3') or (len(header)>1 and header[0]==255 and header[1]&224==224),
         '.wav':header.startswith(b'RIFF') and header[8:12]==b'WAVE','.flac':header.startswith(b'fLaC'),'.ogg':header.startswith(b'OggS'),
         '.png':header.startswith(b'\x89PNG\r\n\x1a\n'),'.jpg':header.startswith(b'\xff\xd8\xff'),'.jpeg':header.startswith(b'\xff\xd8\xff'),
         '.webp':header.startswith(b'RIFF') and header[8:12]==b'WEBP'}[extension]
        if not good:raise ValueError('파일 확장자와 미디어 헤더가 일치하지 않습니다.')
        return extension,*FORMATS[extension]

    def receive(self,work_id,stream,length,name):
        work=self.store.get_work(work_id);work_id=work['id']
        if self.root is None:raise ValueError('전용 업로드 저장소가 연결되지 않았습니다.')
        if not isinstance(name,str) or len(name.encode())>255 or not name.strip() or any(c in name for c in '/\\\r\n\0'):raise ValueError('파일 이름을 확인하세요.')
        if Path(name).suffix.lower() not in FORMATS:raise ValueError('지원하는 미디어 파일을 선택하세요.')
        if any(ord(c)<32 for c in name):raise ValueError('파일 이름을 확인하세요.')
        if type(length) is not int or not 0<length<=self.max_bytes:raise ValueError('미디어 파일 크기 제한을 초과했습니다.')
        if FORMATS[Path(name).suffix.lower()][0]=='cover' and length>10*1024**2:raise ValueError('표지는 10MiB 이내로 선택하세요.')
        if not self.slot.acquire(blocking=False):raise ValueError('다른 미디어 업로드가 진행 중입니다.')
        temporary=None
        try:
            self.root.mkdir(mode=0o700,exist_ok=True)
            if self.root.is_symlink():raise ValueError('미디어 저장소 경로를 확인하세요.')
            fd,path=tempfile.mkstemp(prefix='voice-',suffix='.part',dir=self.root);temporary=Path(path)
            digest=hashlib.sha256();remaining=length
            with os.fdopen(fd,'wb') as output:
                while remaining:
                    block=stream.read(min(remaining,256*1024))
                    if not block:raise ValueError('업로드가 중단됐습니다.')
                    output.write(block);digest.update(block);remaining-=len(block)
                output.flush();os.fsync(output.fileno())
            extension,kind,mime=self.validate(temporary,name);sha=digest.hexdigest();target=self.root/(sha+extension)
            try:os.link(temporary,target)
            except FileExistsError:
                fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                with os.fdopen(fd,'rb') as old:
                    if not stat.S_ISREG(os.fstat(old.fileno()).st_mode) or hashlib.file_digest(old,'sha256').hexdigest()!=sha:raise ValueError('기존 미디어 파일 충돌입니다.')
            directory=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(directory)
            finally:os.close(directory)
            with self.store.db() as db:
                # Audio is an attachment for a comic edition, not a separate audio catalog.
                db.execute('INSERT OR IGNORE INTO voice_assets VALUES(?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,work_id,sha,extension,kind,mime,name,length,time.time()))
                row=db.execute('SELECT id FROM voice_assets WHERE work_id=? AND sha256=? AND kind=?',(work_id,sha,kind)).fetchone()
                if kind=='cover':
                    db.execute('INSERT OR IGNORE INTO editions(work_id) VALUES(?)',(work_id,))
                    db.execute('UPDATE editions SET cover_asset_id=? WHERE work_id=?',(row[0],work_id))
            return {'id':row[0],'kind':kind,'bytes':length}
        finally:
            if temporary:temporary.unlink(missing_ok=True)
            self.slot.release()

    def open(self,asset_id):
        with self.store.db() as db:row=db.execute('SELECT * FROM voice_assets WHERE id=?',(asset_id,)).fetchone()
        if not row or self.root is None:raise KeyError('미디어 파일을 찾을 수 없습니다.')
        if not re.fullmatch('[0-9a-f]{64}',row['sha256']) or row['extension'] not in FORMATS:raise ValueError('저장된 미디어 정보를 확인하세요.')
        directory=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:fd=os.open(row['sha256']+row['extension'],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        finally:os.close(directory)
        stream=os.fdopen(fd,'rb');info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size!=row['bytes']:stream.close();raise ValueError('미디어 파일 상태를 확인하세요.')
        return dict(row),stream
