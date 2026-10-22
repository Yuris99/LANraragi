"""Generated sessions only; no real account, cookies, or external requests."""
import base64
import http.cookiejar
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
import urllib.request
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from site_sessions import CookieVault,LoginClient,allowed_domain
from gallery_engine import cookie_snapshot
from login_service import LoginBrowser,LoginFailure,make_login_server
from server import LRR,Studio,make_server
from store import Store
from init_login import initialize


def cookie(domain='.e-hentai.org',value='generated-secret'):
    return {'domain':domain,'name':'fixture_session','value':value,'path':'/',
            'secure':True,'httpOnly':True,'expires':-1}


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.vault=CookieVault(self.root/'sessions')

    def test_scope_private_files_session_cookies_and_restart(self):
        result=self.vault.save('ehentai',[cookie(),cookie('.unrelated.example','never-store')])
        self.assertEqual(result['state'],'saved_unverified');self.assertFalse(result['site_verified'])
        path=self.vault.path('ehentai')
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertNotIn('never-store',path.read_text())
        restored=CookieVault(self.vault.root).read('ehentai')
        self.assertEqual([(c.name,c.value) for c in restored],[('fixture_session','generated-secret')])
        self.assertTrue(restored[0].has_nonstandard_attr('HTTPOnly'))
        self.assertFalse(allowed_domain('ehentai','e-hentai.org.attacker.example'))
        self.assertFalse(allowed_domain('ehentai','exhentai.org'))

    def test_invalid_new_session_keeps_saved_session_and_no_partial_files(self):
        self.vault.save('ehentai',[cookie()]);old=self.vault.path('ehentai').read_bytes()
        for item in [cookie(value='bad\nvalue'),{**cookie(),'expires':float('nan')},cookie('.wrong.example')]:
            with self.assertRaises(ValueError):self.vault.save('ehentai',[item])
            self.assertEqual(self.vault.path('ehentai').read_bytes(),old)
        self.assertFalse(list(self.vault.root.glob('.session-*')))

    def test_expired_and_insecure_sessions_cannot_be_used_as_anonymous(self):
        self.vault.save('ehentai',[{**cookie(),'expires':time.time()+20}])
        with patch('http.cookiejar.time.time',return_value=time.time()+100):
            with self.assertRaises(ValueError):self.vault.read('ehentai')
        self.vault.path('ehentai').chmod(0o644)
        self.assertEqual(self.vault.status('ehentai')['state'],'unavailable')

    def test_symlink_files_and_shared_directories_are_rejected(self):
        target=self.root/'target';target.write_text('untouched')
        self.vault.path('ehentai').symlink_to(target)
        with self.assertRaises(OSError):self.vault.read('ehentai')
        self.vault.root.chmod(0o755)
        with self.assertRaises(ValueError):CookieVault(self.vault.root)
        self.assertEqual(target.read_text(),'untouched')

    def test_engine_uses_private_scoped_snapshot_and_removes_it(self):
        self.vault.save('ehentai',[cookie()]);self.vault.save('nhentai',[cookie('.nhentai.net','different-secret')])
        source=self.vault.path('ehentai').read_bytes()
        with patch.dict(os.environ,{'STUDIO_SESSION_DIR':str(self.vault.root)}):
            with cookie_snapshot('https://e-hentai.org/g/123/abc123/') as path:
                snapshot=Path(path)
                self.assertEqual(snapshot.stat().st_mode&0o777,0o600)
                self.assertIn('generated-secret',snapshot.read_text())
                self.assertNotIn('different-secret',snapshot.read_text())
                snapshot.write_text('engine cannot modify original')
            self.assertFalse(snapshot.exists())
            with cookie_snapshot('https://hitomi.la/galleries/123.html') as absent:self.assertIsNone(absent)
        self.assertEqual(self.vault.path('ehentai').read_bytes(),source)

    def test_forget_only_selected_profile_and_no_sensitive_status(self):
        for p in ('ehentai','nhentai'):self.vault.save(p,[cookie('.e-hentai.org' if p=='ehentai' else '.nhentai.net')])
        self.vault.forget('ehentai')
        self.assertEqual(self.vault.status('ehentai')['state'],'not_saved')
        self.assertNotIn('generated-secret',json.dumps(self.vault.status('nhentai')))
        self.assertEqual(self.vault.status('nhentai')['cookie_count'],1)

    def test_browser_rejects_arbitrary_url_keys_stale_session_and_wrong_domains(self):
        browser=LoginBrowser(self.vault)
        with self.assertRaises(ValueError):browser.call({'op':'start','provider':'ehentai','url':'https://wrong.example/'})
        with self.assertRaises(ValueError):browser.call({'op':'start','provider':'hitomi'})
        with self.assertRaises(ValueError):browser.call({'op':'text','session':'bad','text':'generated'})
        self.assertIsNone(browser.browser)
        class Route:
            request=type('Request',(),{'url':'https://wrong.example/private','is_navigation_request':lambda self:False})()
            def abort(self):self.aborted=True
            def continue_(self):raise AssertionError('Unrelated request escaped')
        route=Route();browser.provider='ehentai';browser.route(route)
        self.assertTrue(route.aborted)

    def test_official_verification_resource_allowed_without_expanding_navigation(self):
        accepted=[];browser=LoginBrowser(self.vault,lambda route:accepted.append(route.request.url))
        browser.provider='ehentai';main=object()
        browser.page=SimpleNamespace(url='https://forums.e-hentai.org/index.php',main_frame=main)
        def request(url,navigate=False,frame=main):
            result=SimpleNamespace(request=SimpleNamespace(url=url,frame=frame,is_navigation_request=lambda:navigate),aborted=False)
            result.abort=lambda:setattr(result,'aborted',True)
            browser.route(result);return result
        self.assertFalse(request('https://challenges.cloudflare.com/turnstile/v0/api.js').aborted)
        self.assertFalse(request('https://challenges.cloudflare.com/widget',True,object()).aborted)
        for url in ('https://challenges.cloudflare.com/widget','https://challenges.cloudflare.com.evil.example/x',
                    'http://challenges.cloudflare.com/x','https://challenges.cloudflare.com:444/x'):
            self.assertTrue(request(url,True).aborted)
        self.assertTrue(browser.blocked_navigation)
        self.assertEqual(len(accepted),2)
        browser.page.url='https://unrelated.example/'
        self.assertTrue(request('https://challenges.cloudflare.com/widget').aborted)

    def test_client_rejects_unsafe_endpoint_and_no_backend_is_honest(self):
        for url in ('file:///etc/passwd','http://user:password@host','http://host/path'):
            with self.assertRaises(ValueError):LoginClient(url=url)
        self.assertFalse(LoginClient(url='',token_file='').call({'op':'status'})['configured'])

    def test_initializer_preserves_database_and_reuses_key_without_rotation(self):
        volumes=self.root/'volumes';volumes.mkdir()
        for name in ('key','sessions'):(volumes/name).mkdir()
        data=self.root/'data';data.mkdir();database=data/'studio.db';database.write_bytes(b'generated existing data')
        initialize(volumes,os.getuid(),os.getgid(),data)
        key=(data/'.site-login-token').read_bytes()
        self.assertEqual((data/'.site-login-token').stat().st_mode&0o777,0o600)
        initialize(volumes,os.getuid(),os.getgid(),data)
        self.assertEqual((data/'.site-login-token').read_bytes(),key)
        self.assertEqual(database.read_bytes(),b'generated existing data')
        self.assertEqual(set(p.name for p in data.iterdir()),{'studio.db','.site-login-token','.site-login.json'})

    def test_unmarked_volume_data_is_rejected_before_any_provisioning(self):
        volumes=self.root/'volumes';volumes.mkdir()
        for name in ('key','sessions'):(volumes/name).mkdir()
        (volumes/'sessions'/'unrelated').write_bytes(b'keep')
        with self.assertRaises(ValueError):initialize(volumes,os.getuid(),os.getgid())
        self.assertEqual(list((volumes/'key').iterdir()),[])


class SessionHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.token='generated-only-service-token-'+'a'*40
        self.key=self.root/'key';self.key.write_text(self.token);self.key.chmod(0o600)
        class Actor:
            def call(self,data):
                if data.get('op')=='status':return {'configured':True,'sites':[],'active':None}
                raise ValueError('generated-secret-must-never-escape')
        gateway=make_login_server('127.0.0.1',0,Actor(),self.token)
        self.gateway=gateway
        thread=threading.Thread(target=gateway.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(gateway.shutdown(),gateway.server_close(),thread.join(timeout=3)))
        self.client=LoginClient('http://127.0.0.1:'+str(gateway.server_port),str(self.key))

    def test_gateway_auth_and_error_redaction(self):
        self.assertTrue(self.client.call({'op':'status'})['configured'])
        with self.assertRaises(ValueError) as error:self.client.call({'op':'text','text':'generated-secret'})
        self.assertNotIn('generated-secret',str(error.exception))
        request=urllib.request.Request(self.client.url+'/rpc',data=b'{"op":"status"}',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        self.assertEqual(error.exception.code,401)

    def test_specific_timeout_and_unknown_error_redaction(self):
        failure=urllib.error.HTTPError('http://generated',503,'unavailable',{},io.BytesIO(b'{"error":"login_site_timeout"}'))
        with patch('urllib.request.OpenerDirector.open',side_effect=failure):
            with self.assertRaisesRegex(ValueError,'시간 제한'):self.client.call({'op':'start','provider':'ehentai'})
        failure=urllib.error.HTTPError('http://generated',503,'secret',{},io.BytesIO(b'{"error":"generated-secret"}'))
        with patch('urllib.request.OpenerDirector.open',side_effect=failure):
            with self.assertRaises(ValueError) as result:self.client.call({'op':'start','provider':'ehentai'})
        self.assertNotIn('generated-secret',str(result.exception))

    def test_gateway_preserves_safe_browser_failure(self):
        class Actor:
            def call(self,data):raise LoginFailure('browser_start_failed')
        gateway=make_login_server('127.0.0.1',0,Actor(),self.token)
        thread=threading.Thread(target=gateway.serve_forever,daemon=True);thread.start()
        try:
            client=LoginClient('http://127.0.0.1:'+str(gateway.server_port),str(self.key))
            with self.assertRaisesRegex(ValueError,'시작하지 못했습니다'):client.call({'op':'start','provider':'ehentai'})
        finally:gateway.shutdown();gateway.server_close();thread.join(timeout=3)

    def test_studio_requires_admin_same_origin_and_never_accepts_worker_for_login(self):
        with patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-admin','STUDIO_NAS_WORKER_TOKEN':'generated-nas'}):
            store=Store(self.root/'catalog.db');app=Studio(store,object(),self.root/'uploads');app.login=self.client
            server=make_server('127.0.0.1',0,app)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                admin='Basic '+base64.b64encode(b'admin:generated-admin').decode()
                for authorization,origin,expected in [('Bearer generated-nas',None,403),(admin,'https://other.example',403)]:
                    headers={'Authorization':authorization,'Content-Type':'application/json'}
                    if origin:headers['Origin']=origin
                    req=urllib.request.Request(base+'/api/site-connections',data=b'{"op":"status"}',headers=headers)
                    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
                    self.assertEqual(error.exception.code,expected)
                req=urllib.request.Request(base+'/api/site-connections',headers={'Authorization':admin})
                self.assertTrue(json.load(urllib.request.urlopen(req))['configured'])
                exported=app.store.export()
                self.assertNotIn(self.token,json.dumps(exported))
            finally:server.shutdown();server.server_close();thread.join(timeout=3)


class DownloadSubmissionTests(unittest.TestCase):
    def test_new_request_cannot_bypass_uncertain_submission_by_switching_engine(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(Path(root)/'catalog.db');url='https://e-hentai.org/g/123/abc123/'
            job=store.queue(url,'nas','lanraragi');claim=store.claim('nas','lanraragi')
            store.report(job['id'],claim['lease'],'failed',result={'submission':'pending'})
            for engine in ('lanraragi','command'):
                with self.assertRaises(ValueError):store.queue(url,'nas',engine)
            self.assertEqual(len(store.jobs()),1)

    def test_index_keeps_existing_metadata_and_requires_exact_file_proof(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(Path(root)/'catalog.db');work=store.create_work('Manual entry','Original artist')
            store.upsert_source(work['id'],{'url':'https://e-hentai.org/g/123/abc123/','comments':[{'id':'1','text':'preserve'}]})
            job=store.queue('https://e-hentai.org/g/123/abc123/','nas','command',work['id']);claim=store.claim('nas','command')
            result={'files':1,'bytes':123,'directory':job['id']+'-'+'a'*16,
                    'archives':[{'file':'ehentai-123.cbz','sha256':'b'*64,'bytes':123}]}
            store.report(job['id'],claim['lease'],'complete',result=result)
            metadata={'arcid':'c'*40,'filename':'ehentai-123','title':'Downloaded title','pagecount':3,'size':123,'tags':''}
            with self.assertRaises(ValueError):store.index_command_archive(job['id'],metadata,'d'*64)
            self.assertIsNone(store.get_work(work['id'])['lrr_id'])
            actual=store.index_command_archive(job['id'],metadata,'b'*64)
            self.assertEqual(actual,work['id'])
            self.assertEqual(store.get_work(actual)['sources'][0]['comments'][0]['text'],'preserve')
            self.assertEqual(store.list_works()['total'],1)
            self.assertTrue(json.loads(store.job(job['id'])['result'])['catalog_indexed'])

    def test_worker_online_status_expires_and_never_claims_site_success(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(Path(root)/'catalog.db')
            self.assertEqual(store.worker_status(),{'nas':False,'pc':False})
            store.worker_seen('nas')
            self.assertEqual(store.worker_status(),{'nas':True,'pc':False})
            with patch('store.time.time',return_value=time.time()+61):self.assertFalse(store.worker_status()['nas'])

    def test_nas_job_submits_url_as_encoded_query_without_form_body(self):
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        requests=[]
        def opening(request,timeout):
            requests.append(request)
            return Response(b'{"success":1,"job":42}')
        url='https://e-hentai.org/g/123/abc123/'
        def opening(request,timeout):
            requests.append(request)
            path=urllib.parse.urlsplit(request.full_url).path
            if path=='/api/plugins/download':return Response(b'[{"url_regex":"^https://e-hentai.org/"}]')
            if path=='/api/download_url':
                # Emulate the real OpenAPI rejection, not a permissive fixture.
                if request.data is not None or request.get_header('Content-type'):
                    raise urllib.error.HTTPError(request.full_url,400,'invalid body',{},None)
                query=urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
                if query!={'url':[url]}:raise ValueError('Missing complete source URL')
                return Response(b'{"success":1,"job":42}')
            if path=='/api/minion/42/detail':return Response(b'{"state":"finished"}')
            if path=='/api/archives':return Response(b'[]')
            raise AssertionError(path)
        class FastStop:
            count=0
            def wait(self,seconds):self.count+=1;return self.count>=3
        with tempfile.TemporaryDirectory() as root:
            store=Store(Path(root)/'catalog.db');job=store.queue(url,'nas','lanraragi')
            app=Studio(store,LRR('http://generated-lrr'),Path(root)/'uploads');app.stop=FastStop()
            with patch('urllib.request.urlopen',side_effect=opening):app.nas_loop()
            self.assertEqual(store.job(job['id'])['state'],'complete')
            self.assertEqual(json.loads(store.job(job['id'])['result'])['remote_job'],'42')
        submissions=[r for r in requests if urllib.parse.urlsplit(r.full_url).path=='/api/download_url']
        self.assertEqual(len(submissions),1)
        self.assertEqual(submissions[0].method,'POST')



if __name__=='__main__':unittest.main()
