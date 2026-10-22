"""Durable automatic cross-site source connections; never downloads or merges files."""
import json
import secrets
import time
import urllib.error
from metadata import fetch_metadata, counterpart_candidates

PROVIDERS=('ehentai','exhentai','hitomi')
SCHEMA='''
CREATE TABLE IF NOT EXISTS source_link_jobs(
 work_id TEXT PRIMARY KEY REFERENCES works(id),epoch INTEGER NOT NULL DEFAULT 1,
 state TEXT NOT NULL DEFAULT 'queued',attempts INTEGER NOT NULL DEFAULT 0,
 created REAL NOT NULL,updated REAL NOT NULL,next_at REAL NOT NULL,
 lease TEXT,lease_until REAL,result TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS source_links_due ON source_link_jobs(state,next_at);
CREATE TABLE IF NOT EXISTS source_link_circuits(provider TEXT PRIMARY KEY,until REAL NOT NULL,status TEXT NOT NULL);
'''


class LeaseLost(ValueError):pass


class AutomaticSources:
    @staticmethod
    def enqueue_source_link(db,work_id,now=None):
        now=time.time() if now is None else now
        db.execute('''INSERT INTO source_link_jobs(work_id,created,updated,next_at) VALUES(?,?,?,?)
            ON CONFLICT(work_id) DO UPDATE SET epoch=epoch+1,
            state=CASE WHEN state='running' THEN 'running' ELSE 'queued' END,
            attempts=0,result='{}',updated=excluded.updated,next_at=excluded.next_at''',(work_id,now,now,now))

    def automatic_enabled(self):
        with self.db() as db:
            row=db.execute("SELECT value FROM settings WHERE key='automatic_source_links'").fetchone()
        return not row or row[0]!='false'

    def set_automatic_enabled(self,enabled):
        if type(enabled) is not bool:raise ValueError('자동 연결 설정은 켜기·끄기만 가능합니다.')
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('automatic_source_links',?)",('true' if enabled else 'false',))
            if enabled:db.execute("UPDATE source_link_jobs SET state='queued',attempts=0,next_at=? WHERE state IN ('blocked','waiting')",(time.time(),))
        return self.automatic_summary()

    def automatic_summary(self):
        with self.db() as db:
            counts={r[0]:r[1] for r in db.execute('SELECT state,count(*) FROM source_link_jobs GROUP BY state')}
        return {'enabled':self.automatic_enabled(),'counts':counts,'site_verified':False}

    def automatic_status(self,work_id):
        with self.db() as db:row=db.execute('SELECT * FROM source_link_jobs WHERE work_id=?',(work_id,)).fetchone()
        if not row:return {'state':'no_source','result':{},'epoch':0}
        result=dict(row);result['result']=json.loads(result['result'])
        result.pop('lease',None);return result

    def retry_automatic(self,work_id):
        work=self.get_work(work_id)
        if not any(s['provider'] in PROVIDERS for s in work['sources']):raise ValueError('기준 출처 URL 하나를 먼저 연결하세요.')
        with self.db() as db:self.enqueue_source_link(db,work['id'])
        return self.automatic_status(work['id'])

    def claim_automatic(self):
        if not self.automatic_enabled():return None
        now=time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE source_link_jobs SET state='queued',lease=NULL,lease_until=NULL WHERE state='running' AND lease_until<?",(now,))
            row=db.execute("SELECT j.* FROM source_link_jobs j JOIN works w ON w.id=j.work_id WHERE w.merged_into IS NULL AND j.state IN ('queued','waiting','scanning') AND j.next_at<=? ORDER BY j.next_at,j.created LIMIT 1",(now,)).fetchone()
            if not row:return None
            token=secrets.token_hex(16)
            db.execute("UPDATE source_link_jobs SET state='running',attempts=attempts+1,lease=?,lease_until=?,updated=? WHERE work_id=?",(token,now+900,now,row['work_id']))
        return {**dict(row),'lease':token,'attempts':row['attempts']+1}

    @staticmethod
    def check_automatic_lease(db,job):
        enabled=db.execute("SELECT value FROM settings WHERE key='automatic_source_links'").fetchone()
        if enabled and enabled[0]=='false':raise LeaseLost('자동 연결이 중지됐습니다.')
        row=db.execute('SELECT * FROM source_link_jobs WHERE work_id=?',(job['work_id'],)).fetchone()
        if not row or row['state']!='running' or row['lease']!=job['lease'] or row['epoch']!=job['epoch'] or row['lease_until']<time.time():
            raise LeaseLost('출처 작업의 임대 또는 기준 정보가 변경됐습니다.')

    def automatic_heartbeat(self,job):
        with self.db() as db:
            self.check_automatic_lease(db,job)
            db.execute('UPDATE source_link_jobs SET lease_until=? WHERE work_id=?',(time.time()+900,job['work_id']))

    def finish_automatic(self,job,result,state):
        now=time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM source_link_jobs WHERE work_id=?',(job['work_id'],)).fetchone()
            if not row or row['lease']!=job['lease']:return
            if row['epoch']!=job['epoch']:state='queued';result={}
            elif state=='waiting' and job['attempts']>=5:state='blocked'
            delay=10 if state=='scanning' else min(1800*2**(job['attempts']-1),21600) if state=='waiting' else 0
            db.execute('UPDATE source_link_jobs SET state=?,result=?,updated=?,next_at=?,attempts=?,lease=NULL,lease_until=NULL WHERE work_id=?',
                (state,json.dumps(result,ensure_ascii=False),now,now+delay,0 if state=='scanning' else job['attempts'],job['work_id']))

    def automatic_circuit(self,provider,status=None):
        now=time.time()
        with self.db() as db:
            if status:
                db.execute('INSERT OR REPLACE INTO source_link_circuits VALUES(?,?,?)',(provider,now+1800,status))
            row=db.execute('SELECT * FROM source_link_circuits WHERE provider=? AND until>?',(provider,now)).fetchone()
        return dict(row) if row else None

    def automatic_session_changed(self,fingerprint):
        with self.db() as db:
            row=db.execute("SELECT value FROM settings WHERE key='source_session_fingerprint'").fetchone()
            if row and row[0]==fingerprint:return
            db.execute("INSERT OR REPLACE INTO settings VALUES('source_session_fingerprint',?)",(fingerprint,))
            db.execute('DELETE FROM source_link_circuits')
            db.execute("UPDATE source_link_jobs SET state='queued',attempts=0,next_at=? WHERE state IN ('waiting','blocked')",(time.time(),))


class AutoLinker:
    def __init__(self,store,transport,pause=None):
        self.store,self.transport,self.pause=store,transport,pause

    def run_one(self):
        job=self.store.claim_automatic()
        if not job:return False
        previous=json.loads(job['result']);output={'sites':[],'connected':[]};state='complete';scanning=False
        try:
            work=self.store.get_work(job['work_id'])
            sources=[s for s in work['sources'] if s['provider'] in PROVIDERS]
            if not sources:
                self.store.finish_automatic(job,output,'complete');return True
            fetch,index,access=self.transport()
            def guarded_fetch(url):
                self.store.automatic_heartbeat(job)
                if self.pause and self.pause(3):raise LeaseLost('서비스 중단')
                return fetch(url)
            def guarded_index(artist,offset=None):
                self.store.automatic_heartbeat(job)
                if self.pause and self.pause(3):raise LeaseLost('서비스 중단')
                return index(artist,offset) if offset is not None else index(artist)
            # Prefer a complete snapshot, then a known public source. No guessed ID.
            source=next((s for s in sources if s['status']=='fetched' and s['metadata'].get('pages') and s['metadata'].get('artists')),None)
            source=source or next((s for s in sources if s['metadata'].get('pages') and s['metadata'].get('artists')),None)
            source=source or next((s for s in sources if s['provider']=='hitomi'),None) or next((s for s in sources if s['provider']=='ehentai'),None) or sources[0]
            metadata=source['metadata']
            if not metadata:
                if access.get(source['provider']):raise ValueError('source_session_required')
                circuit=self.store.automatic_circuit(source['provider'])
                if circuit:raise ValueError('source_temporarily_unavailable')
                metadata=fetch_metadata(source['url'],guarded_fetch)
                self.store.import_metadata(work['id'],metadata,remote=True,schedule=False,lease_guard=job)
            elif not metadata.get('pages') and work['pages']>0:
                # This evidence belongs to the local edition, not the source
                # snapshot; never label it as remotely fetched page metadata.
                metadata={**metadata,'pages':work['pages']}
                output['baseline_pages']='local-library'
            for target in PROVIDERS:
                old=next((s for s in previous.get('sites',[]) if s['provider']==target),{})
                existing=next((s for s in sources if s['provider']==target),None)
                if existing:
                    if target==source['provider'] or (existing['metadata'] and existing['status']=='fetched'):
                        output['sites'].append({'provider':target,'status':'connected','items':[]});continue
                    circuit=self.store.automatic_circuit(target)
                    if circuit or access.get(target):
                        output['sites'].append({'provider':target,'status':access.get(target) or circuit['status'],'items':[]})
                        state='waiting';continue
                    try:
                        detail=fetch_metadata(existing['url'],guarded_fetch)
                        self.store.import_metadata(work['id'],detail,remote=True,schedule=False,lease_guard=job)
                        output['sites'].append({'provider':target,'status':'connected','items':[]})
                    except LeaseLost:raise
                    except (ValueError,OSError,KeyError,TypeError):
                        self.store.automatic_circuit(target,'access_required')
                        output['sites'].append({'provider':target,'status':'access_required','items':[]});state='waiting'
                    continue
                if old.get('finished'):
                    output['sites'].append(old)
                    if state!='waiting':state='review'
                    continue
                circuit=self.store.automatic_circuit(target)
                if circuit or access.get(target):
                    output['sites'].append({**old,'provider':target,'status':access.get(target) or circuit['status'],'items':old.get('items',[])})
                    state='waiting';continue
                cursor=old.get('next_cursor') or {'offset':0}
                result=counterpart_candidates(metadata,guarded_fetch,guarded_index,target=target,cursor=cursor)
                accumulated={(item['metadata']['provider'],item['metadata']['external_id']):item for item in old.get('items',[])+result['items']}
                result['items']=sorted(accumulated.values(),key=lambda item:(item['comparison']['automatic_eligible'],item['comparison']['artist_match'],item['comparison']['title_similarity']),reverse=True)[:10]
                if result['status']=='no_candidates' and result['items']:result['status']='checked'
                result['finished']=result['status'] in ('checked','no_candidates','needs_artist','search_limit')
                if result['status'] in ('access_required','unavailable','partial'):result['next_cursor']=cursor
                eligible=[item for item in result['items'] if item['comparison']['automatic_eligible']]
                if result['status']=='checked' and len(eligible)==1:
                    try:
                        self.store.import_metadata(work['id'],eligible[0]['metadata'],remote=True,schedule=False,lease_guard=job)
                        output['connected'].append(target);result['status']='connected'
                    except LeaseLost:raise
                    except ValueError:result['status']='ownership_conflict'
                if result['status']=='checked':result['status']='review' if result['items'] else 'no_candidates'
                for item in result['items']:
                    item['metadata']={**item['metadata'],'comments':[]}
                output['sites'].append(result)
                if result['status']=='scanning':scanning=True
                if result['status'] in ('access_required','unavailable','partial'):
                    self.store.automatic_circuit(target,result['status']);state='waiting'
                elif result['status']!='connected' and state!='waiting':state='review'
        except LeaseLost:
            state='queued';scanning=False
        except urllib.error.HTTPError as error:
            state='review' if error.code in (404,410) else 'waiting'
            status='not_found' if state=='review' else 'access_required' if error.code in (301,302,303,307,308,401,403,429) else 'unavailable'
            output['message']='기준 출처의 정상 응답을 확인하지 못했습니다.'
            if 'source' in locals():
                output['sites'].append({'provider':source['provider'],'status':status,'items':[]})
                if state=='waiting':self.store.automatic_circuit(source['provider'],status)
        except (ValueError,OSError,KeyError,TypeError):
            state='waiting';output['message']='기준 출처의 정보 또는 정상 접근을 확인하지 못했습니다. 파일·작품 병합은 실행하지 않았습니다.'
            if 'source' in locals():
                status=access.get(source['provider'],'unavailable') if 'access' in locals() else 'unavailable'
                output['sites'].append({'provider':source['provider'],'status':status,'items':[]})
                self.store.automatic_circuit(source['provider'],status)
        if scanning:state='scanning'
        self.store.finish_automatic(job,output,state)
        return True
