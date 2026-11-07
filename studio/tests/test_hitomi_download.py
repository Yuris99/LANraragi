"""Generated gallery data: metadata survives packaging, indexing and later sync."""
import json
import base64
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import threading
import urllib.request
import urllib.error
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from gallery_engine import engine_argv,package_images
from make_synthetic import create_fixture
from metadata import result
from sources import parse_source
from store import Store
from server import Studio,make_server
from worker import run_job

URL='https://hitomi.la/galleries/123.html'


class HitomiDownloadTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('gallery_dl'),'Requires the pinned worker image')
    def test_pinned_cli_info_and_images_reach_packaging_together(self):
        from gallery_dl import main as gallery_main,config
        from gallery_dl.extractor.hitomi import HitomiGalleryExtractor
        import requests
        info={'id':123,'title':'Generated actual title','type':'manga','language':'korean',
              'artists':[{'artist':'generated artist'}],'tags':[{'tag':'glasses','female':1}],'files':[{},{}]}
        png=bytes.fromhex('89504e470d0a1a0a')+b'generated image body'
        def request(session,method,url,**kwargs):
            if url=='https://ltn.gold-usergeneratedcontent.net/galleries/123.js':body=('var galleryinfo = '+json.dumps(info)).encode()
            elif url in ('https://fixture.invalid/1.png','https://fixture.invalid/2.png'):body=png
            else:raise AssertionError('Unexpected generated request: '+url)
            response=requests.Response();response.url=url;response.status_code=200;response._content=body;response.raw=io.BytesIO(body)
            response.raw.chunked=False;response.encoding='utf-8'
            response.headers={'Content-Length':str(len(body)),'Content-Type':'image/png' if body==png else 'application/javascript'}
            return response
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);config.clear()
            with patch('sys.argv',['gallery-dl',*engine_argv(URL,root)[3:]]),patch('requests.Session.request',request),\
                 patch.object(HitomiGalleryExtractor,'images',return_value=[('https://fixture.invalid/1.png',{}),('https://fixture.invalid/2.png',{})]),\
                 patch.object(HitomiGalleryExtractor,'assets',return_value=[]),patch('gallery_dl.extractor.common.Extractor.sleep'):
                try:gallery_main()
                except SystemExit as error:self.assertIn(error.code,(None,0))
            self.assertTrue((root/'info.json').is_file())
            self.assertEqual(package_images(root,parse_source(URL)),2)
            receipt=json.loads((root/'studio-source.json').read_text(encoding='utf-8'))
            self.assertEqual(receipt['metadata']['title'],info['title'])
            self.assertIn('female:glasses',receipt['metadata']['tags'])
            config.clear()

    def test_engine_writes_info_in_the_attempt_directory(self):
        args=engine_argv(URL,'/tmp/generated')
        self.assertIn('--directory',args)
        self.assertNotIn('--destination',args)

    def test_nested_legacy_info_is_preserved_and_forwarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);fixture=create_fixture(root/'fixture');output=root/'output';output.mkdir()
            nested=output/'hitomi'/'123 Generated title';nested.mkdir(parents=True)
            with zipfile.ZipFile(fixture) as archive:(nested/'0001.png').write_bytes(archive.read('01.png'))
            original={'category':'hitomi','gallery_id':123,'title':'Generated title','title_jpn':'生成タイトル',
                      'artist':['generated artist'],'group':['generated circle'],'parody':['original'],
                      'characters':['generated character'],'language':'Korean','tags':['Glasses ♀','Full Color']}
            raw=json.dumps(original);(nested/'info.json').write_text(raw,encoding='utf-8')
            package_images(output,parse_source(URL))
            with zipfile.ZipFile(output/'hitomi-123.cbz') as archive:
                self.assertEqual(json.loads(archive.read('gallery-dl-original.json')),original)
                self.assertEqual(json.loads(archive.read('info.json'))['source'],URL)
            saved=json.loads((output/'studio-source.json').read_text(encoding='utf-8'))['metadata']
            self.assertEqual(saved['title'],'生成タイトル')
            self.assertEqual(saved['artists'],['generated artist'])
            self.assertTrue({'female:glasses','other:full color','group:generated circle','parody:original','character:generated character','language:korean'} <= set(saved['tags']))
            self.assertEqual((nested/'info.json').read_text(encoding='utf-8'),raw)

    def test_import_repairs_only_placeholder_title_and_survives_sync(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(Path(temporary)/'catalog.db')
            item={'arcid':'a'*40,'filename':'hitomi-123','title':'hitomi-123','pagecount':1,'tags':''}
            store.sync_lrr([item]);work=store.list_works()['items'][0]
            metadata=result(parse_source(URL),'Generated actual title',['artist:generated','language:korean','female:glasses'],pages=1,comments=[])
            store.import_metadata(work['id'],metadata,remote=True)
            store.sync_lrr([item])
            actual=store.get_work(work['id'])
            self.assertEqual(actual['title'],'Generated actual title')
            self.assertEqual(actual['artist'],'generated')
            self.assertIn('female:glasses',actual['all_tags'])
            store.update_work(work['id'],{'title':'Accepted manual title','artist':'Accepted artist','title_locked':True})
            store.import_metadata(work['id'],{**metadata,'title':'New source title'},remote=True)
            store.sync_lrr([item])
            actual=store.get_work(work['id'])
            self.assertEqual((actual['title'],actual['artist']),('Accepted manual title','Accepted artist'))

    def test_index_imports_metadata_from_the_verified_download_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(Path(temporary)/'catalog.db');job=store.queue(URL,'nas','command');claim=store.claim('nas','command')
            metadata=result(parse_source(URL),'Generated actual title',['artist:generated','language:korean'],pages=1,comments=[])
            store.report(job['id'],claim['lease'],'complete',result={'files':2,'bytes':200,'directory':job['id']+'-'+'a'*16,
                'archives':[{'file':'hitomi-123.cbz','bytes':123,'sha256':'b'*64}],'source_metadata':metadata})
            work_id=store.index_command_archive(job['id'],{'arcid':'c'*40,'filename':'hitomi-123','title':'hitomi-123','pagecount':1,'tags':''},'b'*64)
            work=store.get_work(work_id)
            self.assertEqual(work['title'],'Generated actual title')
            self.assertEqual(work['sources'][0]['metadata']['title'],'Generated actual title')

    def test_status_does_not_offer_an_absent_server_downloader(self):
        class NoHitomiDownloader:
            def json(self,path):
                self.asserted_path=path
                return [{'url_regex':r'https://e-hentai\.org/g/[0-9]+/[0-9a-f]+/'}]
        with tempfile.TemporaryDirectory() as temporary:
            app=Studio(Store(Path(temporary)/'catalog.db'),NoHitomiDownloader())
            status=app.download_status(include_plugins=True)
            self.assertTrue(status['server_plugins']['ehentai'])
            self.assertFalse(status['server_plugins']['hitomi'])
            self.assertFalse(status['server_plugins']['exhentai'])

    def test_worker_forwards_the_bounded_public_metadata_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            metadata=result(parse_source(URL),'Generated title',['artist:generated'],pages=1,comments=[])
            program="import pathlib,json,sys;p=pathlib.Path(sys.argv[2]);(p/'hitomi-123.cbz').write_bytes(b'generated archive');(p/'studio-source.json').write_text(json.dumps({'engine':'gallery-dl','metadata':"+repr(metadata)+"}))"
            reports=[]
            run_job({'id':'a'*32,'url':URL},[sys.executable,'-c',program,'{url}','{output}'],temporary,
                    lambda state,message='',value=None:reports.append((state,value)),heartbeat_interval=1)
            self.assertEqual(reports[-1][0],'complete')
            self.assertEqual(reports[-1][1]['source_metadata'],metadata)

    def test_wrong_gallery_report_does_not_create_a_catalog_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=Store(Path(temporary)/'catalog.db');job=store.queue(URL,'nas','command');claim=store.claim('nas','command')
            metadata=result(parse_source('https://hitomi.la/galleries/999.html'),'Other gallery',[],pages=1,comments=[])
            store.report(job['id'],claim['lease'],'complete',result={'files':1,'bytes':123,'directory':job['id']+'-'+'a'*16,
                'archives':[{'file':'hitomi-123.cbz','bytes':123,'sha256':'b'*64}],'source_metadata':metadata})
            with self.assertRaises(ValueError):
                store.index_command_archive(job['id'],{'arcid':'c'*40,'filename':'hitomi-123','title':'hitomi-123'},'b'*64)
            self.assertEqual(store.list_works()['total'],0)

    def test_multiple_or_mismatched_gallery_info_stops_packaging(self):
        for duplicate in (False,True):
            with self.subTest(duplicate=duplicate),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);fixture=create_fixture(root/'fixture')
                with zipfile.ZipFile(fixture) as archive:(root/'0001.png').write_bytes(archive.read('01.png'))
                (root/'info.json').write_text(json.dumps({'gallery_id':999,'title':'Other gallery'}))
                if duplicate:
                    (root/'nested').mkdir();(root/'nested/info.json').write_text('{}')
                with self.assertRaises(ValueError):package_images(root,parse_source(URL))
                self.assertFalse((root/'hitomi-123.cbz').exists())

    def test_http_rejects_an_unsupported_plugin_before_creating_a_job(self):
        class NoDownloaders:
            def json(self,path):return []
        with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-download'}):
            store=Store(Path(temporary)/'catalog.db');server=make_server('127.0.0.1',0,Studio(store,NoDownloaders()))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                data={'provider':'hitomi','reference':'123','target':'nas','engine':'lanraragi'}
                request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/api/downloads',data=json.dumps(data).encode(),
                    headers={'Content-Type':'application/json','Authorization':'Basic '+base64.b64encode(b'admin:generated-download').decode()})
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request,timeout=5)
                self.assertEqual(error.exception.code,400)
                self.assertEqual(store.jobs(),[])
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
