"""Small SQLite catalog kept separate from upstream Redis and original files."""
import contextlib
import json
import re
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from sources import parse_source, tags_list, comments_list, filename_hints, canonical_archive_name, clean_title
from metadata import canonical_tag, visible_tag


def uid():
    return uuid.uuid4().hex


from editions import EditionCatalog, SCHEMA as EDITION_SCHEMA
from auto_sources import AutomaticSources, SCHEMA as AUTO_SOURCE_SCHEMA


class Store(EditionCatalog,AutomaticSources):
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
              CREATE TABLE IF NOT EXISTS work_numbers (
                number INTEGER PRIMARY KEY AUTOINCREMENT,
                work_id TEXT NOT NULL UNIQUE REFERENCES works(id));
              CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, work_id TEXT, url TEXT NOT NULL, target TEXT NOT NULL,
                engine TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL,
                updated REAL NOT NULL, lease TEXT, lease_until REAL, remote_id TEXT,
                message TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '{}');
              CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(target,state,created);
              CREATE TABLE IF NOT EXISTS uploads (
                sha256 TEXT PRIMARY KEY, original_name TEXT NOT NULL,stored_name TEXT NOT NULL,
                bytes INTEGER NOT NULL,created REAL NOT NULL,lrr_id TEXT,
                state TEXT NOT NULL DEFAULT 'stored');
              CREATE TABLE IF NOT EXISTS upload_tags (
                sha256 TEXT NOT NULL REFERENCES uploads(sha256),tag TEXT NOT NULL,PRIMARY KEY(sha256,tag));
              CREATE TABLE IF NOT EXISTS imports (
                path TEXT PRIMARY KEY,bytes INTEGER NOT NULL,mtime INTEGER NOT NULL,sha256 TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS user_tags (
                work_id TEXT NOT NULL REFERENCES works(id),tag TEXT NOT NULL,
                PRIMARY KEY(work_id,tag));
              CREATE INDEX IF NOT EXISTS user_tags_name ON user_tags(tag,work_id);
              CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS folder_jobs (
                id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
                source_id TEXT NOT NULL, collections TEXT NOT NULL,
                state TEXT NOT NULL, limit_count INTEGER NOT NULL DEFAULT 10,
                imported INTEGER NOT NULL DEFAULT 0, scanned INTEGER NOT NULL DEFAULT 0,
                skipped INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0,
                created REAL NOT NULL, updated REAL NOT NULL, lease TEXT, lease_until REAL,
                message TEXT NOT NULL DEFAULT '');
              CREATE UNIQUE INDEX IF NOT EXISTS folder_jobs_active ON folder_jobs((1))
                WHERE state IN ('queued','running');
            ''')

            db.executescript('''
              CREATE TABLE IF NOT EXISTS copy_retirements (
                sha256 TEXT PRIMARY KEY,copy_lrr_id TEXT NOT NULL UNIQUE,
                old_work_id TEXT NOT NULL REFERENCES works(id),work_id TEXT NOT NULL REFERENCES works(id),
                state TEXT NOT NULL,details TEXT NOT NULL,created REAL NOT NULL);
            ''')
            db.executescript(EDITION_SCHEMA)
            db.executescript(AUTO_SOURCE_SCHEMA)
            upload_columns={r['name'] for r in db.execute('PRAGMA table_info(uploads)')}
            if 'state' not in upload_columns:db.execute("ALTER TABLE uploads ADD COLUMN state TEXT NOT NULL DEFAULT 'stored'")
            work_columns={r['name'] for r in db.execute('PRAGMA table_info(works)')}
            if 'merged_into' not in work_columns:db.execute("ALTER TABLE works ADD COLUMN merged_into TEXT REFERENCES works(id)")
            if 'archive_filename' not in work_columns:db.execute("ALTER TABLE works ADD COLUMN archive_filename TEXT NOT NULL DEFAULT ''")
            if 'artist_locked' not in work_columns:db.execute("ALTER TABLE works ADD COLUMN artist_locked INTEGER NOT NULL DEFAULT 0")
            columns={r['name'] for r in db.execute('PRAGMA table_info(sources)')}
            for name,definition in [('comments_attempted','REAL'),('comments_fetched','REAL'),('comments_status',"TEXT NOT NULL DEFAULT 'import-only'"),('metadata',"TEXT NOT NULL DEFAULT '{}'")]:
                if name not in columns:db.execute('ALTER TABLE sources ADD COLUMN '+name+' '+definition)
            # Historical versions grouped ExHentai under E-Hentai. Preserve the
            # saved URL and an old E bookmark while giving each host its own ID.
            for source in db.execute("SELECT * FROM sources WHERE provider='ehentai' AND url LIKE 'https://exhentai.org/%'").fetchall():
                db.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',('legacy_ex_e:'+source['external_id'],source['work_id']))
                snapshot=json.loads(source['metadata'])
                if snapshot:snapshot['provider']='exhentai'
                db.execute("UPDATE sources SET provider='exhentai',metadata=? WHERE id=?",(json.dumps(snapshot,ensure_ascii=False),source['id']))
            now=time.time()
            db.execute("INSERT OR IGNORE INTO source_link_jobs(work_id,created,updated,next_at) SELECT DISTINCT s.work_id,?,?,? FROM sources s JOIN works w ON w.id=s.work_id WHERE w.merged_into IS NULL AND s.provider IN ('ehentai','exhentai','hitomi')",(now,now,now))
            db.execute('''INSERT INTO work_numbers(work_id)
                SELECT w.id FROM works w WHERE NOT EXISTS
                (SELECT 1 FROM work_numbers n WHERE n.work_id=w.id) ORDER BY w.added,w.id''')

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.create_function('studio_tag',1,canonical_tag,deterministic=True)
        db.create_function('visible_tag',1,visible_tag,deterministic=True)
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
        result['organization'] = filename_hints(result.get('archive_filename') or result['title'])
        hint = result['organization']
        numbers = [n['number'] for n in hint['numbers'] if n['provider'] or len(n['number']) >= 5] if not hint['ambiguous'] else []
        result['display_title'] = clean_title(result['title'], result['artist'] or hint['artist'], numbers)
        return result

    @staticmethod
    def source_row(row):
        result = dict(row)
        for key in ('tags', 'comments', 'metadata'):
            result[key] = json.loads(result[key])
        meta = result['metadata']
        if meta.get('title'):
            result['display_title'] = clean_title(meta['title'],meta.get('artists',[]),[result['external_id']])
        return result

    @staticmethod
    def short_identity(work):
        for provider,prefix in [('hitomi',''),('ehentai','E'),('exhentai','X'),('nhentai','N')]:
            values=[s['external_id'] for s in work['sources'] if s['provider']==provider
                    and re.fullmatch(r'[0-9]{1,32}',s['external_id'])]
            if values:return prefix+min(values,key=lambda value:(len(value),value))
        return 'L'+str(work['local_number'])

    def resolve_short_id(self, value):
        if not isinstance(value,str):raise ValueError('작품 번호 형식을 확인하세요.')
        match=re.fullmatch(r'([EXNL]?)([0-9]{1,32})',value.upper())
        if not match:raise ValueError('작품 번호는 히토미 숫자, E번호, X번호, N번호 또는 L번호입니다.')
        prefix,number=match.groups()
        with self.db() as db:
            if prefix=='L':
                if len(number)>19 or not 1<=int(number)<=9223372036854775807:raise ValueError('로컬 번호 범위를 확인하세요.')
                row=db.execute('SELECT work_id FROM work_numbers WHERE number=?',(int(number),)).fetchone()
            else:
                provider={'':'hitomi','E':'ehentai','X':'exhentai','N':'nhentai'}[prefix]
                row=db.execute('SELECT work_id FROM sources WHERE provider=? AND external_id=?',(provider,number)).fetchone()
                if not row and prefix=='E':row=db.execute('SELECT value AS work_id FROM settings WHERE key=?',('legacy_ex_e:'+number,)).fetchone()
        if not row:raise KeyError('보관함에 연결된 작품 번호가 없습니다. 자동 다운로드는 실행하지 않습니다.')
        return self.get_work(row['work_id'])

    def get_work(self, work_id):
        with self.db() as db:
            seen=set()
            while True:
                alias=db.execute('SELECT merged_into FROM works WHERE id=?',(work_id,)).fetchone()
                if not alias or not alias['merged_into']:break
                if work_id in seen or len(seen)>8:raise ValueError('작품 연결 순환을 확인하세요.')
                seen.add(work_id);work_id=alias['merged_into']
            row = db.execute('SELECT works.*,n.number AS local_number FROM works JOIN work_numbers n ON n.work_id=works.id WHERE works.id=?', (work_id,)).fetchone()
            if not row:
                raise KeyError('작품을 찾을 수 없습니다.')
            result = self.work_row(row)
            result['user_tags'] = [r[0] for r in db.execute('SELECT tag FROM user_tags WHERE work_id=? ORDER BY tag',(work_id,))]
            result['sources'] = [self.source_row(s) for s in db.execute(
                'SELECT * FROM sources WHERE work_id=? ORDER BY provider,external_id', (work_id,))]
            result['all_tags'] = list(dict.fromkeys(canonical_tag(t) for t in result['tags'] + result['user_tags'] + [
                t for s in result['sources'] for t in s['tags']] if visible_tag(t)))
            result['short_id']=self.short_identity(result)
            result['edition']=self.edition_details(result)
            result['cover_asset_id']=result['edition'].get('cover_asset_id')
            result['edition_summary']={k:result['edition'][k] for k in ('kind','language','label','translator','group_id')}
            return result

    def list_works(self, query='', sort='added', descending=True, page=1, limit=48,
                   provider='', favorite=False, unread=False, tag='', all_tag=''):
        order = {'added': 'added', 'title': 'title COLLATE NOCASE', 'artist': 'artist COLLATE NOCASE',
                 'pages': 'pages', 'bytes': 'bytes', 'rating': 'rating',
                 'last_read': 'COALESCE(last_read,0)', 'random': 'RANDOM()'}
        if sort not in order or not 1 <= limit <= 120 or not 1 <= page <= 100000:
            raise ValueError('정렬 또는 페이지 범위가 올바르지 않습니다.')
        where, args = ['works.merged_into IS NULL'], []
        if query:
            # Parameters preserve SQL safety; LIKE wildcards are treated literally.
            term = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            where.append("(title LIKE ? ESCAPE '\\' OR artist LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM sources s WHERE s.work_id=works.id AND (s.external_id LIKE ? ESCAPE '\\' OR s.tags LIKE ? ESCAPE '\\'))) ")
            where[-1]="("+where[-1]+" OR EXISTS (SELECT 1 FROM user_tags u WHERE u.work_id=works.id AND u.tag LIKE ? ESCAPE '\\'))"
            args += [term] * 6
            if ':' in query:
                normalized=canonical_tag(query)
                normalized='%'+normalized.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
                where[-1]="("+where[-1]+" OR EXISTS (SELECT 1 FROM json_each(works.tags) t WHERE studio_tag(t.value) LIKE ? ESCAPE '\\') OR EXISTS (SELECT 1 FROM sources s,json_each(s.tags) t WHERE s.work_id=works.id AND studio_tag(t.value) LIKE ? ESCAPE '\\'))"
                args.extend([normalized,normalized])
        if tag:
            where.append("EXISTS (SELECT 1 FROM user_tags u WHERE u.work_id=works.id AND u.tag=?)")
            args.append(tag)
        if all_tag:
            if not isinstance(all_tag,str) or len(all_tag)>300:raise ValueError('태그 길이를 확인하세요.')
            where.append('''(EXISTS (SELECT 1 FROM user_tags u WHERE u.work_id=works.id AND studio_tag(u.tag)=?)
                OR EXISTS (SELECT 1 FROM json_each(works.tags) t WHERE studio_tag(t.value)=?)
                OR EXISTS (SELECT 1 FROM sources s,json_each(s.tags) t WHERE s.work_id=works.id AND studio_tag(t.value)=?))''')
            args.extend([canonical_tag(all_tag)]*3)
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
            rows = db.execute('SELECT works.*,n.number AS local_number FROM works JOIN work_numbers n ON n.work_id=works.id'+condition+' ORDER BY '+order[sort]+
                              (' DESC' if descending else ' ASC')+',id LIMIT ? OFFSET ?',
                              [*args, limit, (page-1)*limit]).fetchall()
            sources={row['id']:[] for row in rows}
            user_tags={row['id']:[] for row in rows}
            if rows:
                placeholders=','.join('?' for _ in rows)
                for source in db.execute('SELECT * FROM sources WHERE work_id IN ('+placeholders+') ORDER BY provider,external_id',list(sources)):
                    sources[source['work_id']].append(self.source_row(source))
                for item in db.execute('SELECT work_id,tag FROM user_tags WHERE work_id IN ('+placeholders+') ORDER BY tag',list(sources)):
                    user_tags[item['work_id']].append(item['tag'])
            items=[]
            for row in rows:
                work=self.work_row(row);work['sources']=sources[row['id']]
                work['user_tags']=user_tags[row['id']]
                work['all_tags']=list(dict.fromkeys(canonical_tag(tag) for tag in work['tags']+work['user_tags']+[tag for source in work['sources'] for tag in source['tags']] if visible_tag(tag)))
                work['short_id']=self.short_identity(work)
                items.append(work)
            if items:
                meta={r['work_id']:dict(r) for r in db.execute('SELECT * FROM editions WHERE work_id IN ('+placeholders+')',list(sources))}
                for work in items:
                    work['edition_summary']={k:meta.get(work['id'],{}).get(k,v) for k,v in {'kind':'comic','language':'','label':'','translator':'','group_id':None}.items()}
                    work['cover_asset_id']=meta.get(work['id'],{}).get('cover_asset_id')
        return dict(items=items,total=total,page=page,limit=limit)

    @staticmethod
    def user_tag_values(value):
        if not isinstance(value,list) or len(value)>100:
            raise ValueError('태그는 최대 100개의 목록이어야 합니다.')
        if any(not isinstance(t,str) or not t.strip() or len(t)>120 or any(ord(c)<32 for c in t) for t in value):
            raise ValueError('태그는 1~120자의 텍스트여야 합니다.')
        return list(dict.fromkeys(t.strip() for t in value))

    def edit_user_tags(self,work_ids,add=None,remove=None):
        if not isinstance(work_ids,list) or not 1<=len(work_ids)<=120 or any(not isinstance(i,str) for i in work_ids):
            raise ValueError('작품을 1~120개 선택하세요.')
        ids=list(dict.fromkeys(work_ids));add=self.user_tag_values([] if add is None else add);remove=self.user_tag_values([] if remove is None else remove)
        with self.db() as db:
            for work_id in ids:
                if not db.execute('SELECT 1 FROM works WHERE id=?',(work_id,)).fetchone():raise KeyError('작품을 찾을 수 없습니다.')
            for work_id in ids:
                db.executemany('DELETE FROM user_tags WHERE work_id=? AND tag=?',[(work_id,t) for t in remove])
                db.executemany('INSERT OR IGNORE INTO user_tags(work_id,tag) VALUES(?,?)',[(work_id,t) for t in add])
                if db.execute('SELECT count(*) FROM user_tags WHERE work_id=?',(work_id,)).fetchone()[0]>100:
                    raise ValueError('작품당 사용자 태그는 최대 100개입니다.')
        return {'updated':len(ids)}

    def tag_catalog(self,query=''):
        if not isinstance(query,str) or len(query)>120:raise ValueError('검색어가 너무 깁니다.')
        term='%'+query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        with self.db() as db:
            rows=db.execute("SELECT u.tag,count(*) AS count FROM user_tags u JOIN works w ON w.id=u.work_id WHERE w.merged_into IS NULL AND u.tag LIKE ? ESCAPE '\\' GROUP BY tag ORDER BY count DESC,tag LIMIT 100",(term,)).fetchall()
        return [dict(row) for row in rows]

    def library_tags(self,query=''):
        if not isinstance(query,str) or len(query)>300:raise ValueError('태그 검색어가 너무 깁니다.')
        query=canonical_tag(query)
        term='%'+query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        with self.db() as db:
            rows=db.execute('''SELECT studio_tag(tag) AS tag,count(DISTINCT work_id) AS count FROM (
                SELECT u.work_id,u.tag FROM user_tags u JOIN works w ON w.id=u.work_id WHERE w.merged_into IS NULL UNION
                SELECT w.id,t.value FROM works w,json_each(w.tags) t WHERE w.merged_into IS NULL UNION
                SELECT s.work_id,t.value FROM sources s JOIN works w ON w.id=s.work_id,json_each(s.tags) t WHERE w.merged_into IS NULL)
                WHERE visible_tag(tag) AND studio_tag(tag) LIKE ? ESCAPE ? GROUP BY studio_tag(tag)
                ORDER BY count DESC,tag LIMIT 100''',(term,'\\')).fetchall()
        return [dict(row) for row in rows]

    def rename_user_tag(self,source,target):
        values=self.user_tag_values([source,target])
        if len(values)!=2:raise ValueError('서로 다른 이름을 입력하세요.')
        source,target=values
        with self.db() as db:
            count=db.execute('SELECT count(*) FROM user_tags WHERE tag=?',(source,)).fetchone()[0]
            db.execute('INSERT OR IGNORE INTO user_tags(work_id,tag) SELECT work_id,? FROM user_tags WHERE tag=?',(target,source))
            db.execute('DELETE FROM user_tags WHERE tag=?',(source,))
        return {'updated':count}

    def annotate_upload(self,sha,tags):
        tags=self.user_tag_values(tags)
        with self.db() as db:
            db.executemany('INSERT OR IGNORE INTO upload_tags(sha256,tag) VALUES(?,?)',[(sha,t) for t in tags])
            self.apply_upload_tags(db,sha)

    @staticmethod
    def apply_upload_tags(db,sha):
        db.execute('INSERT OR IGNORE INTO user_tags(work_id,tag) SELECT w.id,t.tag FROM uploads u JOIN works w ON w.lrr_id=u.lrr_id JOIN upload_tags t ON t.sha256=u.sha256 WHERE u.sha256=?',(sha,))
        if db.execute('SELECT count(*) FROM upload_tags WHERE sha256=?',(sha,)).fetchone()[0]>100:
            raise ValueError('업로드 태그는 최대 100개입니다.')
        row=db.execute('SELECT w.id FROM works w JOIN uploads u ON u.lrr_id=w.lrr_id WHERE u.sha256=?',(sha,)).fetchone()
        if row and db.execute('SELECT count(*) FROM user_tags WHERE work_id=?',(row[0],)).fetchone()[0]>100:
            raise ValueError('작품당 사용자 태그는 최대 100개입니다.')
        if row:db.execute('DELETE FROM upload_tags WHERE sha256=?',(sha,))

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
            db.execute('INSERT INTO work_numbers(work_id) VALUES(?)',(work_id,))
        return self.get_work(work_id)

    def update_work(self, work_id, data):
        work_id=self.get_work(work_id)['id']
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
        if 'artist' in values:values['artist_locked']=1
        if values:
            with self.db() as db:
                db.execute('UPDATE works SET '+','.join(k+'=?' for k in values)+' WHERE id=?',
                           [*values.values(),work_id])
        return self.get_work(work_id)

    def upsert_source(self, work_id, data, schedule=True, lease_guard=None):
        work_id=self.get_work(work_id)['id']
        identity = parse_source(data.get('url'))
        tags = tags_list(data.get('tags',[]))
        comments = comments_list(data.get('comments',[]))
        if data.get('status','manual') not in ('manual','fetched','unverified'):
            raise ValueError('출처 상태가 올바르지 않습니다.')
        artist=data.get('artist_if_empty','')
        if not isinstance(artist,str) or len(artist)>500:raise ValueError('작가 형식을 확인하세요.')
        artist=artist.strip()
        metadata=data.get('metadata')
        if metadata is not None and (not isinstance(metadata,dict) or len(json.dumps(metadata).encode())>256*1024):
            raise ValueError('출처 메타데이터 형식을 확인하세요.')
        if metadata is not None:
            allowed={'provider','external_id','url','title','tags','raw_tags','artists','languages','collector','pages','comments','title_original','title_localized'}
            if set(metadata)-allowed or any(metadata.get(key)!=identity[key] for key in ('provider','external_id','url')):
                raise ValueError('출처 메타데이터의 번호·URL을 확인하세요.')
            if not isinstance(metadata.get('title'),str) or not 0<len(metadata['title'])<=2000:
                raise ValueError('출처 제목 형식을 확인하세요.')
            for key in ('tags','raw_tags','artists','languages'):
                if not isinstance(metadata.get(key),list):raise ValueError('출처 메타데이터 목록을 확인하세요.')
                tags_list(metadata[key])
            comments_list(metadata.get('comments',[]))
            if metadata.get('pages') is not None and (type(metadata['pages']) is not int or not 1<=metadata['pages']<=100000):
                raise ValueError('출처 페이지 수를 확인하세요.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if lease_guard:self.check_automatic_lease(db,lease_guard)
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
            if artist:
                db.execute("UPDATE works SET artist=?,artist_locked=1 WHERE id=? AND artist='' AND artist_locked=0 AND merged_into IS NULL",(artist,work_id))
            if metadata is not None:
                db.execute('UPDATE sources SET metadata=? WHERE id=?',(json.dumps(metadata,ensure_ascii=False),source_id))
            if schedule and identity['provider'] in ('ehentai','exhentai','hitomi') and (not existing or existing['url']!=identity['url'] or (metadata is not None and json.loads(existing['metadata'])!=metadata)):
                self.enqueue_source_link(db,work_id)
        return self.get_work(work_id)

    def import_metadata(self,work_id,metadata,remote=False,schedule=True,lease_guard=None):
        # Source title never overwrites the user's catalog title or edition.
        self.upsert_source(work_id,{'url':metadata['url'],'tags':metadata['tags'],
            'metadata':metadata,'artist_if_empty':', '.join(metadata['artists'])[:500],
            'status':'fetched' if remote else 'manual'},schedule=schedule,lease_guard=lease_guard)
        work=self.get_work(work_id)
        source=next(s for s in work['sources'] if s['url']==metadata['url'])
        if metadata.get('comments'):
            self.apply_comments(work['id'],source['id'],{'status':'fetched','comments':metadata['comments'],'fetched_at':time.time()})
        return self.get_work(work['id'])

    def begin_comment_fetch(self, work_id, source_id):
        work_id=self.get_work(work_id)['id']
        now=time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM sources WHERE id=? AND work_id=?',(source_id,work_id)).fetchone()
            if not row:raise KeyError('출처를 찾을 수 없습니다.')
            if row['comments_attempted'] and now-row['comments_attempted']<60:
                raise ValueError('댓글 갱신 시도는 출처별 60초 간격으로 가능합니다.')
            db.execute('UPDATE sources SET comments_attempted=? WHERE id=?',(now,source_id))

    def apply_comments(self, work_id, source_id, result):
        work_id=self.get_work(work_id)['id']
        if result['status']=='unsupported':return
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM sources WHERE id=? AND work_id=?',(source_id,work_id)).fetchone()
            if not row:raise KeyError('출처를 찾을 수 없습니다.')
            existing=json.loads(row['comments'])
            # Stable IDs are scoped to this source; omitted/deleted comments stay archived.
            updates={item['id']:item for item in result['comments']}
            merged=[updates.pop(item['id'],item) if item.get('id') else item for item in existing]
            merged.extend(updates.values())
            db.execute('UPDATE sources SET comments=?,comments_fetched=?,comments_status=? WHERE id=?',
                       (json.dumps(comments_list(merged),ensure_ascii=False),result['fetched_at'],result['status'],source_id))

    def sync_lrr(self, archives):
        count = 0
        for item in archives:
            lrr_id = item.get('arcid','')
            if not re.fullmatch('[0-9a-f]{40}',lrr_id):
                continue
            with self.db() as db:
                if db.execute('SELECT 1 FROM copy_retirements WHERE copy_lrr_id=?',(lrr_id,)).fetchone():continue
            stored_stem=Path(item.get('filename','')).stem
            with self.db() as db:
                upload=db.execute('SELECT * FROM uploads WHERE sha256=?',(stored_stem,)).fetchone()
            if upload and (not item.get('title') or item['title']==stored_stem):
                item={**item,'title':Path(upload['original_name']).stem}
            tags = tags_list(item.get('tags',''))
            artist = ', '.join(x.split(':',1)[1] for x in tags if x.startswith('artist:'))
            with self.db() as db:
                row = db.execute('SELECT id,title_locked,artist_locked FROM works WHERE lrr_id=?',(lrr_id,)).fetchone()
            if row:
                with self.db() as db:
                    db.execute('UPDATE works SET pages=?,bytes=? WHERE id=?',
                               (int(item.get('pagecount') or 0),int(item.get('arcsize') or item.get('size') or 0),row['id']))
                    if not row['title_locked']:
                        db.execute('UPDATE works SET title=?,tags=? WHERE id=?',
                                   (item.get('title') or lrr_id,json.dumps(tags,ensure_ascii=False),row['id']))
                    if not row['title_locked'] and not row['artist_locked']:
                        db.execute('UPDATE works SET artist=? WHERE id=?',(artist,row['id']))
                work = self.get_work(row['id'])
            else:
                work = self.create_work(item.get('title') or lrr_id,artist,lrr_id,
                                        item.get('pagecount') or 0,item.get('arcsize') or item.get('size') or 0,tags)
            with self.db() as db:
                filename=Path(str(item.get('filename','')).replace('\\','/')).name[:1000]
                if upload:filename=upload['original_name']
                db.execute('UPDATE works SET archive_filename=? WHERE id=?',(filename,work['id']))
            for tag in tags:
                if tag.startswith('source:'):
                    value = tag.split(':',1)[1].strip()
                    try:self.upsert_source(work['id'],{'url':value if value.startswith('https://') else 'https://'+value})
                    except ValueError:pass  # A source collision is never used to merge works.
            if upload:
                with self.db() as db:
                    db.execute("UPDATE uploads SET lrr_id=?,state='indexed' WHERE sha256=?",(lrr_id,upload['sha256']))
                    self.apply_upload_tags(db,upload['sha256'])
            count += 1
        return count

    @staticmethod
    def consolidate_copy(db, old_id, survivor_id, sha, copy_lrr_id, details):
        """Called only by NAS-local executor after full file/backend verification."""
        if db.execute('SELECT 1 FROM editions WHERE work_id IN (?,?)',(old_id,survivor_id)).fetchone() or db.execute('SELECT 1 FROM voice_assets WHERE work_id IN (?,?)',(old_id,survivor_id)).fetchone():raise ValueError('edition_metadata_requires_review')
        previous=db.execute('SELECT * FROM copy_retirements WHERE sha256=?',(sha,)).fetchone()
        if previous:
            if previous['old_work_id']!=old_id or previous['work_id']!=survivor_id:raise ValueError('retirement_identity_conflict')
            return False
        old=db.execute('SELECT * FROM works WHERE id=?',(old_id,)).fetchone()
        target=db.execute('SELECT * FROM works WHERE id=?',(survivor_id,)).fetchone()
        if not old or not target or old_id==survivor_id or old['merged_into'] or target['merged_into'] or old['lrr_id']!=copy_lrr_id:raise ValueError('retirement_work_conflict')
        if db.execute("SELECT 1 FROM jobs WHERE work_id IN (?,?) AND state IN ('queued','running')",(old_id,survivor_id)).fetchone():raise ValueError('active_download_job')
        for field,lock in [('title','title_locked'),('artist','artist_locked')]:
            if old[lock] and target[lock] and old[field]!=target[field]:raise ValueError('manual_metadata_conflict')
        # Keep the untouched old work row as an archive of scalar preferences.
        tags=list(dict.fromkeys(json.loads(old['tags'])+json.loads(target['tags'])))
        user_values={r[0] for r in db.execute('SELECT tag FROM user_tags WHERE work_id IN (?,?)',(old_id,survivor_id))}
        if len(user_values|set(tags))>100:raise ValueError('merged_user_tag_limit')
        db.executemany('INSERT OR IGNORE INTO user_tags(work_id,tag) VALUES(?,?)',[(survivor_id,t) for t in tags])
        db.execute('INSERT OR IGNORE INTO user_tags SELECT ?,tag FROM user_tags WHERE work_id=?',(survivor_id,old_id))
        db.execute('UPDATE sources SET work_id=? WHERE work_id=?',(survivor_id,old_id))
        pages=int(details['pages'])
        if pages<1 or max(old['progress'],target['progress'])>pages:raise ValueError('progress_page_mismatch')
        details={**details,'old_work_before':dict(old),'survivor_before':dict(target)}
        values={'pages':pages,'favorite':max(old['favorite'],target['favorite']),'rating':max(old['rating'],target['rating']),
                'progress':max(old['progress'],target['progress']),'last_read':max(old['last_read'] or 0,target['last_read'] or 0) or None,
                'tags':json.dumps(tags,ensure_ascii=False)}
        for field,lock in [('title','title_locked'),('artist','artist_locked')]:
            if old[lock] or not target[field]:values[field]=old[field];values[lock]=max(old[lock],target[lock])
        db.execute('UPDATE works SET '+','.join(k+'=?' for k in values)+' WHERE id=?',[*values.values(),survivor_id])
        db.execute('UPDATE works SET merged_into=?,lrr_id=NULL WHERE id=?',(survivor_id,old_id))
        db.execute("UPDATE uploads SET state='retired',lrr_id=NULL WHERE sha256=?",(sha,))
        db.execute('INSERT INTO copy_retirements VALUES(?,?,?,?,?,?,?)',
            (sha,copy_lrr_id,old_id,survivor_id,'merged',json.dumps(details,ensure_ascii=False),time.time()))
        return True

    def organization_preview(self, query='', page=1):
        result=self.list_works(query=query,page=page,limit=24,sort='title',descending=False)
        for work in result['items']:
            hint=work['organization']
            source=next(iter(work['sources']),{})
            number=source.get('external_id') or (hint['numbers'][0]['number'] if not hint['ambiguous'] else None)
            work['proposed_filename']=canonical_archive_name(hint['title'] if work['title']==hint['filename'] else work['title'],work['artist'] or hint['artist'],source.get('provider'),number)
        return result

    @staticmethod
    def _fill_filename_artists(db, rows):
        updated=0
        for row in rows:
            if row['merged_into'] or row['artist'] or row['artist_locked']:continue
            artist=filename_hints(row['archive_filename'] or row['title'])['artist']
            if not artist:continue
            db.execute('UPDATE works SET artist=?,artist_locked=1 WHERE id=?',(artist,row['id']));updated+=1
        return {'updated':updated,'inspected':len(rows),'skipped':len(rows)-updated}

    def apply_filename_artists(self, work_ids):
        if not isinstance(work_ids,list) or not 1<=len(work_ids)<=200 or any(not isinstance(i,str) or not re.fullmatch('[0-9a-f]{32}',i) for i in work_ids):
            raise ValueError('확인한 작품을 최대200개 선택하세요.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=[]
            for work_id in set(work_ids):
                row=db.execute('SELECT * FROM works WHERE id=?',(work_id,)).fetchone()
                if not row:raise KeyError('작품을 찾을 수 없습니다.')
                rows.append(row)
            return self._fill_filename_artists(db,rows)

    def apply_all_filename_artists(self):
        # One local transaction, independent of page/search and without network I/O.
        # Fetch only eligible rows; preserve all existing values and explicit blanks.
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute("SELECT * FROM works WHERE merged_into IS NULL AND artist='' AND artist_locked=0 LIMIT 10001").fetchall()
            if len(rows)>10000:raise ValueError('빈 작가가 10000개를 넘습니다. 페이지별로 등록하세요.')
            return self._fill_filename_artists(db,rows)

    def begin_matching(self, work_id):
        self.get_work(work_id)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            key='matching-attempt:'+work_id
            row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
            now=time.time()
            if row and now-float(row[0])<60:raise ValueError('세 사이트 확인은 작품별60초 간격으로 가능합니다.')
            db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(key,str(now)))

    def progress(self, work_id, page):
        work = self.get_work(work_id)
        work_id=work['id']
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
            candidates=db.execute("SELECT * FROM jobs WHERE target=? AND state IN ('queued','running','failed','blocked')",(target,)).fetchall()
            for existing in candidates:
                identity=parse_source(existing['url'])
                if (identity['provider'],identity['external_id'])!=(source['provider'],source['external_id']):continue
                remote=json.loads(existing['result'])
                if existing['state'] in ('queued','running'):return dict(existing)
                if existing['engine']=='lanraragi' and (remote.get('remote_job') or remote.get('submission')=='pending'):
                    raise ValueError('기존 서버 작업의 접수 여부를 먼저 확인하세요. 다른 엔진으로도 중복 제출하지 않았습니다.')
            job_id=uid();now=time.time()
            db.execute('INSERT INTO jobs(id,work_id,url,target,engine,state,created,updated) VALUES(?,?,?,?,?,?,?,?)',
                       (job_id,work_id,source['url'],target,engine,'queued',now,now))
        return self.job(job_id)

    def resolve_reference(self,provider,reference):
        if provider not in ('ehentai','exhentai','hitomi','nhentai'):
            raise ValueError('출처를 선택하세요.')
        if not isinstance(reference,str) or not 1<=len(reference.strip())<=2048:
            raise ValueError('작품 번호 또는 전체 URL을 입력하세요.')
        value=reference.strip();origin='url'
        if re.fullmatch('[0-9]{1,20}',value):
            number=str(int(value))
            if number=='0':raise ValueError('올바른 작품 번호를 입력하세요.')
            with self.db() as db:
                saved=db.execute('SELECT url FROM sources WHERE provider=? AND external_id=?',(provider,number)).fetchone()
            if saved:value=saved[0];origin='saved'
            elif provider in ('ehentai','exhentai'):
                raise ValueError('E-Hentai의 처음 등록하는 번호에는 전체 작품 URL이 필요합니다. 번호 외 URL 식별값을 추측하지 않습니다.')
            else:
                value=(f'https://hitomi.la/galleries/{number}.html' if provider=='hitomi' else f'https://nhentai.net/g/{number}/')
                origin='number'
        source=parse_source(value)
        if source['provider']!=provider:raise ValueError('선택한 출처와 URL의 사이트가 다릅니다.')
        with self.db() as db:
            work=db.execute('''SELECT w.id,w.lrr_id FROM sources s JOIN works w ON w.id=s.work_id
                               WHERE s.provider=? AND s.external_id=?''',
                            (provider,source['external_id'])).fetchone()
        return {**source,'origin':origin,'work_id':work['id'] if work else None,
                'available':bool(work and work['lrr_id'])}

    def request_download(self,provider,reference,target,engine):
        if provider=='exhentai':raise ValueError('익헨의 인증된 동일 출처 다운로드는 아직 검증 전입니다. 자동 정보 연결과 별개입니다.')
        if target not in ('nas','pc') or engine not in ('lanraragi','command') or (target=='pc' and engine=='lanraragi'):
            raise ValueError('저장 대상 또는 엔진이 올바르지 않습니다.')
        source=self.resolve_reference(provider,reference)
        if source['available']:
            return {'state':'available','work_id':source['work_id']}
        return {'state':'queued','job':self.public_job(self.queue(source['url'],target,engine,source['work_id']))}

    def job(self, job_id):
        with self.db() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row:raise KeyError('작업을 찾을 수 없습니다.')
            return dict(row)

    @staticmethod
    def public_job(job):
        return {k:v for k,v in job.items() if k not in ('lease','lease_until')}

    def expire_jobs(self):
        now=time.time()
        with self.db() as db:
            db.execute("UPDATE jobs SET state='blocked',lease=NULL,lease_until=NULL,message='임대 만료: 출력 폴더와 원격 작업을 확인한 뒤 다시 시도하세요.',updated=? WHERE state='running' AND lease_until<?",(now,now))

    def jobs(self):
        self.expire_jobs()
        with self.db() as db:
            return [dict(x) for x in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 200')]

    def worker_seen(self,target):
        if target not in ('nas','pc'):raise ValueError('잘못된 작업 대상입니다.')
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',('command_worker_seen_'+target,str(time.time())))

    def worker_status(self):
        with self.db() as db:
            rows=dict(db.execute("SELECT key,value FROM settings WHERE key IN ('command_worker_seen_nas','command_worker_seen_pc')"))
        return {target:0<=time.time()-float(rows.get('command_worker_seen_'+target,'0'))<60 for target in ('nas','pc')}

    def index_command_archive(self,job_id,metadata,verified_sha):
        """Link only the exact completed attempt, never equal cross-site numbers."""
        job=self.job(job_id);result=json.loads(job['result']);source=parse_source(job['url'])
        arcid=metadata.get('arcid','');directory=result.get('directory','')
        expected=source['provider']+'-'+source['external_id']
        proofs=result.get('archives',[])
        if job['target']!='nas' or job['engine']!='command' or job['state']!='complete' or not re.fullmatch(job_id+r'-[0-9a-f]{16}',directory) or metadata.get('filename') not in (expected,expected+'.cbz') or not re.fullmatch('[0-9a-f]{40}',arcid) or not re.fullmatch('[0-9a-f]{64}',verified_sha) or not any(p.get('file')==expected+'.cbz' and p.get('sha256')==verified_sha for p in proofs if isinstance(p,dict)):
            raise ValueError('다운로드 결과와 색인 파일의 연결을 확인하세요.')
        with self.db() as db:
            owner=db.execute('SELECT work_id FROM sources WHERE provider=? AND external_id=?',(source['provider'],source['external_id'])).fetchone()
            work_id=owner[0] if owner else job['work_id']
            if work_id:
                work=db.execute('SELECT id,lrr_id FROM works WHERE id=? AND merged_into IS NULL',(work_id,)).fetchone()
                other=db.execute('SELECT id FROM works WHERE lrr_id=?',(arcid,)).fetchone()
                if not work or work['lrr_id'] not in (None,arcid) or other and other[0]!=work_id:
                    raise ValueError('기존 파일 또는 다른 판본과의 연결은 직접 확인하세요.')
                db.execute('UPDATE works SET lrr_id=? WHERE id=?',(arcid,work_id))
        self.sync_lrr([metadata])
        with self.db() as db:work_id=db.execute('SELECT id FROM works WHERE lrr_id=?',(arcid,)).fetchone()[0]
        self.upsert_source(work_id,{'url':source['url']})
        result.update(catalog_work_id=work_id,catalog_indexed=True)
        with self.db() as db:
            db.execute('UPDATE jobs SET result=?,message=? WHERE id=? AND state=?',
                       (json.dumps(result),'다운로드 및 보관함 연결 완료',job_id,'complete'))
        return work_id

    def claim(self, target, engine):
        if target not in ('nas','pc') or engine not in ('lanraragi','command'):
            raise ValueError('잘못된 작업 대상입니다.')
        now=time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            # Expired command tasks need explicit retry: a crashed engine might still be writing.
            db.execute("UPDATE jobs SET state='blocked',lease=NULL,lease_until=NULL,message='임대 만료: 출력 폴더와 원격 작업을 확인한 뒤 다시 시도하세요.',updated=? WHERE state='running' AND lease_until<?",(now,now))
            row=db.execute("SELECT * FROM jobs WHERE target=? AND engine=? AND state='queued' ORDER BY created LIMIT 1",(target,engine)).fetchone()
            if not row:return None
            lease=secrets.token_urlsafe(32)
            db.execute("UPDATE jobs SET state='running',lease=?,lease_until=?,updated=? WHERE id=?",(lease,now+120,now,row['id']))
            result=dict(row);result.update(state='running',lease=lease)
            return result

    def report(self, job_id, lease, state, message='', result=None, worker_target=None):
        if state not in ('running','complete','failed','blocked'):
            raise ValueError('잘못된 작업 상태입니다.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row or row['state']!='running' or not secrets.compare_digest(row['lease'] or '',lease or ''):
                raise ValueError('만료되었거나 잘못된 작업 임대입니다.')
            if worker_target and (row['engine']!='command' or worker_target not in ('*',row['target'])):
                raise ValueError('작업자의 대상 범위가 올바르지 않습니다.')
            if row['lease_until'] < time.time():
                raise ValueError('작업 임대가 만료됐습니다.')
            if result is not None and (not isinstance(result,dict) or len(json.dumps(result))>32768):
                raise ValueError('작업 결과는 32KiB 이내 JSON 객체여야 합니다.')
            if row['engine']=='command' and state=='complete':
                if not isinstance(result,dict) or type(result.get('files')) is not int or result['files']<1 or type(result.get('bytes')) is not int or result['bytes']<1 or not re.fullmatch(job_id+r'-[0-9a-f]{16}',str(result.get('directory',''))):
                    raise ValueError('완료 보고에 파일 수, 크기와 시도별 출력 폴더가 필요합니다.')
            db.execute('UPDATE jobs SET state=?,message=?,result=?,updated=?,lease_until=? WHERE id=?',
                       (state,str(message)[:2000],json.dumps(result if result is not None else json.loads(row['result']),ensure_ascii=False),time.time(),time.time()+120,job_id))

    def reconcile_remote(self, job_id, remote_id, state):
        """Resolve an expired upstream job without submitting another download."""
        if state not in ('finished','failed'):
            raise ValueError('원격 작업이 진행 중이거나 상태를 확인할 수 없습니다. 다시 제출하지 않았습니다.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row or row['state'] not in ('blocked','failed') or json.loads(row['result']).get('remote_job')!=remote_id:
                raise ValueError('원격 작업 상태가 변경됐습니다. 새로 고침하세요.')
            result=json.loads(row['result'])
            if state=='failed':result['previous_remote_job']=result.pop('remote_job')
            db.execute('UPDATE jobs SET state=?,result=?,message=?,updated=? WHERE id=?',
                       ('complete' if state=='finished' else 'failed',json.dumps(result),
                        '원격 작업 확인: '+state,time.time(),job_id))

    def retry(self, job_id):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row or row['state'] not in ('failed','blocked'):
                raise ValueError('실패하거나 중단된 작업만 다시 시도할 수 있습니다.')
            if row['engine']=='lanraragi' and (json.loads(row['result']).get('remote_job') or json.loads(row['result']).get('submission')=='pending'):
                raise ValueError('원격 작업이 남아 있습니다. 상태를 확인한 뒤 중복 다운로드 없이 처리해야 합니다.')
            identity=parse_source(row['url'])
            for active in db.execute("SELECT id,url FROM jobs WHERE target=? AND engine=? AND state IN ('queued','running')",(row['target'],row['engine'])):
                other=parse_source(active['url'])
                if (other['provider'],other['external_id'])==(identity['provider'],identity['external_id']):
                    raise ValueError('같은 출처의 다운로드가 이미 대기 또는 실행 중입니다.')
            db.execute("UPDATE jobs SET state='queued',lease=NULL,remote_id=NULL,message='',updated=? WHERE id=?",(time.time(),job_id))

    def export(self):
        with self.db() as db:
            ids=[x[0] for x in db.execute('SELECT id FROM works WHERE merged_into IS NULL ORDER BY added')]
        return {'schema_version':1,'exported_at':time.time(),'works':[self.get_work(i) for i in ids]}

    @staticmethod
    def folder_public(row):
        return {k:row[k] for k in ('id','collections','state','limit_count','imported','scanned','skipped','errors','created','updated','message')}

    def folder_status(self):
        with self.db() as db:
            row=db.execute("SELECT value FROM settings WHERE key='folder-worker'").fetchone()
            worker=json.loads(row[0]) if row else {}
            jobs=[self.folder_public(r) for r in db.execute('SELECT * FROM folder_jobs ORDER BY created DESC LIMIT 20')]
        for job in jobs:job['collections']=json.loads(job['collections'])
        return {'connected':time.time()-worker.get('seen',0)<660,
                'configured':bool(worker),'collections':worker.get('collections',[]),
                'last_seen':worker.get('seen'),'jobs':jobs,'batch_limit':10}

    def queue_folder_import(self,collections,request_key):
        if (not isinstance(collections,list) or not collections
            or any(type(c) is not str or c not in ('manga','images') for c in collections)
            or len(set(collections))!=len(collections)):
            raise ValueError('manga 또는 images에서 가져올 폴더를 선택하세요.')
        if not isinstance(request_key,str) or not re.fullmatch('[0-9a-f]{32}',request_key):
            raise ValueError('가져오기 요청 번호가 올바르지 않습니다.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT * FROM folder_jobs WHERE request_key=?',(request_key,)).fetchone()
            if previous:return self.folder_public(previous)
            worker=db.execute("SELECT value FROM settings WHERE key='folder-worker'").fetchone()
            worker=json.loads(worker[0]) if worker else {}
            if time.time()-worker.get('seen',0)>=660 or not set(collections)<=set(worker.get('collections',[])):
                raise ValueError('NAS 폴더 작업자를 먼저 연결하세요. 원본 폴더에는 아직 접근하지 않았습니다.')
            active=db.execute("SELECT * FROM folder_jobs WHERE state IN ('queued','running')").fetchone()
            if active:raise ValueError('폴더 가져오기가 이미 대기 또는 실행 중입니다.')
            now=time.time();identity=uid()
            db.execute('''INSERT INTO folder_jobs(id,request_key,source_id,collections,state,created,updated)
                VALUES(?,?,?,?, 'queued',?,?)''',(identity,request_key,worker['source_id'],json.dumps(collections),now,now))
            return self.folder_public(db.execute('SELECT * FROM folder_jobs WHERE id=?',(identity,)).fetchone())

    def cancel_folder_import(self,identity):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT state FROM folder_jobs WHERE id=?',(identity,)).fetchone()
            if not row:raise KeyError('가져오기 작업을 찾을 수 없습니다.')
            if row['state']!='queued':raise ValueError('대기 중인 작업만 취소할 수 있습니다. 실행 중인 작업은 최대10권에서 끝납니다.')
            db.execute("UPDATE folder_jobs SET state='cancelled',updated=? WHERE id=?",(time.time(),identity))
        return {'success':True}
