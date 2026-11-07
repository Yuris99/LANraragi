"""Retired provider is hidden and inactive; historical catalog data survives."""
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
from server import Studio,make_server
from store import Store
from connectors import source_candidates


class RemovedProviderTests(unittest.TestCase):
    def test_api_refuses_new_actions_and_preserves_legacy_data(self):
        class Login:
            def call(self,data):
                if data!={'op':'status'}:raise AssertionError('Unexpected login operation')
                return {'sites':[{'provider':p} for p in ['ehentai','exhentai','nhentai']],
                        'active':{'provider':'nhentai','session':'generated-legacy'}}
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-retired'}):
            store=Store(Path(directory)/'studio.db');store.set_automatic_enabled(False)
            work=store.create_work('Generated legacy record')
            value=store.upsert_source(work['id'],{'url':'https://nhentai.net/g/123/','tags':['original'],
                'comments':[{'id':'1','text':'Generated preserved comment'}]})
            source=value['sources'][0]
            snapshot=json.dumps(store.get_work(work['id']),sort_keys=True)
            app=Studio(store,None);app.login=Login()
            server=make_server('127.0.0.1',0,app)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                auth='Basic '+base64.b64encode(b'admin:generated-retired').decode()
                def request(path,data=None):
                    return urllib.request.urlopen(urllib.request.Request(base+path,
                        data=None if data is None else json.dumps(data).encode(),
                        headers={'Authorization':auth,'Content-Type':'application/json'}),timeout=5)
                with request('/api/site-connections') as response:status=json.load(response)
                self.assertEqual([s['provider'] for s in status['sites']],['ehentai','exhentai'])
                self.assertIsNone(status['active'])
                with request('/api/site-connections',{'op':'status'}) as response:
                    self.assertEqual(json.load(response),status)
                for path,data in [
                    ('/api/works/'+work['id']+'/sources',{'url':'https://nhentai.net/g/456/'}),
                    ('/api/downloads/resolve',{'provider':'nhentai','reference':'123'}),
                    ('/api/jobs',{'url':source['url'],'target':'pc','engine':'command'}),
                    ('/api/site-connections',{'op':'start','provider':'nhentai'}),
                    ('/api/site-connections',{'op':'import-session','provider':'nhentai'}),
                    ('/api/works/'+work['id']+'/sources/'+source['id']+'/fetch',{}),
                    ('/api/works/'+work['id']+'/sources/'+source['id']+'/comments/fetch',{}),
                ]:
                    with self.subTest(path=path),self.assertRaises(urllib.error.HTTPError) as error:request(path,data)
                    self.assertEqual(error.exception.code,400)
                self.assertEqual(store.jobs(),[])
                self.assertEqual(json.dumps(store.get_work(work['id']),sort_keys=True),snapshot)
            finally:server.shutdown();server.server_close();thread.join()

    def test_number_lookup_never_requests_retired_host(self):
        requests=[]
        def fetch(url,*args):
            requests.append(url)
            if 'nhentai.net' in url:raise AssertionError('Retired provider request')
            raise OSError('Generated offline')
        self.assertEqual([r['provider'] for r in source_candidates('123',fetch)],['ehentai','hitomi'])
        self.assertEqual(len(requests),2)


if __name__=='__main__':unittest.main()
