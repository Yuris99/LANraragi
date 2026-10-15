import base64
import json
import os
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

    def test_worker_claim_is_exclusive_and_targeted(self):
        job=self.store.queue('https://hitomi.la/galleries/123.html','pc','command')
        self.assertIsNone(self.store.claim('nas','command'))
        claim=self.store.claim('pc','command');self.assertEqual(claim['id'],job['id'])
        self.assertIsNone(self.store.claim('pc','command'))
        with self.assertRaises(ValueError):self.store.report(job['id'],'wrong','complete')
        self.store.report(job['id'],claim['lease'],'complete','checked',{'files':2})
        with self.assertRaises(ValueError):self.store.report(job['id'],claim['lease'],'failed')

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
        self.assertTrue((Path(self.temp.name)/'downloads'/('c'*32)/'studio-manifest.json').exists())


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=temporary_directory();self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{'STUDIO_PASSWORD':'test-password','STUDIO_WORKER_TOKEN':'worker-test-token'})
        self.env.start();self.addCleanup(self.env.stop)
        class FakeLRR:
            def json(self,path,*args):
                if path=='/api/info':return {'version':'test'}
                if path=='/api/archives':return ['a'*40]
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
        for path in ['/','/api/works','/api/export','/app.js']:
            with self.subTest(path=path),self.assertRaises(urllib.error.HTTPError) as error:self.request(path,auth=False)
            self.assertEqual(error.exception.code,401)

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

    def test_nonloopback_development_is_rejected(self):
        with self.assertRaises(ValueError):make_server('0.0.0.0',0,self.app,dev=True)


if __name__=='__main__':unittest.main()
