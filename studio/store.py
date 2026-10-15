"""Small SQLite catalog kept separate from upstream Redis and original files."""
import contextlib
import json
import re
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from sources import parse_source, tags_list, comments_list


def uid():
    return uuid.uuid4().hex


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS works (
                id TEXT PRIMARY KEY, lrr_id TEXT UNIQUE, title TEXT NOT NULL,
                artist TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
                pages INTEGER NOT NULL DEFAULT 0, bytes INTEGER NOT NULL DEFAULT 0,
                added REAL NOT NULL, last_read REAL, progress INTEGER NOT NULL DEFAULT 0,
                rating INTEGER NOT NULL DEFAULT 0, favorite INTEGER NOT NULL DEFAULT 0,
                title_locked INTEGER NOT NULL DEFAULT 0);
              CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES works(id),
                provider TEXT NOT NULL, external_id TEXT NOT NULL, url TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]', comments TEXT NOT NULL DEFAULT '[]',
                fetched REAL, status TEXT NOT NULL DEFAULT 'unverified',
                UNIQUE(provider,external_id));
              CREATE INDEX IF NOT EXISTS sources_work ON sources(work_id);
              CREATE INDEX IF NOT EXISTS works_added ON works(added);
              CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, work_id TEXT, url TEXT NOT NULL, target TEXT NOT NULL,
                engine TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL,
                updated REAL NOT NULL, lease TEXT, lease_until REAL, remote_id TEXT,
                message TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '{}');
              CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(target,state,created);
              CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            ''')

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def work_row(row):
        result = dict(row)
        result['tags'] = json.loads(result['tags'])
        return result

    @staticmethod
    def source_row(row):
        result = dict(row)
        for key in ('tags', 'comments'):
            result[key] = json.loads(result[key])
        return result

    def get_work(self, work_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM works WHERE id=?', (work_id,)).fetchone()
            if not row:
                raise KeyError('작품을 찾을 수 없습니다.')
            result = self.work_row(row)
            result['sources'] = [self.source_row(s) for s in db.execute(
                'SELECT * FROM sources WHERE work_id=? ORDER BY provider,external_id', (work_id,))]
            result['all_tags'] = list(dict.fromkeys(result['tags'] + [
                t for s in result['sources'] for t in s['tags']]))
            return result

    def list_works(self, query='', sort='added', descending=True, page=1, limit=48,
                   provider='', favorite=False, unread=False):
        order = {'added': 'added', 'title': 'title COLLATE NOCASE', 'artist': 'artist COLLATE NOCASE',
                 'pages': 'pages', 'bytes': 'bytes', 'rating': 'rating',
                 'last_read': 'COALESCE(last_read,0)', 'random': 'RANDOM()'}
        if sort not in order or not 1 <= limit <= 120 or not 1 <= page <= 100000:
            raise ValueError('정렬 또는 페이지 범위가 올바르지 않습니다.')
        where, args = [], []
        if query:
            # Parameters preserve SQL safety; LIKE wildcards are treated literally.
            term = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            where.append("(title LIKE ? ESCAPE '\\' OR artist LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM sources s WHERE s.work_id=works.id AND (s.external_id LIKE ? ESCAPE '\\' OR s.tags LIKE ? ESCAPE '\\'))) ")
            args += [term] * 5
        if provider:
            where.append('EXISTS (SELECT 1 FROM sources s WHERE s.work_id=works.id AND s.provider=?)')
            args.append(provider)
        if favorite:
            where.append('favorite=1')
        if unread:
            where.append('last_read IS NULL')
        condition = ' WHERE ' + ' AND '.join(where) if where else ''
        with self.db() as db:
            total = db.execute('SELECT count(*) FROM works'+condition, args).fetchone()[0]
            rows = db.execute('SELECT id FROM works'+condition+' ORDER BY '+order[sort]+
                              (' DESC' if descending else ' ASC')+',id LIMIT ? OFFSET ?',
                              [*args, limit, (page-1)*limit]).fetchall()
        return dict(items=[self.get_work(row['id']) for row in rows], total=total,
                    page=page, limit=limit)

    def create_work(self, title, artist='', lrr_id=None, pages=0, size=0, tags=None):
        title = str(title).strip()
        if not title or len(title) > 1000:
            raise ValueError('제목은 1~1000자여야 합니다.')
        if lrr_id is not None and not re.fullmatch('[0-9a-f]{40}', lrr_id):
            raise ValueError('LANraragi ID 형식이 올바르지 않습니다.')
        work_id = uid()
        with self.db() as db:
            db.execute('INSERT INTO works(id,lrr_id,title,artist,pages,bytes,tags,added) VALUES(?,?,?,?,?,?,?,?)',
                       (work_id,lrr_id,title,str(artist)[:500],max(0,int(pages)),max(0,int(size)),
                        json.dumps(tags_list(tags or []),ensure_ascii=False),time.time()))
        return self.get_work(work_id)

    def update_work(self, work_id, data):
        self.get_work(work_id)
        allowed = {'title','artist','rating','favorite','title_locked','tags'}
        if set(data)-allowed:
            raise ValueError('수정할 수 없는 필드입니다.')
        values = {}
        for k,v in data.items():
            if k in ('title','artist'):
                if not isinstance(v,str) or len(v)>1000 or (k=='title' and not v.strip()):
                    raise ValueError('제목·작가 형식이 올바르지 않습니다.')
                values[k] = v.strip()
            elif k=='rating':
                if type(v) is not int or not 0 <= v <= 5:
                    raise ValueError('별점은 0~5입니다.')
                values[k] = v
            elif k=='tags':
                values[k] = json.dumps(tags_list(v),ensure_ascii=False)
            else:
                values[k] = int(bool(v))
        if values:
            with self.db() as db:
                db.execute('UPDATE works SET '+','.join(k+'=?' for k in values)+' WHERE id=?',
                           [*values.values(),work_id])
        return self.get_work(work_id)

    def upsert_source(self, work_id, data):
        self.get_work(work_id)
        identity = parse_source(data.get('url'))
        tags = tags_list(data.get('tags',[]))
        comments = comments_list(data.get('comments',[]))
        if data.get('status','manual') not in ('manual','fetched','unverified'):
            raise ValueError('출처 상태가 올바르지 않습니다.')
        with self.db() as db:
            existing = db.execute('SELECT * FROM sources WHERE provider=? AND external_id=?',
                                  (identity['provider'],identity['external_id'])).fetchone()
            if existing and existing['work_id'] != work_id:
                raise ValueError('이미 다른 작품에 연결된 출처입니다. 판본을 확인하세요.')
            source_id = existing['id'] if existing else uid()
            # Omitted fields preserve previously fetched comments and tags.
            if existing:
                if 'tags' not in data: tags = json.loads(existing['tags'])
                if 'comments' not in data: comments = json.loads(existing['comments'])
            fetched = time.time() if data.get('status')=='fetched' else (existing['fetched'] if existing else None)
            db.execute('''INSERT INTO sources(id,work_id,provider,external_id,url,tags,comments,fetched,status)
                       VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(provider,external_id) DO UPDATE SET
                       url=excluded.url,tags=excluded.tags,comments=excluded.comments,
                       fetched=excluded.fetched,status=excluded.status''',
                       (source_id,work_id,identity['provider'],identity['external_id'],identity['url'],
                        json.dumps(tags,ensure_ascii=False),json.dumps(comments,ensure_ascii=False),
                        fetched,data.get('status','manual')))
        return self.get_work(work_id)

    def sync_lrr(self, archives):
        count = 0
        for item in archives:
            lrr_id = item.get('arcid','')
            if not re.fullmatch('[0-9a-f]{40}',lrr_id):
                continue
            tags = tags_list(item.get('tags',''))
            artist = ', '.join(x.split(':',1)[1] for x in tags if x.startswith('artist:'))
            with self.db() as db:
                row = db.execute('SELECT id,title_locked FROM works WHERE lrr_id=?',(lrr_id,)).fetchone()
            if row:
                with self.db() as db:
                    db.execute('UPDATE works SET pages=?,bytes=? WHERE id=?',
                               (int(item.get('pagecount') or 0),int(item.get('arcsize') or 0),row['id']))
                    if not row['title_locked']:
                        db.execute('UPDATE works SET title=?,artist=?,tags=? WHERE id=?',
                                   (item.get('title') or lrr_id,artist,json.dumps(tags,ensure_ascii=False),row['id']))
                work = self.get_work(row['id'])
            else:
                work = self.create_work(item.get('title') or lrr_id,artist,lrr_id,
                                        item.get('pagecount') or 0,item.get('arcsize') or 0,tags)
            for tag in tags:
                if tag.startswith('source:'):
                    value = tag.split(':',1)[1].strip()
                    try:self.upsert_source(work['id'],{'url':value if value.startswith('https://') else 'https://'+value})
                    except ValueError:pass  # A source collision is never used to merge works.
            count += 1
        return count

    def progress(self, work_id, page):
        work = self.get_work(work_id)
        if type(page) is not int or page<1 or page>work['pages']:
            raise ValueError('페이지 범위가 올바르지 않습니다.')
        with self.db() as db:
            db.execute('UPDATE works SET progress=?,last_read=? WHERE id=?',(page,time.time(),work_id))

    def queue(self, url, target, engine, work_id=None):
        source = parse_source(url)
        if target not in ('nas','pc') or engine not in ('lanraragi','command'):
            raise ValueError('저장 대상 또는 엔진이 올바르지 않습니다.')
        if engine=='lanraragi' and target!='nas':
            raise ValueError('LANraragi 엔진은 서버 저장 전용입니다.')
        if work_id:self.get_work(work_id)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute("SELECT * FROM jobs WHERE url=? AND target=? AND engine=? AND state IN ('queued','running')",
                                (source['url'],target,engine)).fetchone()
            if existing:return dict(existing)
            job_id=uid();now=time.time()
            db.execute('INSERT INTO jobs(id,work_id,url,target,engine,state,created,updated) VALUES(?,?,?,?,?,?,?,?)',
                       (job_id,work_id,source['url'],target,engine,'queued',now,now))
        return self.job(job_id)

    def job(self, job_id):
        with self.db() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row:raise KeyError('작업을 찾을 수 없습니다.')
            return dict(row)

    def jobs(self):
        with self.db() as db:
            return [dict(x) for x in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 200')]

    def claim(self, target, engine):
        if target not in ('nas','pc') or engine not in ('lanraragi','command'):
            raise ValueError('잘못된 작업 대상입니다.')
        now=time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            # Expired command tasks need explicit retry: a crashed engine might still be writing.
            db.execute("UPDATE jobs SET state='blocked',message='Worker lease expired; inspect output before retry',updated=? WHERE state='running' AND lease_until<?",(now,now))
            row=db.execute("SELECT * FROM jobs WHERE target=? AND engine=? AND state='queued' ORDER BY created LIMIT 1",(target,engine)).fetchone()
            if not row:return None
            lease=secrets.token_urlsafe(32)
            db.execute("UPDATE jobs SET state='running',lease=?,lease_until=?,updated=? WHERE id=?",(lease,now+120,now,row['id']))
            result=dict(row);result.update(state='running',lease=lease)
            return result

    def report(self, job_id, lease, state, message='', result=None):
        if state not in ('running','complete','failed','blocked'):
            raise ValueError('잘못된 작업 상태입니다.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row or row['state']!='running' or not secrets.compare_digest(row['lease'] or '',lease or ''):
                raise ValueError('만료되었거나 잘못된 작업 임대입니다.')
            if row['lease_until'] < time.time():
                raise ValueError('작업 임대가 만료됐습니다.')
            db.execute('UPDATE jobs SET state=?,message=?,result=?,updated=?,lease_until=? WHERE id=?',
                       (state,str(message)[:2000],json.dumps(result or {},ensure_ascii=False),time.time(),time.time()+120,job_id))

    def retry(self, job_id):
        with self.db() as db:
            row=db.execute('SELECT state FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row or row['state'] not in ('failed','blocked'):
                raise ValueError('실패하거나 중단된 작업만 다시 시도할 수 있습니다.')
            db.execute("UPDATE jobs SET state='queued',lease=NULL,remote_id=NULL,message='',updated=? WHERE id=?",(time.time(),job_id))

    def export(self):
        with self.db() as db:
            ids=[x[0] for x in db.execute('SELECT id FROM works ORDER BY added')]
        return {'schema_version':1,'exported_at':time.time(),'works':[self.get_work(i) for i in ids]}
