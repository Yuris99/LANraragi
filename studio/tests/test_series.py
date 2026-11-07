"""Generated reading series and exact catalog facets; no production mutations."""
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
from backup import copy_database


class SeriesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'catalog.db');self.store.set_automatic_enabled(False)
        self.a=self.store.create_work('First','Artist, Co-author',tags=['series:original','female:glasses'])
        self.b=self.store.create_work('Second',tags=['artist:artist','parody:original'])
        self.c=self.store.create_work('Other','Artist extended')

    def test_exact_artist_uses_catalog_and_all_tag_origins(self):
        self.store.edit_user_tags([self.c['id']],['artist:ARTIST'])
        d=self.store.create_work('Source only')
        self.store.upsert_source(d['id'],{'url':'https://e-hentai.org/g/123/abc/','tags':['artist:Artist']})
        self.assertEqual({w['id'] for w in self.store.list_works(artist='ARTIST')['items']},{self.a['id'],self.b['id'],self.c['id'],d['id']})
        self.assertEqual([w['id'] for w in self.store.list_works(artist='Co-author')['items']],[self.a['id']])
        self.assertEqual(self.store.list_works(artist="Artist%' OR 1=1 --")['total'],0)
        self.assertEqual(self.store.list_works(all_tag='series:original')['total'],2)
        self.store.edit_user_tags([self.c['id']],['artist:ÄUTHOR'])
        self.assertEqual(self.store.list_works(artist='äuthor')['total'],1)

    def test_create_join_order_reopen_remove_preserves_editions_sources_and_files(self):
        before={w['id']:self.store.get_work(w['id']) for w in (self.a,self.b)}
        first=self.store.set_work_series(self.a['id'],{'name':'Generated story','position':2});series=first['series'][0]['id']
        self.store.set_work_series(self.b['id'],{'series_id':series,'position':1})
        result=self.store.list_works(series=series,sort='series',descending=False)
        self.assertEqual([w['id'] for w in result['items']],[self.b['id'],self.a['id']])
        self.assertEqual([w['series_position'] for w in result['items']],[1,2])
        self.assertEqual(result['series']['name'],'Generated story')
        self.assertEqual(self.store.list_works(series=series,all_tag='female:glasses')['total'],1)
        self.assertEqual(Store(self.store.path).list_series()[0]['count'],2)
        self.store.set_work_series(self.a['id'],{'series_id':series,'position':3})
        self.store.remove_work_series(self.b['id'],series)
        self.assertEqual(self.store.list_series()[0]['count'],1)
        for work_id,old in before.items():
            value=self.store.get_work(work_id);value.pop('series');old.pop('series')
            self.assertEqual(value,old)
        self.store.remove_work_series(self.a['id'],series)
        self.assertEqual(self.store.list_series()[0]['count'],0)

    def test_failed_edits_are_atomic_and_validate_untrusted_fields(self):
        for data in [{'name':''},{'name':'x','position':True},{'name':'x','position':0},{'name':'x','position':100001},
                     {'name':'x','series_id':[]},{'name':'x','series_id':'a'*32},{'name':'x\n'}, {'name':'x','extra':1},[]]:
            with self.subTest(data=data),self.assertRaises(ValueError):self.store.set_work_series(self.a['id'],data)
        self.assertEqual(self.store.list_series(),[])
        self.store.set_work_series(self.a['id'],{'name':'Sample'})
        with self.assertRaises(ValueError):self.store.set_work_series(self.b['id'],{'name':'sample'})
        with self.assertRaises(KeyError):self.store.set_work_series(self.b['id'],{'series_id':'a'*32})
        self.assertEqual(self.store.list_series()[0]['count'],1)
        with self.assertRaises(ValueError):self.store.list_works(series='malformed')
        with self.assertRaises(KeyError):self.store.list_works(series='a'*32)

    def test_default_append_preserves_order_and_blocks_unreviewed_retirement(self):
        old=self.store.create_work('Copy',lrr_id='a'*40,pages=6)
        target=self.store.create_work('Original',lrr_id='b'*40,pages=6)
        series=self.store.set_work_series(old['id'],{'name':'Preserved'})['series'][0]['id']
        appended=self.store.set_work_series(self.a['id'],{'series_id':series})
        self.assertEqual(appended['series'][0]['position'],2)
        self.assertEqual(self.store.set_work_series(self.a['id'],{'series_id':series})['series'][0]['position'],2)
        with self.assertRaisesRegex(ValueError,'series_metadata_requires_review'),self.store.db() as db:
            self.store.consolidate_copy(db,old['id'],target['id'],'c'*64,'a'*40,{'pages':6})
        self.assertEqual(self.store.get_work(old['id'])['series'][0]['id'],series)
        self.assertEqual(self.store.list_series()[0]['count'],2)

    @unittest.skipIf(os.name=='nt','POSIX fsync verification runs in Linux')
    def test_sqlite_backup_retains_series(self):
        self.store.set_work_series(self.a['id'],{'name':'Backed-up series'})
        destination=Path(self.temp.name)/'backup.db';copy_database(self.store.path,destination)
        reopened=Store(destination)
        self.assertEqual(reopened.list_series(),self.store.list_series())
        self.assertEqual(reopened.get_work(self.a['id'])['series'],self.store.get_work(self.a['id'])['series'])

    def test_admin_api_roundtrip_and_worker_cannot_change_series(self):
        with patch.dict(os.environ,{'STUDIO_PASSWORD':'series-test','STUDIO_PC_WORKER_TOKEN':'series-worker'}):
            server=make_server('127.0.0.1',0,Studio(self.store,None))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                auth='Basic '+base64.b64encode(b'admin:series-test').decode()
                def request(path,data=None,credential=auth):
                    return urllib.request.urlopen(urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':credential,'Content-Type':'application/json'}),timeout=5)
                path='/api/works/'+self.a['id']+'/series'
                with request(path,{'name':'HTTP series'}) as response:series=json.load(response)['series'][0]['id']
                with request('/api/series') as response:self.assertEqual(json.load(response)[0]['count'],1)
                with request('/api/works?series='+series+'&sort=series&direction=asc') as response:self.assertEqual(json.load(response)['total'],1)
                for endpoint,data in [(path,{'series_id':series,'position':2}),('/api/series',None),(path+'/'+series+'/remove',{})]:
                    with self.assertRaises(urllib.error.HTTPError) as error:request(endpoint,data,'Bearer series-worker')
                    self.assertEqual(error.exception.code,403)
                with request(path+'/'+series+'/remove',{}) as response:self.assertEqual(json.load(response)['series'],[])
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
