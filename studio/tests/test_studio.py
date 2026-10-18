import base64
import json
import os
import signal
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from connectors import fetch_comments
from sources import parse_source
from store import Store
from server import Studio, make_server
from worker import run_job

TEST_ROOT=Path(__file__).resolve().parents[1]/'test-results'
TEST_ROOT.mkdir(exist_ok=True)

def temporary_directory():
    value=tempfile.TemporaryDirectory(dir=TEST_ROOT)
    assert Path(value.name).resolve().parent==TEST_ROOT.resolve()
    return value


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=temporary_directory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'catalog.db')
        self.work=self.store.create_work('A quiet library','Example Artist')

    def test_hitomi_identity_preserves_full_original_url(self):
        url='https://hitomi.la/doujinshi/synthetic-work-123.html'
        self.assertEqual(parse_source(url),{'provider':'hitomi','external_id':'123','url':url})

    def test_comment_connector_limits_and_preserves_source_provenance(self):
        url='https://nhentai.net/g/123/'
        payload=[{'id':n,'poster':{'username':'Fixture'},'body':'Synthetic comment','post_date':1700000000} for n in range(101)]
        result=fetch_comments(url,lambda endpoint:payload)
        self.assertEqual(result['status'],'limited')
        self.assertEqual(len(result['comments']),100)
        self.assertEqual(result['comments'][0]['source_url'],url)
        source=self.store.upsert_source(self.work['id'],{'url':url,'comments':[{'id':'archived','text':'preserve'}]})['sources'][0]
        self.store.apply_comments(self.work['id'],source['id'],result)
        payload[0]['body']='Updated fixture'
        refreshed=fetch_comments(url,lambda endpoint:payload[:1])
        self.store.apply_comments(self.work['id'],source['id'],refreshed)
        comments=self.store.get_work(self.work['id'])['sources'][0]['comments']
        self.assertEqual(len(comments),101)
        self.assertEqual(next(c for c in comments if c['id']=='0')['text'],'Updated fixture')
        self.assertEqual(comments[0]['id'],'archived')

    def test_unsupported_comments_make_no_network_request(self):
        def forbidden(endpoint):raise AssertionError('Unexpected network call')
        for url in ['https://hitomi.la/galleries/123.html','https://e-hentai.org/g/123/abc/']:
            self.assertEqual(fetch_comments(url,forbidden)['status'],'unsupported')

    def test_failed_comment_attempt_remains_rate_limited_after_restart(self):
        source=self.store.upsert_source(self.work['id'],{'url':'https://nhentai.net/g/123/'})['sources'][0]
        self.store.begin_comment_fetch(self.work['id'],source['id'])
        restarted=Store(self.store.path)
        with self.assertRaises(ValueError):restarted.begin_comment_fetch(self.work['id'],source['id'])
        self.assertIsNone(restarted.get_work(self.work['id'])['sources'][0]['comments_fetched'])

    def test_invalid_comment_response_preserves_saved_comments(self):
        url='https://nhentai.net/g/123/'
        source=self.store.upsert_source(self.work['id'],{'url':url,'comments':[{'id':'1','text':'keep'}]})['sources'][0]
        with self.assertRaises(ValueError):
            result=fetch_comments(url,lambda endpoint:{'challenge':'login required'})
            self.store.apply_comments(self.work['id'],source['id'],result)
        self.assertEqual(self.store.get_work(self.work['id'])['sources'][0]['comments'][0]['text'],'keep')

    def test_source_numbers_are_namespaced(self):
        self.store.upsert_source(self.work['id'],{'url':'https://e-hentai.org/g/123/abc/'})
        self.store.upsert_source(self.work['id'],{'url':'https://hitomi.la/galleries/123.html'})
        self.assertEqual(len(self.store.get_work(self.work['id'])['sources']),2)

    def test_conflicting_sources_do_not_merge_books(self):
        self.store.upsert_source(self.work['id'],{'url':'https://hitomi.la/galleries/123.html'})
        other=self.store.create_work('Different edition')
        with self.assertRaises(ValueError):
            self.store.upsert_source(other['id'],{'url':'https://hitomi.la/galleries/123.html'})
        self.assertEqual(len(self.store.get_work(other['id'])['sources']),0)

    def test_tags_comments_preserve_provenance(self):
        url='https://e-hentai.org/g/123/abc/'
        self.store.upsert_source(self.work['id'],{'url':url,'tags':['artist:example'],'comments':[{'text':'saved comment','author':'example'}]})
        work=self.store.upsert_source(self.work['id'],{'url':url,'tags':['language:korean'],'status':'fetched'})
        self.assertEqual(work['sources'][0]['comments'][0]['text'],'saved comment')
        self.assertEqual(work['sources'][0]['tags'],['language:korean'])
        self.assertIsNotNone(work['sources'][0]['fetched'])

    def test_locked_title_survives_synchronization(self):
        work=self.store.create_work('Original','', 'a'*40)
        self.store.update_work(work['id'],{'title':'My title','title_locked':True,'rating':5,'favorite':True})
        self.store.sync_lrr([{'arcid':'a'*40,'title':'Remote title','pagecount':12}])
        result=self.store.get_work(work['id'])
        self.assertEqual(result['title'],'My title');self.assertEqual(result['rating'],5)
        self.assertEqual(result['pages'],12)

    def test_search_and_sort_are_bounded(self):
        self.store.upsert_source(self.work['id'],{'url':'https://hitomi.la/galleries/123.html','tags':['collection:blue']})
        self.assertEqual(self.store.list_works(query='123')['total'],1)
        self.assertEqual(self.store.list_works(query='blue')['total'],1)
        self.assertEqual(self.store.list_works(query="' OR 1=1 --")['total'],0)
        with self.assertRaises(ValueError):self.store.list_works(sort='title;DROP TABLE works')
        with self.assertRaises(ValueError):self.store.list_works(limit=100000)

    def test_complete_report_requires_a_nonempty_output_manifest_summary(self):
        job=self.store.queue('https://hitomi.la/galleries/123.html','pc','command')
        claim=self.store.claim('pc','command')
        with self.assertRaises(ValueError):self.store.report(job['id'],claim['lease'],'complete',result={'files':0})
        self.assertEqual(self.store.job(job['id'])['state'],'running')

    def test_ambiguous_upstream_submission_is_never_blindly_retried(self):
        job=self.store.queue('https://hitomi.la/galleries/123.html','nas','lanraragi')
        claim=self.store.claim('nas','lanraragi')
        self.store.report(job['id'],claim['lease'],'running',result={'submission':'pending'})
        self.store.report(job['id'],claim['lease'],'failed','Synthetic connection lost after POST')
        with self.assertRaises(ValueError):self.store.retry(job['id'])

    def test_worker_claim_is_exclusive_and_targeted(self):
        job=self.store.queue('https://hitomi.la/galleries/123.html','pc','command')
        self.assertIsNone(self.store.claim('nas','command'))
        claim=self.store.claim('pc','command');self.assertEqual(claim['id'],job['id'])
        self.assertIsNone(self.store.claim('pc','command'))
        with self.assertRaises(ValueError):self.store.report(job['id'],'wrong','complete')
        self.store.report(job['id'],claim['lease'],'complete','checked',{'files':2,'bytes':2,'directory':job['id']+'-'+'a'*16})
        with self.assertRaises(ValueError):self.store.report(job['id'],claim['lease'],'failed')

    def test_queue_source_identity_deduplicates_url_variants_but_not_sites(self):
        first=self.store.queue('https://hitomi.la/galleries/123.html','pc','command')
        variant=self.store.queue('https://hitomi.la/reader/123.html','pc','command')
        different=self.store.queue('https://nhentai.net/g/123/','pc','command')
        self.assertEqual(first['id'],variant['id'])
        self.assertNotEqual(first['id'],different['id'])

    def test_retry_cannot_duplicate_another_active_job_for_same_source(self):
        first=self.store.queue('https://hitomi.la/galleries/123.html','pc','command')
        claim=self.store.claim('pc','command')
        self.store.report(first['id'],claim['lease'],'failed')
        self.store.queue('https://hitomi.la/reader/123.html','pc','command')
        with self.assertRaises(ValueError):self.store.retry(first['id'])

    def test_queue_is_idempotent_for_active_jobs(self):
        a=self.store.queue('https://hitomi.la/galleries/123.html','pc','command')
        b=self.store.queue('https://hitomi.la/galleries/123.html','pc','command')
        self.assertEqual(a['id'],b['id'])

    def test_expired_worker_is_blocked_instead_of_duplicate_download(self):
        job=self.store.queue('https://hitomi.la/galleries/123.html','pc','command')
        self.store.claim('pc','command')
        with self.store.db() as db:db.execute('UPDATE jobs SET lease_until=?',(time.time()-1,))
        self.assertIsNone(self.store.claim('pc','command'))
        self.assertEqual(self.store.job(job['id'])['state'],'blocked')

    def test_source_urls_reject_network_escape(self):
        for url in ['http://127.0.0.1/','https://hitomi.la.evil.test/galleries/1.html',
                    'https://user:pass@hitomi.la/galleries/1.html','https://hitomi.la:444/galleries/1.html',
                    'file:///etc/passwd','https://hitomi.la/galleries/1.html?redirect=evil']:
            with self.subTest(url=url),self.assertRaises(ValueError):parse_source(url)

    def test_eh_url_preserves_token(self):
        self.assertEqual(parse_source('https://exhentai.org/g/123/abc123/')['url'],'https://exhentai.org/g/123/abc123/')

    def test_progress_updates_only_explicit_read_event(self):
        work=self.store.create_work('Book',pages=3)
        self.store.get_work(work['id']);self.assertIsNone(self.store.get_work(work['id'])['last_read'])
        self.store.progress(work['id'],2);self.assertEqual(self.store.get_work(work['id'])['progress'],2)
        with self.assertRaises(ValueError):self.store.progress(work['id'],4)

    def test_engine_success_requires_output(self):
        events=[]
        command=[sys.executable,'-c','import sys; sys.exit(0)','{url}','{output}']
        run_job({'id':'b'*32,'url':'https://hitomi.la/galleries/1.html'},command,Path(self.temp.name)/'downloads',lambda *a:events.append(a))
        self.assertEqual(events[-1][0],'blocked')

    def test_engine_download_is_verified_and_keeps_shell_metacharacters_as_data(self):
        events=[]
        command=[sys.executable,'-c',"from pathlib import Path;import sys;Path(sys.argv[2],'01.jpg').write_bytes(b'fixture')",'{url}','{output}']
        run_job({'id':'c'*32,'url':'https://hitomi.la/galleries/1.html'},command,Path(self.temp.name)/'downloads',lambda *a:events.append(a))
        self.assertEqual(events[-1][0],'complete')
        self.assertEqual(events[-1][2]['files'],1)
        self.assertTrue((Path(self.temp.name)/'downloads'/events[-1][2]['directory']/'studio-manifest.json').exists())


    @unittest.skipUnless(os.name=='posix' and Path('/proc').exists(),'POSIX process-group test')
    def test_heartbeat_failure_stops_child_that_ignores_termination(self):
        pidfile=Path(self.temp.name)/'child.pid'
        code="import subprocess,sys,time;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(30)']);Path(sys.argv[3]).write_text(str(p.pid));time.sleep(30)"
        command=[sys.executable,'-c',code,'{url}','{output}',str(pidfile)]
        events=[]
        def report(*event):
            events.append(event)
            if len(events)>1:
                deadline=time.monotonic()+2
                while not pidfile.exists() and time.monotonic()<deadline:time.sleep(0.01)
                raise OSError('Synthetic lost lease heartbeat')
        with self.assertRaises(RuntimeError):
            run_job({'id':'f'*32,'url':'https://hitomi.la/galleries/1.html'},command,Path(self.temp.name)/'downloads',report,heartbeat_interval=0.2)
        pid=int(pidfile.read_text());state=Path(f'/proc/{pid}/stat')
        deadline=time.monotonic()+2
        while state.exists() and state.read_text().split()[2]!='Z' and time.monotonic()<deadline:time.sleep(0.02)
        self.assertTrue(not state.exists() or state.read_text().split()[2]=='Z')

    def test_engine_heartbeat_failure_stops_engine_without_completion(self):
        events=[]
        def report(*event):
            events.append(event)
            if len(events)>1:raise OSError('synthetic heartbeat outage')
        command=[sys.executable,'-c','import time;time.sleep(30)','{url}','{output}']
        started=time.monotonic()
        with self.assertRaises(RuntimeError):
            run_job({'id':'e'*32,'url':'https://hitomi.la/galleries/1.html'},command,Path(self.temp.name)/'downloads',report,heartbeat_interval=0.01)
        self.assertLess(time.monotonic()-started,5)
        self.assertFalse(any(e[0]=='complete' for e in events))

    def test_remote_reconciliation_completes_without_new_submission(self):
        job=self.store.queue('https://hitomi.la/galleries/123.html','nas','lanraragi')
        claim=self.store.claim('nas','lanraragi')
        self.store.report(job['id'],claim['lease'],'blocked',result={'remote_job':'42'})
        with self.assertRaises(ValueError):self.store.reconcile_remote(job['id'],'42','active')
        self.store.reconcile_remote(job['id'],'42','finished')
        self.assertEqual(self.store.job(job['id'])['state'],'complete')
        self.assertIsNone(self.store.claim('nas','lanraragi'))

    def test_upstream_retry_cannot_duplicate_existing_remote_job(self):
        job=self.store.queue('https://hitomi.la/galleries/123.html','nas','lanraragi')
        claim=self.store.claim('nas','lanraragi')
        self.store.report(job['id'],claim['lease'],'failed',result={'remote_job':'42'})
        with self.assertRaises(ValueError):self.store.retry(job['id'])

    def test_retry_uses_new_directory_and_preserves_previous_files(self):
        events=[]
        job={'id':'d'*32,'url':'https://hitomi.la/galleries/1.html'}
        command=[sys.executable,'-c',"from pathlib import Path;import sys;Path(sys.argv[2],'01.jpg').write_bytes(b'fixture')",'{url}','{output}']
        root=Path(self.temp.name)/'downloads'
        run_job(job,command,root,lambda *a:events.append(a))
        first=events[-1][2]['directory']
        run_job(job,command,root,lambda *a:events.append(a))
        self.assertNotEqual(first,events[-1][2]['directory'])
        self.assertEqual((root/first/'01.jpg').read_bytes(),b'fixture')

    def test_expired_upstream_result_survives_heartbeat_and_restart(self):
        job=self.store.queue('https://hitomi.la/galleries/123.html','nas','lanraragi')
        claim=self.store.claim('nas','lanraragi')
        self.store.report(job['id'],claim['lease'],'running',result={'remote_job':'42'})
        self.store.report(job['id'],claim['lease'],'running')
        with self.store.db() as db:db.execute('UPDATE jobs SET lease_until=?',(time.time()-1,))
        restarted=Store(self.store.path)
        public=restarted.public_job(restarted.jobs()[0])
        self.assertEqual(public['state'],'blocked')
        self.assertEqual(json.loads(public['result']),{'remote_job':'42'})
        self.assertNotIn('lease',public)
        with self.assertRaises(ValueError):restarted.report(job['id'],claim['lease'],'complete')


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=temporary_directory();self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{'STUDIO_PASSWORD':'test-password','STUDIO_WORKER_TOKEN':'worker-test-token'})
        self.env.start();self.addCleanup(self.env.stop)
        class FakeLRR:
            def json(self,path,*args):
                if path=='/api/info':return {'version':'test'}
                if path=='/api/archives':return [{'arcid':'a'*40}]
                if path.endswith('/metadata'):return {'arcid':'a'*40,'title':'Fixture book','pagecount':4,'tags':'artist:example'}
                raise ValueError('Unknown fake endpoint')
        self.app=Studio(Store(Path(self.temp.name)/'http.db'),FakeLRR())
        self.server=make_server('127.0.0.1',0,self.app)
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)

    def request(self,path,body=None,auth=True,origin=None):
        headers={}
        if auth:headers['Authorization']='Basic '+base64.b64encode(b'admin:test-password').decode()
        if body is not None:headers['Content-Type']='application/json'
        if origin:headers['Origin']=origin
        req=urllib.request.Request(self.url+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        return urllib.request.urlopen(req,timeout=5)

    def test_authentication_covers_static_and_catalog(self):
        for path in ['/','/unsen','/unsen/','/api/works','/api/export','/api/library/status','/app.js']:
            with self.subTest(path=path),self.assertRaises(urllib.error.HTTPError) as error:self.request(path,auth=False)
            self.assertEqual(error.exception.code,401)

    def test_library_status_handles_no_folders_and_returns_counts_without_private_names(self):
        with self.request('/api/library/status') as response:
            self.assertEqual(json.load(response)['folder_archives'],0)
        with self.app.store.db() as db:
            db.execute("INSERT INTO uploads(sha256,original_name,stored_name,bytes,created) VALUES(?,?,?,?,?)",('b'*64,'Private title.cbz','b'*64+'.cbz',123,1))
            db.execute('CREATE TABLE folder_imports(root TEXT,path TEXT,snapshot TEXT,sha256 TEXT)')
            db.execute('INSERT INTO folder_imports VALUES(?,?,?,?)',('private-root','private-book','signature','b'*64))
        with self.request('/api/library/status') as response:
            result=json.load(response)
        self.assertEqual((result['folder_archives'],result['pending_archives']),(1,1))
        self.assertEqual(result['site_downloads'],'not-verified')
        self.assertNotIn('private',json.dumps(result).lower())

    def test_library_status_counts_catalog_not_old_import_receipts(self):
        store=self.app.store
        for index in range(3):
            store.create_work('Private book',lrr_id=str(index)*40)
        store.create_work('Private metadata')
        with store.db() as db:
            for index in range(2):
                db.execute("INSERT INTO uploads(sha256,original_name,stored_name,bytes,created,lrr_id,state) VALUES(?,?,?,?,?,?,?)",
                    (str(index)*64,'Private file.cbz',str(index)*64+'.cbz',1,1,'0'*40,'indexed'))
        with self.request('/api/library/status') as response:
            result=json.load(response)
        self.assertEqual((result['catalog_works'],result['indexed_archives'],result['uploaded_archives'],result['metadata_only']),(4,3,1,1))
        self.assertEqual(result['folder_archives'],0)
        self.assertEqual(result['folder_registration'],'optional-copy')
        self.assertNotIn('private',json.dumps(result).lower())

    def test_organization_requires_admin_and_checks_candidates_without_linking(self):
        work=self.app.store.create_work('Generated')
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/organization',auth=False)
        self.assertEqual(error.exception.code,401)
        with self.request('/api/organization') as response:self.assertEqual(json.load(response)['total'],1)
        with patch('server.source_candidates',return_value=[{'provider':'hitomi','status':'found'}]) as fetch:
            with self.request('/api/works/'+work['id']+'/matches',{'number':'123456'}) as response:
                self.assertEqual(json.load(response)['items'][0]['status'],'found')
            fetch.assert_called_once_with('123456')
        self.assertEqual(self.app.store.get_work(work['id'])['sources'],[])
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/works/'+work['id']+'/matches',{'number':'123456'})
        self.assertEqual(error.exception.code,400)

    def test_same_origin_required_for_mutations(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/works',{'title':'Example'},origin='https://other.invalid')
        self.assertEqual(error.exception.code,403)

    def test_sync_exercises_real_http_catalog_boundary(self):
        with self.request('/api/sync',{}) as response:self.assertEqual(json.load(response)['synced'],1)
        with self.request('/api/works') as response:
            value=json.load(response);self.assertEqual(value['items'][0]['title'],'Fixture book')

    def test_worker_endpoints_require_worker_token(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/worker/claim',{'target':'pc'})
        self.assertEqual(error.exception.code,403)


    def test_worker_http_claim_engine_and_reports_complete_end_to_end(self):
        with self.request('/api/jobs',{'url':'https://hitomi.la/galleries/123.html','target':'pc','engine':'command'}) as response:
            queued=json.load(response)
        def worker_request(path,body):
            request=urllib.request.Request(self.url+path,data=json.dumps(body).encode(),headers={
                'Authorization':'Bearer worker-test-token','Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=5) as response:return json.load(response)
        claim=worker_request('/api/worker/claim',{'target':'pc'})
        def report(state,message='',result=None):
            return worker_request('/api/worker/'+claim['id']+'/report',{'lease':claim['lease'],'state':state,'message':message,'result':result})
        command=[sys.executable,'-c',"from pathlib import Path;import sys;Path(sys.argv[2],'01.png').write_bytes(b'synthetic')",'{url}','{output}']
        run_job(claim,command,Path(self.temp.name)/'downloads',report)
        job=self.app.store.job(queued['id'])
        self.assertEqual(job['state'],'complete')
        result=json.loads(job['result'])
        manifest=json.loads((Path(self.temp.name)/'downloads'/result['directory']/'studio-manifest.json').read_text())
        self.assertEqual(manifest[0]['bytes'],9)
        self.assertEqual(result['files'],1)

    def test_target_scoped_token_cannot_claim_other_device_jobs(self):
        self.app.store.queue('https://hitomi.la/galleries/123.html','nas','command')
        with patch.dict(os.environ,{'STUDIO_PC_WORKER_TOKEN':'pc-scoped-token'}):
            req=urllib.request.Request(self.url+'/api/worker/claim',data=b'{"target":"nas"}',headers={
                'Authorization':'Bearer pc-scoped-token','Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req,timeout=5)
            self.assertEqual(error.exception.code,403)
        self.assertEqual(self.app.store.jobs()[0]['state'],'queued')

    def test_nas_token_cannot_report_pc_job_even_with_its_lease(self):
        job=self.app.store.queue('https://hitomi.la/galleries/123.html','pc','command')
        claim=self.app.store.claim('pc','command')
        with patch.dict(os.environ,{'STUDIO_NAS_WORKER_TOKEN':'nas-scoped-token'}):
            req=urllib.request.Request(self.url+'/api/worker/'+job['id']+'/report',data=json.dumps({'lease':claim['lease'],'state':'failed'}).encode(),headers={
                'Authorization':'Bearer nas-scoped-token','Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req,timeout=5)
        self.assertEqual(self.app.store.job(job['id'])['state'],'running')

    def test_worker_token_cannot_read_or_mutate_library(self):
        for path,body in [('/',None),('/api/export',None),('/api/library/status',None),('/api/works',{'title':'Unauthorized'}),('/api/sync',{})]:
            headers={'Authorization':'Bearer worker-test-token','Content-Type':'application/json'}
            req=urllib.request.Request(self.url+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
            with self.subTest(path=path),self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req,timeout=5)
            self.assertEqual(error.exception.code,403)

    def test_duplicate_queue_response_never_exposes_running_lease(self):
        data={'url':'https://hitomi.la/galleries/123.html','target':'pc','engine':'command'}
        with self.request('/api/jobs',data):pass
        claim=self.app.store.claim('pc','command')
        with self.request('/api/jobs',data) as response:
            value=json.load(response)
        self.assertEqual(value['id'],claim['id'])
        self.assertNotIn('lease',value)
        self.assertNotIn('lease_until',value)

    def test_nonloopback_development_is_rejected(self):
        with self.assertRaises(ValueError):make_server('0.0.0.0',0,self.app,dev=True)


if __name__=='__main__':unittest.main()
