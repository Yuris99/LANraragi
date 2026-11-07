"""Reference resolution is local, source-scoped, and never guesses gallery tokens."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import Store
from server import Studio,make_server


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'studio.db')

    def test_new_eh_number_requires_full_url_without_any_queue_or_library_change(self):
        with self.assertRaisesRegex(ValueError,'전체 작품 URL'):
            self.store.request_download('ehentai','123','nas','lanraragi')
        self.assertEqual(self.store.jobs(),[]);self.assertEqual(self.store.list_works()['total'],0)

    def test_saved_ex_number_keeps_host_token_and_separate_provider(self):
        work=self.store.create_work('Synthetic saved source')
        url='https://exhentai.org/g/123/abcdef/'
        self.store.upsert_source(work['id'],{'url':url})
        result=self.store.resolve_reference('exhentai','000123')
        self.assertEqual(result['url'],url);self.assertEqual(result['origin'],'saved')
        self.assertEqual(result['work_id'],work['id'])
        self.assertEqual(result['provider'],'exhentai')
        self.assertEqual(self.store.resolve_reference('exhentai','X123')['url'],url)
        with self.assertRaises(ValueError):self.store.resolve_reference('ehentai','000123')
        with self.assertRaises(ValueError):self.store.resolve_reference('ehentai','X123')
        queued=self.store.request_download('exhentai','X123','nas','command')
        self.assertEqual(queued['job']['url'],url)
        with self.assertRaisesRegex(ValueError,'외부 다운로드'):self.store.request_download('exhentai','X123','nas','lanraragi')

    def test_existing_ex_file_opens_without_new_download(self):
        work=self.store.create_work('Generated EX',lrr_id='a'*40)
        self.store.upsert_source(work['id'],{'url':'https://exhentai.org/g/123/abcdef/'})
        result=self.store.request_download('exhentai','X123','nas','command')
        self.assertEqual(result,{'state':'available','work_id':work['id']})
        self.assertEqual(self.store.jobs(),[])

    def test_ex_worker_capability_requires_current_code_and_preserves_heartbeat(self):
        app=Studio(self.store,None)
        runtime={'adapter':'same-source-1','gallery_engine_sha256':hashlib.sha256((Path(__file__).resolve().parents[1]/'gallery_engine.py').read_bytes()).hexdigest(),'worker_sha256':'a'*64,'gallery_dl_version':'1.32.16','sessions_available':True}
        self.assertFalse(app.download_status()['exhentai_workers']['nas'])
        self.store.worker_seen('nas',runtime)
        self.assertTrue(app.download_status()['exhentai_workers']['nas'])
        self.store.worker_seen('nas')
        self.assertTrue(app.download_status()['exhentai_workers']['nas'])
        with patch('store.time.time',return_value=__import__('time').time()+61):
            self.store.worker_seen('nas')
            self.assertFalse(app.download_status()['exhentai_workers']['nas'])
        self.store.worker_seen('nas',runtime)
        self.store.worker_seen('nas',reset_runtime=True)
        self.assertFalse(app.download_status()['exhentai_workers']['nas'])
        with self.assertRaises(ValueError):self.store.worker_seen('nas',{**runtime,'cookie':'do not accept'})

    def test_legacy_worker_cannot_claim_ex_job(self):
        ex=self.store.queue('https://exhentai.org/g/123/0123456789/','nas','command')
        hitomi=self.store.queue('https://hitomi.la/galleries/456.html','nas','command')
        self.assertEqual(self.store.claim('nas','command',exhentai_allowed=False)['id'],hitomi['id'])
        self.assertIsNone(self.store.claim('nas','command',exhentai_allowed=False))
        self.assertEqual(self.store.claim('nas','command',exhentai_allowed=True)['id'],ex['id'])

    def test_verification_jobs_do_not_replace_requested_full_downloads(self):
        url='https://exhentai.org/g/123/0123456789/'
        job=self.store.queue(url,'nas','command',verification=True)
        self.assertTrue(json.loads(job['result'])['verification'])
        with self.assertRaises(ValueError):self.store.queue(url,'nas','command')
        self.assertEqual(len(self.store.jobs()),1)

    def test_same_number_from_other_source_cannot_supply_a_missing_token(self):
        work=self.store.create_work('Synthetic different source')
        self.store.upsert_source(work['id'],{'url':'https://hitomi.la/galleries/123.html'})
        with self.assertRaises(ValueError):self.store.resolve_reference('ehentai','123')

    def test_numeric_sources_are_distinct_and_active_submissions_are_idempotent(self):
        one=self.store.request_download('hitomi','123','pc','command')
        again=self.store.request_download('hitomi','000123','pc','command')
        other=self.store.request_download('ehentai','https://e-hentai.org/g/123/abc/','pc','command')
        self.assertEqual(one['job']['id'],again['job']['id'])
        self.assertNotEqual(one['job']['id'],other['job']['id'])
        self.assertIsNone(one['job']['work_id']);self.assertNotIn('lease',one['job'])
        self.assertEqual(self.store.list_works()['total'],0)

    def test_wrong_provider_url_and_invalid_references_are_rejected(self):
        for provider,value in [('ehentai','https://hitomi.la/galleries/123.html'),('hitomi','https://127.0.0.1/'),
                               ('hitomi','1; echo injected'),('hitomi','0'),('hitomi','１'),
                               ('hitomi','9'*2049),('unknown','123'),('nhentai','123'),('hitomi',None)]:
            with self.subTest(provider=provider,value=value),self.assertRaises(ValueError):
                self.store.resolve_reference(provider,value)
        self.assertEqual(self.store.jobs(),[])

    def test_existing_library_file_is_returned_without_redownloading(self):
        work=self.store.create_work('Already available',lrr_id='a'*40)
        self.store.upsert_source(work['id'],{'url':'https://hitomi.la/galleries/123.html'})
        result=self.store.request_download('hitomi','123','nas','command')
        self.assertEqual(result,{'state':'available','work_id':work['id']})
        self.assertEqual(self.store.jobs(),[])
        with self.assertRaises(ValueError):self.store.request_download('hitomi','123','pc','lanraragi')

    def test_metadata_only_work_is_linked_by_qualified_source_identity(self):
        work=self.store.create_work('Saved metadata')
        self.store.upsert_source(work['id'],{'url':'https://hitomi.la/doujinshi/synthetic-123.html'})
        result=self.store.request_download('hitomi','123','nas','command')
        self.assertEqual(result['job']['work_id'],work['id'])
        self.assertEqual(result['job']['url'],'https://hitomi.la/doujinshi/synthetic-123.html')

    def test_real_http_preview_and_submission_need_admin_not_worker_credentials(self):
        with patch.dict(os.environ,{'STUDIO_PASSWORD':'reference-test','STUDIO_PC_WORKER_TOKEN':'reference-worker'}):
            app=Studio(self.store,None);server=make_server('127.0.0.1',0,app)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                data=json.dumps({'provider':'hitomi','reference':'123','target':'pc','engine':'command'}).encode()
                auth='Basic '+base64.b64encode(b'admin:reference-test').decode()
                def request(path,credential):
                    return urllib.request.urlopen(urllib.request.Request(base+path,data=data,
                        headers={'Content-Type':'application/json','Authorization':credential}),timeout=5)
                with request('/api/downloads/resolve',auth) as response:
                    self.assertEqual(json.load(response)['external_id'],'123')
                self.assertEqual(self.store.jobs(),[])
                with request('/api/downloads',auth) as response:self.assertEqual(json.load(response)['state'],'queued')
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/downloads','Bearer reference-worker')
                self.assertEqual(error.exception.code,403)
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
