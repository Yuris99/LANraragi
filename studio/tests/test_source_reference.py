"""Attach source numbers/codes to an existing work without downloading or merging."""
import base64
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


class SourceReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'studio.db')
        self.work=self.store.create_work('Keep original title',artist='Keep artist',lrr_id='a'*40,pages=7,tags=['language:korean'])
        self.store.progress(self.work['id'],3)

    def test_hitomi_number_and_ex_code_attach_to_current_work_without_downloading(self):
        before=self.store.get_work(self.work['id'])
        self.store.link_reference(self.work['id'],'hitomi','123456')
        result=self.store.link_reference(self.work['id'],'ehentai-family','987654/ABCDEF0123')
        self.assertEqual({s['url'] for s in result['sources']},{'https://hitomi.la/galleries/123456.html','https://exhentai.org/g/987654/abcdef0123/'})
        for key in ('id','lrr_id','title','artist','pages','bytes','progress','last_read','tags'):self.assertEqual(result[key],before[key],key)
        self.assertEqual(self.store.jobs(),[]);self.assertEqual(self.store.list_works()['total'],1)
        self.assertEqual(self.store.automatic_status(self.work['id'])['state'],'queued')

    def test_saved_ex_number_reuses_exact_url_and_preserves_fetched_fields(self):
        url='https://exhentai.org/g/123/abcdef0123/'
        self.store.upsert_source(self.work['id'],{'url':url,'tags':['language:korean'],'comments':[{'text':'Keep generated comment'}]})
        result=self.store.link_reference(self.work['id'],'ehentai-family','X123')
        self.assertEqual(len(result['sources']),1);self.assertEqual(result['sources'][0]['url'],url)
        self.assertEqual(result['sources'][0]['tags'],['language:korean']);self.assertEqual(result['sources'][0]['comments'][0]['text'],'Keep generated comment')
        self.assertEqual(self.store.jobs(),[])

    def test_other_work_ownership_and_family_counterpart_cannot_be_silently_moved(self):
        other=self.store.create_work('Other edition',lrr_id='b'*40)
        self.store.upsert_source(other['id'],{'url':'https://hitomi.la/galleries/123.html'})
        self.store.upsert_source(other['id'],{'url':'https://e-hentai.org/g/456/abcdef0123/'})
        for provider,reference in [('hitomi','123'),('ehentai-family','456/abcdef0123')]:
            with self.subTest(reference=reference),self.assertRaisesRegex(ValueError,'다른 작품'):self.store.link_reference(self.work['id'],provider,reference)
        self.assertEqual(self.store.get_work(self.work['id'])['sources'],[]);self.assertEqual(len(self.store.get_work(other['id'])['sources']),2)
        self.assertEqual(self.store.list_works()['total'],2)

    def test_missing_ex_token_bad_provider_and_path_injection_do_not_change_work(self):
        for provider,reference in [('ehentai-family','987654'),('hitomi','987654/abcdef0123'),('exhentai','E123/abcdef0123'),('unknown','123'),('hitomi','https://127.0.0.1/'),('hitomi','123;pwd')]:
            with self.subTest(reference=reference),self.assertRaises(ValueError):self.store.link_reference(self.work['id'],provider,reference)
        with self.assertRaises(ValueError):self.store.link_reference(self.work['id'],'hitomi','123',{'url':'https://example.com/'})
        self.assertEqual(self.store.get_work(self.work['id'])['sources'],[]);self.assertEqual(self.store.jobs(),[])

    def test_http_admin_origin_and_fields_are_validated(self):
        with patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-reference-link','STUDIO_PC_WORKER_TOKEN':'generated-worker'}):
            app=Studio(self.store,None);server=make_server('127.0.0.1',0,app);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)+'/api/works/'+self.work['id']+'/sources/reference'
            auth='Basic '+base64.b64encode(b'admin:generated-reference-link').decode()
            def call(credential=auth,data=None,origin=None):
                headers={'Authorization':credential,'Content-Type':'application/json'}
                if origin:headers['Origin']=origin
                payload={'provider':'hitomi','reference':'123456'} if data is None else data
                return urllib.request.urlopen(urllib.request.Request(base,data=json.dumps(payload).encode(),headers=headers),timeout=5)
            try:
                for credential,code in [('',401),('Bearer generated-worker',403)]:
                    with self.assertRaises(urllib.error.HTTPError) as error:call(credential)
                    self.assertEqual(error.exception.code,code)
                with self.assertRaises(urllib.error.HTTPError) as error:call(origin='https://example.invalid')
                self.assertEqual(error.exception.code,403)
                with self.assertRaises(urllib.error.HTTPError) as error:call(data={'provider':'hitomi','reference':'123456','target':'nas'})
                self.assertEqual(error.exception.code,400)
                with call() as response:result=json.load(response)
                self.assertEqual(result['id'],self.work['id']);self.assertEqual(result['sources'][0]['external_id'],'123456')
                self.assertEqual(self.store.jobs(),[])
            finally:server.shutdown();server.server_close();thread.join()

    def test_new_ex_number_uses_one_exact_same_host_lookup_without_saving_or_downloading(self):
        app=Studio(self.store,None);calls=[]
        def fetch(url):
            calls.append(url)
            return '<a href="/g/987654/abcdef0123/">Exact</a><a href="https://e-hentai.org/g/987654/aaaaaaaaaa/">Wrong host</a><a href="/g/999999/aaaaaaaaaa/">Wrong number</a>'
        app.source_transport=lambda:(fetch,None,{})
        result=app.resolve_source_reference('ehentai-family','987654')
        self.assertEqual(result['url'],'https://exhentai.org/g/987654/abcdef0123/')
        self.assertEqual(result['origin'],'number-search')
        self.assertEqual(calls,['https://exhentai.org/?f_search=gid%3A987654'])
        self.assertEqual(self.store.get_work(self.work['id'])['sources'],[]);self.assertEqual(self.store.jobs(),[])

    def test_explicit_ex_prefix_can_lookup_same_host_when_only_eh_url_was_saved(self):
        self.store.upsert_source(self.work['id'],{'url':'https://e-hentai.org/g/987654/abcdef0123/'})
        app=Studio(self.store,None);calls=[]
        def fetch(url):calls.append(url);return '<a href="https://exhentai.org/g/987654/abcdef0123/">Exact</a>'
        app.source_transport=lambda:(fetch,None,{})
        result=app.resolve_source_reference('ehentai-family','X987654')
        self.assertEqual(calls,['https://exhentai.org/?f_search=gid%3A987654']);self.assertEqual(result['provider'],'exhentai')

    def test_denied_lookup_does_not_retry_other_hosts_or_attach_an_unverified_source(self):
        app=Studio(self.store,None);calls=[]
        def fetch(url):calls.append(url);raise urllib.error.HTTPError(url,403,'Generated denial',{},None)
        app.source_transport=lambda:(fetch,None,{})
        with self.assertRaisesRegex(ValueError,'접근'):app.resolve_source_reference('ehentai-family','987654')
        self.assertEqual(calls,['https://exhentai.org/?f_search=gid%3A987654'])
        self.assertEqual(self.store.get_work(self.work['id'])['sources'],[])

    def test_ambiguous_wrong_number_and_challenge_search_results_are_rejected(self):
        for html in ['<a href="/g/987654/abcdef0123/">A</a><a href="/g/987654/aaaaaaaaaa/">B</a>',
                     '<a href="/g/999999/abcdef0123/">Other</a>','<title>Just a moment</title>','x'*(2*1024*1024+1)]:
            app=Studio(self.store,None);app.source_transport=lambda:(lambda url:html,None,{})
            with self.subTest(length=len(html)),self.assertRaises(ValueError):app.resolve_source_reference('ehentai-family','987654')
        self.assertEqual(self.store.jobs(),[])

    def test_explicit_eh_prefix_and_saved_numbers_keep_their_original_origin(self):
        app=Studio(self.store,None);calls=[]
        def fetch(url):calls.append(url);return '<a href="/g/987654/abcdef0123/">Exact</a>'
        app.source_transport=lambda:(fetch,None,{})
        result=app.resolve_source_reference('ehentai-family','E987654')
        self.assertEqual(result['provider'],'ehentai');self.assertEqual(calls,['https://e-hentai.org/?f_search=gid%3A987654'])
        self.store.upsert_source(self.work['id'],{'url':result['url']})
        self.assertEqual(app.resolve_source_reference('ehentai-family','E987654')['origin'],'saved')
        self.assertEqual(len(calls),1)

    def test_real_http_new_ex_number_link_and_download_use_the_resolved_url(self):
        with patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-ex-reference'}):
            app=Studio(self.store,None);calls=[]
            def fetch(url):
                calls.append(url);gid=url.rsplit('gid%3A',1)[1]
                return '<a href="https://exhentai.org/g/'+gid+'/abcdef0123/">Exact</a>'
            app.source_transport=lambda:(fetch,None,{})
            app.download_status=lambda **kwargs:{'exhentai_workers':{'nas':True}}
            server=make_server('127.0.0.1',0,app);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port);auth='Basic '+base64.b64encode(b'admin:generated-ex-reference').decode()
            def call(path,data):
                req=urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Authorization':auth,'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
            try:
                payload={'provider':'ehentai-family','reference':'987654'}
                resolved=call('/api/source-references/resolve',payload)
                self.assertEqual(resolved['origin'],'number-search');self.assertEqual(self.store.get_work(self.work['id'])['sources'],[])
                work=call('/api/works/'+self.work['id']+'/sources/reference',payload)
                self.assertEqual(work['sources'][0]['url'],resolved['url']);self.assertEqual(self.store.jobs(),[])
                queued=call('/api/downloads',{**payload,'target':'nas','engine':'command'})
                self.assertEqual(queued,{'state':'available','work_id':self.work['id']})
                queued=call('/api/downloads',{**payload,'reference':'987655','target':'nas','engine':'command'})
                self.assertEqual(queued['job']['url'],'https://exhentai.org/g/987655/abcdef0123/');self.assertEqual(len(calls),3)
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
