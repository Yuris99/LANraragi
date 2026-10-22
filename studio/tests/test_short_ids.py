"""Source-qualified navigation aliases, migration/backup and exact tag filtering."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backup import copy_database
from server import Studio,make_server
from store import Store


class ShortIdTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(self.root/'studio.db')
    def source(self,work,provider,number,tags=None):
        url={'hitomi':f'https://hitomi.la/galleries/{number}.html','ehentai':f'https://e-hentai.org/g/{number}/token/','nhentai':f'https://nhentai.net/g/{number}/'}[provider]
        return self.store.upsert_source(work['id'],{'url':url,'tags':tags or []})
    def test_equal_numbers_are_separate_and_never_fall_back_to_other_sites(self):
        works=[self.store.create_work(p) for p in ['H','E','N']]
        for work,provider in zip(works,['hitomi','ehentai','nhentai']):self.source(work,provider,'123')
        for work,alias in zip(works,['123','E123','N123']):
            resolved=self.store.resolve_short_id(alias);self.assertEqual(resolved['id'],work['id']);self.assertEqual(resolved['short_id'],alias)
        e=self.store.create_work('Only E');self.source(e,'ehentai','999')
        with self.assertRaises(KeyError):self.store.resolve_short_id('999')
        self.assertEqual(self.store.resolve_short_id('e999')['id'],e['id'])
        self.assertEqual(self.store.list_works()['total'],4);self.assertEqual(self.store.jobs(),[])
    def test_explicit_multi_source_links_prefer_hitomi_but_keep_all_aliases(self):
        work=self.store.create_work('Explicit same work');local=work['short_id']
        self.source(work,'ehentai','321');self.source(work,'nhentai','654')
        self.assertEqual(self.store.get_work(work['id'])['short_id'],'E321')
        self.source(work,'hitomi','987')
        for alias in [local,'E321','N654','987']:
            resolved=self.store.resolve_short_id(alias);self.assertEqual(resolved['id'],work['id']);self.assertEqual(resolved['short_id'],'987')
        self.assertEqual(len(self.store.get_work(work['id'])['sources']),3)
        other=self.store.create_work('Different book')
        with self.assertRaises(ValueError):self.source(other,'hitomi','987')
    def test_local_numbers_survive_restart_vacuum_and_new_source_links(self):
        first=self.store.create_work('First');second=self.store.create_work('Second')
        for _ in range(3):self.store=Store(self.store.path)
        with self.store.db() as db:db.execute('VACUUM')
        self.assertEqual(self.store.get_work(first['id'])['short_id'],first['short_id'])
        self.assertEqual(self.store.get_work(second['id'])['local_number'],second['local_number'])
        with self.store.db() as db:self.assertEqual(db.execute("SELECT seq FROM sqlite_sequence WHERE name='work_numbers'").fetchone()[0],2)
        self.source(first,'hitomi','777')
        self.assertEqual(self.store.resolve_short_id(first['short_id'])['short_id'],'777')
        self.assertEqual(self.store.create_work('Third')['short_id'],'L3')
    def test_old_database_is_backfilled_and_backup_restore_keeps_numbers(self):
        first=self.store.create_work('Old first');second=self.store.create_work('Old second')
        with self.store.db() as db:db.execute('DROP TABLE work_numbers')
        self.store=Store(self.store.path)
        self.assertEqual(self.store.get_work(first['id'])['short_id'],'L1')
        self.assertEqual(self.store.get_work(second['id'])['short_id'],'L2')
        backup=self.root/'backup.db';result=copy_database(self.store.path,backup)
        self.assertEqual(result['counts']['work_numbers'],2)
        restored=self.root/'restored.db';copy_database(backup,restored,restore=True)
        store=Store(restored)
        self.assertEqual(store.resolve_short_id('L1')['id'],first['id']);self.assertEqual(store.create_work('New')['short_id'],'L3')
    def test_invalid_aliases_are_bounded_and_create_no_jobs(self):
        for alias in ['',None,'Q123','/123','123/6','L0','L9223372036854775808','1'*33,'https://hitomi.la/galleries/123.html']:
            with self.subTest(alias=alias),self.assertRaises(ValueError):self.store.resolve_short_id(alias)
        with self.assertRaises(KeyError):self.store.resolve_short_id('E123')
        self.assertEqual(self.store.jobs(),[])
    def test_exact_all_tags_deduplicate_works_and_combine_with_favorites(self):
        first=self.store.create_work('Blue',tags=['theme:blue','theme:bluebird'])
        second=self.store.create_work('Bluebird',tags=['theme:bluebird'])
        self.source(first,'hitomi','123',['theme:blue','source:only'])
        self.store.edit_user_tags([first['id']],['theme:blue','my:tag','100% literal'])
        self.store.edit_user_tags([second['id']],['my:tag'])
        self.store.update_work(first['id'],{'favorite':True})
        for tag,total in [('theme:blue',1),('theme:bluebird',2),('source:only',1),('my:tag',2)]:
            self.assertEqual(self.store.list_works(all_tag=tag)['total'],total)
        self.assertEqual(self.store.list_works(tag='source:only')['total'],0)
        self.assertEqual(self.store.list_works(all_tag='my:tag',favorite=True)['total'],1)
        catalog={r['tag']:r['count'] for r in self.store.library_tags()}
        self.assertEqual(catalog['theme:blue'],1);self.assertEqual(catalog['my:tag'],2)
        self.assertEqual(self.store.library_tags('%'),[{'tag':'100% literal','count':1}])
        self.assertEqual(self.store.get_work(first['id'])['sources'][0]['tags'],['theme:blue','source:only'])


class ShortIdHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.environment=patch.dict(os.environ,{'STUDIO_PASSWORD':'short-synthetic','STUDIO_PC_WORKER_TOKEN':'short-worker'});self.environment.start();self.addCleanup(self.environment.stop)
        self.store=Store(Path(self.temp.name)/'studio.db');self.work=self.store.create_work('HTTP fixture',tags=['theme:blue'])
        self.store.upsert_source(self.work['id'],{'url':'https://hitomi.la/galleries/123.html'})
        class NoSiteCalls:
            def json(self,*args):raise AssertionError('Short ID lookup must not contact a site or LANraragi')
        self.server=make_server('127.0.0.1',0,Studio(self.store,NoSiteCalls()))
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever,daemon=True).start();self.base='http://127.0.0.1:'+str(self.server.server_port)
    def request(self,path,authorization=None):
        if authorization is None:authorization='Basic '+base64.b64encode(b'admin:short-synthetic').decode()
        return urllib.request.urlopen(urllib.request.Request(self.base+path,headers={'Authorization':authorization}),timeout=5)
    def test_short_lookup_and_tag_filter_are_local_authenticated_reads(self):
        with self.request('/api/short/123') as response:self.assertEqual(json.load(response)['id'],self.work['id'])
        with self.request('/api/library/tags') as response:self.assertEqual(json.load(response),[{'tag':'theme:blue','count':1}])
        with self.request('/api/works?'+urllib.parse.urlencode({'all_tag':'theme:blue'})) as response:self.assertEqual(json.load(response)['total'],1)
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/short/E123')
        self.assertEqual(error.exception.code,404);self.assertEqual(self.store.jobs(),[])
    def test_missing_auth_and_worker_tokens_cannot_read_aliases_or_tags(self):
        for path in ['/api/short/123','/api/library/tags']:
            for auth,code in [('',401),('Bearer short-worker',403)]:
                with self.subTest(path=path,code=code),self.assertRaises(urllib.error.HTTPError) as error:self.request(path,auth)
                self.assertEqual(error.exception.code,code)


if __name__=='__main__':unittest.main()
