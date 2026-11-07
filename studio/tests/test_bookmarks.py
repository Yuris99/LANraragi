"""Bookmark persistence and HTTP authorization using generated metadata only."""
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


class BookmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'studio.db';self.store=Store(self.path)

    def test_saved_tags_and_artists_persist_without_changing_original_metadata(self):
        work=self.store.create_work('Generated original',artist='Generated artist',tags=['language:korean'])
        original=self.store.get_work(work['id'])
        for kind,value in [('tag','language:korean'),('artist','Generated artist')]:
            self.store.set_bookmark(kind,value,True)
            self.store.set_bookmark(kind,value,True)
        expected=[{'kind':'tag','value':'language:korean'},{'kind':'artist','value':'Generated artist'}]
        self.assertEqual(Store(self.path).bookmarks(),expected)
        self.assertEqual(self.store.export()['bookmarks'],expected)
        self.assertEqual(self.store.get_work(work['id']),original)
        self.store.set_bookmark('tag','language:korean',False)
        self.store.set_bookmark('tag','language:korean',False)
        self.assertEqual(self.store.bookmarks(),expected[1:])

    def test_validation_and_limit_leave_saved_values_unchanged(self):
        for kind,value,saved in [('source','x',True),('tag','date_added:123',True),('tag','timestamp',True),
                                 ('tag','',True),('artist','x\ny',True),('artist','x'*301,True),
                                 ('tag',None,True),('tag','language:korean','true')]:
            with self.subTest(value=value),self.assertRaises(ValueError):self.store.set_bookmark(kind,value,saved)
        self.assertEqual(self.store.bookmarks(),[])
        expected=[{'kind':'artist','value':f'Generated {n}'} for n in range(500)]
        with self.store.db() as db:db.execute("INSERT INTO settings(key,value) VALUES('bookmarks',?)",(json.dumps(expected),))
        self.assertEqual(self.store.set_bookmark('artist','Generated 0',True),expected)
        with self.assertRaises(ValueError):self.store.set_bookmark('artist','Generated extra',True)
        self.assertEqual(self.store.bookmarks(),expected)

    def test_http_requires_admin_and_same_origin_and_rejects_extra_fields(self):
        with patch.dict(os.environ,{'STUDIO_PASSWORD':'bookmark-test','STUDIO_PC_WORKER_TOKEN':'bookmark-worker'}):
            app=Studio(self.store,None);server=make_server('127.0.0.1',0,app)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                auth='Basic '+base64.b64encode(b'admin:bookmark-test').decode()
                def request(credential=auth,data=None,origin=None):
                    headers={'Content-Type':'application/json','Authorization':credential}
                    if origin:headers['Origin']=origin
                    req=urllib.request.Request(base+'/api/bookmarks',data=None if data is None else json.dumps(data).encode(),headers=headers)
                    return urllib.request.urlopen(req,timeout=5)
                payload={'kind':'tag','value':'language:korean','saved':True}
                for credential,code in [('',401),('Bearer bookmark-worker',403)]:
                    for data in (None,payload):
                        with self.assertRaises(urllib.error.HTTPError) as error:request(credential,data)
                        self.assertEqual(error.exception.code,code)
                with self.assertRaises(urllib.error.HTTPError) as error:request(data=payload,origin='https://example.invalid')
                self.assertEqual(error.exception.code,403)
                with self.assertRaises(urllib.error.HTTPError) as error:request(data={**payload,'unexpected':True})
                self.assertEqual(error.exception.code,400)
                self.assertEqual(self.store.bookmarks(),[])
                with request(data=payload) as response:self.assertEqual(json.load(response),[{'kind':'tag','value':'language:korean'}])
                with request() as response:self.assertEqual(len(json.load(response)),1)
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
