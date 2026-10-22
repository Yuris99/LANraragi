"""Automatic registration-to-three-sites tests use generated metadata only."""
import io
import json
from email.message import Message
from pathlib import Path
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import threading
import base64
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from auto_sources import AutoLinker,LeaseLost
from store import Store
from metadata import parse_html,parse_hitomi_json,counterpart_candidates
from sources import parse_source
from site_sessions import CookieVault,source_document
from backup import copy_database
from test_metadata import E,H,eh_html,hitomi_js

X='https://exhentai.org/g/765432/ghijkl/'


def ex_html():return eh_html().replace('987654','765432').replace('abcdef','ghijkl')


def generated_fetch(url):
    if 'galleries/' in url and url.endswith('.js'):
        return hitomi_js().replace('123456',url.rsplit('/',1)[-1][:-3])
    if url.startswith('https://e-hentai.org/?'):return '<a href="'+E+'">generated</a>'
    if url.startswith('https://exhentai.org/?'):return '<a href="'+X+'">generated</a>'
    if url==E:return eh_html()
    if url==X:return ex_html()
    raise AssertionError('Unexpected generated request')


def generated_index(artist,offset=None):return {'ids':['123456'],'complete':True}


class AutoSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'catalog.db';self.store=Store(self.path)
        self.work=self.store.create_work('Keep title','Keep artist')

    def linker(self,fetch=generated_fetch,index=generated_index,access=None):
        return AutoLinker(self.store,lambda:(fetch,index,access or {}))

    def seed_h(self,work=None,number='123456'):
        work=work or self.work
        return self.store.import_metadata(work['id'],parse_hitomi_json(H.replace('123456',number),hitomi_js().replace('123456',number)))

    def test_registration_alone_runs_both_other_sites_without_a_button(self):
        self.store.upsert_source(self.work['id'],{'url':H})
        self.assertEqual(self.store.automatic_status(self.work['id'])['state'],'queued')
        self.assertTrue(self.linker().run_one())
        work=self.store.get_work(self.work['id'])
        self.assertEqual({s['provider'] for s in work['sources']},{'ehentai','exhentai','hitomi'})
        self.assertEqual((work['title'],work['artist']),('Keep title','Keep artist'))
        self.assertEqual(self.store.automatic_status(work['id'])['state'],'complete')
        self.assertFalse(self.linker().run_one())

    def test_existing_linked_urls_also_get_their_own_metadata_and_comments(self):
        self.store.upsert_source(self.work['id'],{'url':H})
        self.store.upsert_source(self.work['id'],{'url':E})
        self.linker().run_one()
        sources=self.store.get_work(self.work['id'])['sources']
        self.assertEqual(len(sources),3)
        self.assertTrue(all(s['metadata'] for s in sources))
        self.assertEqual(next(s for s in sources if s['provider']=='ehentai')['comments'][0]['text'],'A & B')

    def test_different_language_is_reviewed_without_automatic_source_attachment(self):
        self.seed_h()
        def translated(url):return generated_fetch(url).replace('ta_language:korean','ta_language:english')
        self.linker(fetch=translated,access={'exhentai':'session_required'}).run_one()
        self.assertEqual(len(self.store.get_work(self.work['id'])['sources']),1)
        result=self.store.automatic_status(self.work['id'])['result']
        e=next(s for s in result['sites'] if s['provider']=='ehentai')
        self.assertEqual(e['status'],'review')
        self.assertFalse(e['items'][0]['comparison']['language_match'])

    def test_eh_or_ex_registration_can_discover_hitomi_and_the_other_host(self):
        for url,html in [(E,eh_html()),(X,ex_html())]:
            with tempfile.TemporaryDirectory() as directory:
                store=Store(Path(directory)/'catalog.db');work=store.create_work('Generated')
                store.import_metadata(work['id'],parse_html(url,html))
                AutoLinker(store,lambda:(generated_fetch,generated_index,{})).run_one()
                self.assertEqual({s['provider'] for s in store.get_work(work['id'])['sources']},{'ehentai','exhentai','hitomi'})

    def test_legacy_ex_migration_preserves_saved_url_metadata_and_old_alias(self):
        self.store.import_metadata(self.work['id'],parse_html(X,ex_html()))
        with self.store.db() as db:
            db.execute("UPDATE sources SET provider='ehentai',metadata=json_set(metadata,'$.provider','ehentai')")
        reopened=Store(self.path)
        self.assertEqual(reopened.get_work(self.work['id'])['sources'][0]['provider'],'exhentai')
        self.assertEqual(reopened.resolve_short_id('E765432')['id'],self.work['id'])
        self.assertEqual(reopened.resolve_short_id('X765432')['id'],self.work['id'])
        other=reopened.create_work('Distinct host')
        reopened.upsert_source(other['id'],{'url':'https://e-hentai.org/g/765432/another/'})
        self.assertEqual(reopened.resolve_short_id('E765432')['id'],other['id'])
        self.assertEqual(reopened.resolve_short_id('X765432')['id'],self.work['id'])

    def test_active_epoch_change_and_expired_lease_cannot_attach_stale_result(self):
        self.seed_h();job=self.store.claim_automatic()
        self.store.retry_automatic(self.work['id'])
        with self.assertRaises(LeaseLost):self.store.import_metadata(self.work['id'],parse_html(E,eh_html()),schedule=False,lease_guard=job)
        self.store.finish_automatic(job,{'stale':True},'complete')
        self.assertEqual(self.store.automatic_status(self.work['id'])['state'],'queued')
        self.assertEqual(self.store.automatic_status(self.work['id'])['result'],{})
        old=self.store.claim_automatic()
        with self.store.db() as db:db.execute('UPDATE source_link_jobs SET lease_until=0')
        new=self.store.claim_automatic();self.assertNotEqual(old['lease'],new['lease'])
        with self.assertRaises(LeaseLost):self.store.import_metadata(self.work['id'],parse_html(E,eh_html()),schedule=False,lease_guard=old)
        self.assertEqual(len(self.store.get_work(self.work['id'])['sources']),1)

    def test_pause_prevents_claim_and_inflight_commit(self):
        self.seed_h();job=self.store.claim_automatic()
        self.store.set_automatic_enabled(False)
        self.assertIsNone(self.store.claim_automatic())
        with self.assertRaises(LeaseLost):self.store.import_metadata(self.work['id'],parse_html(E,eh_html()),schedule=False,lease_guard=job)

    def test_global_access_circuit_avoids_repeating_denied_site_for_every_book(self):
        self.seed_h();other=self.store.create_work('Other');self.seed_h(other,'123457');calls=[]
        def denied(url):calls.append(url);raise urllib.error.HTTPError(url,403,'Denied',{},None)
        linker=self.linker(fetch=denied)
        linker.run_one();linker.run_one()
        self.assertEqual(len(calls),2)  # One denied request per distinct target.
        self.assertEqual(self.store.automatic_status(other['id'])['state'],'waiting')

    def test_scan_resumes_after_restart_and_waits_for_ambiguity_check(self):
        self.store.import_metadata(self.work['id'],parse_html(E,eh_html()))
        positions=[]
        def index(artist,offset=None):
            positions.append(offset)
            return {'ids':['123456' if offset==0 else '223456'],'complete':offset==8}
        self.linker(index=index,access={'exhentai':'session_required'}).run_one()
        self.assertEqual(self.store.automatic_status(self.work['id'])['state'],'scanning')
        self.assertEqual(len(self.store.get_work(self.work['id'])['sources']),1)
        self.store=Store(self.path)
        with self.store.db() as db:db.execute('UPDATE source_link_jobs SET next_at=0')
        self.linker(index=index,access={'exhentai':'session_required'}).run_one()
        self.assertEqual(positions,[0,8])
        status=self.store.automatic_status(self.work['id'])
        h=next(s for s in status['result']['sites'] if s['provider']=='hitomi')
        self.assertTrue(h['finished']);self.assertEqual(len(h['items']),2)
        self.assertEqual(h['status'],'review')
        self.assertEqual(len(self.store.get_work(self.work['id'])['sources']),1)

    def test_restore_disables_replay_and_session_change_wakes_blocked_jobs(self):
        self.seed_h();job=self.store.claim_automatic()
        backup=Path(self.temp.name)/'restored.db';copy_database(self.path,backup,restore=True)
        restored=Store(backup)
        self.assertFalse(restored.automatic_enabled())
        self.assertEqual(restored.automatic_status(self.work['id'])['state'],'blocked')
        self.assertIsNone(restored.claim_automatic())
        restored.automatic_session_changed('new-generated-session')
        self.assertIsNone(restored.claim_automatic())
        restored.set_automatic_enabled(True);self.assertIsNotNone(restored.claim_automatic())

    def test_eh_search_progress_moves_through_all_result_batches_then_pages(self):
        calls=[]
        def fetch(url):
            calls.append(url)
            if '?f_search=' in url:
                return ''.join('<a href="https://e-hentai.org/g/'+str(987654+n)+'/abcdef/">result</a>' for n in range(6))+'<a href="/?f_search=A%20Garden&amp;page=1">next</a>'
            number=url.split('/g/')[1].split('/')[0]
            return eh_html().replace('987654',number)
        meta=parse_hitomi_json(H,hitomi_js())
        one=counterpart_candidates(meta,fetch,target='ehentai',cursor={'offset':0})
        self.assertEqual(one['next_cursor'],{'page':0,'offset':5})
        self.assertEqual(one['status'],'scanning')
        two=counterpart_candidates(meta,fetch,target='ehentai',cursor=one['next_cursor'])
        self.assertEqual(len(two['items']),1)
        self.assertEqual(two['next_cursor'],{'page':1,'offset':0})


class DocumentRPCTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.vault=CookieVault(Path(self.temp.name)/'sessions')

    def test_ex_requires_own_session_without_anonymous_or_other_host_fallback(self):
        with patch('urllib.request.build_opener',side_effect=AssertionError('no network')):
            self.assertEqual(source_document(self.vault,X)['status'],'session_required')
            for url in ['https://127.0.0.1/','https://exhentai.org/s/abc/123-1','https://exhentai.org/g/1/a/?x=1','https://exhentai.org:443/g/1/a/','https://ltn.gold-usergeneratedcontent.net/gg.js']:
                with self.subTest(url=url),self.assertRaises(ValueError):source_document(self.vault,url)

    def test_only_account_cookies_are_used_and_response_contains_no_credentials(self):
        self.vault.save('exhentai',[dict(domain='.exhentai.org',path='/',name=name,value='generated-secret',secure=True,expires=-1)
            for name in ('igneous','cf_clearance')])
        headers=Message();headers['Content-Type']='text/html'
        class Response(io.BytesIO):
            status=200
        response=Response(b'<h1>generated metadata</h1>');response.headers=headers
        class Opener:
            def open(self,request,timeout):
                self.url=request.full_url;return response
        def opener(*handlers):
            jar=next(h.cookiejar for h in handlers if hasattr(h,'cookiejar'))
            self.assertEqual([c.name for c in jar],['igneous'])
            return Opener()
        with patch('urllib.request.build_opener',side_effect=opener):result=source_document(self.vault,X)
        self.assertEqual(result['status'],'ok')
        self.assertNotIn('generated-secret',json.dumps(result))

    def test_index_range_resumes_exactly_and_rejects_truncated_or_wrong_range(self):
        headers=Message();headers['Content-Type']='application/octet-stream';headers['Content-Range']='bytes 32-35/36'
        class Response(io.BytesIO):status=206
        def response():
            value=Response((123456).to_bytes(4,'big'));value.headers=headers;return value
        class Opener:
            def open(self,request,timeout):
                if request.get_header('Range')!='bytes=32-63':raise AssertionError('wrong range')
                return response()
        with patch('urllib.request.build_opener',return_value=Opener()):
            value=source_document(self.vault,'https://ltn.gold-usergeneratedcontent.net/artist/fixture-all.nozomi',8)
            self.assertTrue(value['complete'])
            self.assertEqual(int.from_bytes(base64.b64decode(value['index']),'big'),123456)
            headers.replace_header('Content-Range','bytes 32-63/64')
            self.assertEqual(source_document(self.vault,'https://ltn.gold-usergeneratedcontent.net/artist/fixture-all.nozomi',8)['status'],'invalid_response')

    def test_authenticated_rpc_keeps_cookie_access_internal_and_validates_routes(self):
        from login_service import BrowserActor,make_login_server
        vault=self.vault
        class Browser:
            def __init__(self):self.vault=vault
            def call(self,data):return {'configured':True}
            def expire(self):pass
            def close(self):pass
        actor=BrowserActor(vault,browser=Browser());token='generated-service-key-'+'x'*32
        server=make_login_server('127.0.0.1',0,actor,token)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def post(data,key=token):
            request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/rpc',
                data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
            with urllib.request.urlopen(request) as response:return json.load(response)
        try:
            value=post({'op':'source-document','url':X})
            self.assertEqual(value,{'status':'session_required'})
            with self.assertRaises(urllib.error.HTTPError) as error:post({'op':'source-document','url':X},'wrong')
            self.assertEqual(error.exception.code,401)
            with self.assertRaises(urllib.error.HTTPError) as error:post({'op':'source-document','url':'https://127.0.0.1/'})
            self.assertEqual(error.exception.code,400)
        finally:server.shutdown();server.server_close();thread.join();actor.close()
