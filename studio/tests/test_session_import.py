"""Explicit generated account exports only; no real website or credentials."""
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from site_sessions import CookieVault,source_document,LoginClient
from login_service import LoginBrowser,BrowserActor,make_login_server
from server import Studio,make_server
from store import Store


def exported(domain='.e-hentai.org'):
    return [dict(domain=domain,path='/',name=n,value='generated-'+n,secure=True,httpOnly=True,expires=-1)
            for n in ('ipb_member_id','ipb_pass_hash','cf_clearance','unrelated_preference')]


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.vault=CookieVault(Path(self.temp.name)/'sessions')

    def test_json_and_netscape_restart_filtering_and_private_status(self):
        result=self.vault.import_file('ehentai',json.dumps(exported()))
        self.assertEqual(result['cookie_count'],2)
        self.assertFalse(result['site_verified'])
        restored=CookieVault(self.vault.root)
        self.assertEqual({c.name for c in restored.read('ehentai')},{'ipb_member_id','ipb_pass_hash'})
        self.assertEqual(self.vault.path('ehentai').stat().st_mode&0o777,0o600)
        text='# Netscape HTTP Cookie File\n'+''.join('#HttpOnly_.exhentai.org\tTRUE\t/\tTRUE\t0\t'+c['name']+'\t'+c['value']+'\n' for c in exported())
        self.vault.import_file('exhentai',text)
        self.assertEqual(len(self.vault.read('exhentai')),2)
        self.assertNotIn('generated-',json.dumps(self.vault.status('exhentai')))

    def test_invalid_import_preserves_existing_and_redacts_errors(self):
        self.vault.import_file('ehentai',json.dumps(exported()))
        old=self.vault.path('ehentai').read_bytes()
        cases=['bad generated-secret',json.dumps(exported('.attacker.example')),json.dumps(exported()[:1]),
               json.dumps([dict(c,value='generated-secret\ninvalid') for c in exported()]),
               json.dumps([dict(c,expires=time.time()-10) for c in exported()]),
               'x'*131073,json.dumps([None]),json.dumps([dict(c,value='') for c in exported()])]
        for value in cases:
            with self.subTest(size=len(value)),self.assertRaises(ValueError) as error:self.vault.import_file('ehentai',value)
            self.assertNotIn('generated-secret',str(error.exception))
            self.assertEqual(self.vault.path('ehentai').read_bytes(),old)
        self.assertFalse(list(self.vault.root.glob('.session-*')))
        with self.assertRaises(ValueError):self.vault.import_file('hitomi',json.dumps(exported()))

    def test_diagnostics_separate_saved_anonymous_and_access_failure(self):
        class Response(io.BytesIO):pass
        class Opener:
            def open(self,request,timeout):return Response(b'<html>generated</html>')
        url='https://e-hentai.org/g/123/abc/'
        with patch('urllib.request.build_opener',return_value=Opener()):
            source_document(self.vault,url)
            self.assertEqual(self.vault.status('ehentai')['last_request']['mode'],'anonymous')
            self.vault.import_file('ehentai',json.dumps(exported()))
            self.assertIsNone(self.vault.status('ehentai')['last_request'])
            source_document(self.vault,url)
            self.assertEqual(self.vault.status('ehentai')['last_request']['mode'],'saved_session')
        with patch('urllib.request.build_opener',side_effect=urllib.error.HTTPError(url,403,'secret',{},None)):
            source_document(self.vault,url)
        status=self.vault.status('ehentai')
        self.assertEqual(status['last_request']['status'],'access_required')
        self.assertEqual(status['last_request']['http_status'],403)
        self.assertNotIn('generated-',json.dumps(status));self.assertNotIn(url,json.dumps(status))
        self.vault.forget('ehentai');self.assertIsNone(self.vault.status('ehentai')['last_request'])

    def test_desktop_schema_accepts_import_without_starting_browser(self):
        from login_service import DesktopBrowser
        browser=DesktopBrowser(self.vault)
        with patch.object(browser,'start',side_effect=AssertionError('browser must not start')):
            result=browser.call({'op':'import-session','provider':'ehentai','content':json.dumps(exported())})
        self.assertEqual(result['state'],'saved_unverified')
        with self.assertRaises(ValueError):browser.call({'op':'import-session','provider':'ehentai','content':'[]','url':'https://attacker.example'})


class ImportHTTPTests(unittest.TestCase):
    def test_real_studio_gateway_import_is_admin_only_and_not_exported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);vault=CookieVault(root/'sessions')
            token='generated-service-token-'+'a'*40
            key=root/'key';key.write_text(token);key.chmod(0o600)
            actor=BrowserActor(vault,browser=LoginBrowser(vault))
            gateway=make_login_server('127.0.0.1',0,actor,token)
            gateway_thread=threading.Thread(target=gateway.serve_forever,daemon=True);gateway_thread.start()
            with patch.dict('os.environ',{'STUDIO_PASSWORD':'generated-admin','STUDIO_NAS_WORKER_TOKEN':'generated-worker'}):
                app=Studio(Store(root/'catalog.db'),object(),root/'uploads')
                app.login=LoginClient('http://127.0.0.1:'+str(gateway.server_port),str(key))
                server=make_server('127.0.0.1',0,app)
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                base='http://127.0.0.1:'+str(server.server_port)
                admin='Basic '+base64.b64encode(b'admin:generated-admin').decode()
                content=json.dumps(exported())+' '*20000
                data=json.dumps(dict(op='import-session',provider='ehentai',content=content)).encode()
                def post(auth=admin,origin=base):
                    req=urllib.request.Request(base+'/api/site-connections',data=data,headers={
                        'Authorization':auth,'Origin':origin,'Content-Type':'application/json'})
                    return json.load(urllib.request.urlopen(req))
                try:
                    for auth,origin in [('Bearer generated-worker',base),(admin,'https://attacker.example')]:
                        with self.assertRaises(urllib.error.HTTPError) as error:post(auth,origin)
                        self.assertEqual(error.exception.code,403)
                    result=post();self.assertEqual(result['cookie_count'],2)
                    self.assertNotIn('generated-',json.dumps(result))
                    self.assertNotIn('generated-ipb_',json.dumps(app.store.export()))
                    self.assertEqual({c.name for c in vault.read('ehentai')},{'ipb_member_id','ipb_pass_hash'})
                finally:server.shutdown();server.server_close();thread.join()
            gateway.shutdown();gateway.server_close();gateway_thread.join();actor.close()
