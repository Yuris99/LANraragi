import base64
import concurrent.futures
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog import Catalog
from media_details import MediaDetails, MediaDetailsConflict
from server import make_server

DEFAULT={'subtitle_files':'unknown','video_subtitles':'unknown','script':'unknown','dubbing':'unknown','audio_language':'','note':''}


class MediaDetailsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'media-details.json';self.store=MediaDetails(self.path)

    def test_read_does_not_create_file_and_save_preserves_other_editions(self):
        self.assertEqual(self.store.read()['revision'],0);self.assertFalse(self.path.exists())
        self.store.save('a'*32,0,{**DEFAULT,'script':'present','note':'台本.txt 확인'})
        value=self.store.save('b'*32,1,{**DEFAULT,'dubbing':'present','audio_language':'ko'})
        self.assertEqual(value['editions']['a'*32]['script'],'present')
        self.assertEqual(MediaDetails(self.path).read(),value)
        self.assertEqual(self.store.save('b'*32,2,value['editions']['b'*32]),value)

    def test_invalid_or_corrupt_data_never_overwrites(self):
        self.store.save('a'*32,0,DEFAULT);raw=self.path.read_bytes()
        for update in ({'dubbing':'maybe'},{'note':'x'*1001},{'audio_language':None},{'script':[]},{'arbitrary':'x'}):
            with self.subTest(update=update),self.assertRaises(ValueError):self.store.save('a'*32,1,{**DEFAULT,**update})
            self.assertEqual(self.path.read_bytes(),raw)
        self.path.write_bytes(b'broken')
        with self.assertRaises(ValueError):self.store.save('a'*32,1,DEFAULT)
        self.assertEqual(self.path.read_bytes(),b'broken')

    def test_concurrent_save_one_winner(self):
        barrier=threading.Barrier(2)
        def save(key):
            barrier.wait()
            try:self.store.save(key*32,0,DEFAULT);return 'saved'
            except MediaDetailsConflict:return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(2) as pool:self.assertCountEqual(pool.map(save,['a','b']),['saved','conflict'])

    def test_api_auth_origin_validation_export_and_catalog_unchanged(self):
        catalog=Catalog(self.root/'audio.sqlite3');w=catalog.create_work('Original');e=catalog.create_edition(w['id'],'Edition','audio')
        t=catalog.add_track(e['id'],'Track','01.wav',10);catalog.progress(t['id'],3)
        catalog.add_subtitle(t['id'],'01.srt',language='und',label='Original subtitle')
        original=catalog.works();server=make_server(catalog,self.root,port=0,password='fixture-only')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            path='/audio/api/editions/'+e['id']+'/media-details'
            def req(method,path,data=None,auth=True,origin=None):
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port);headers={'Content-Type':'application/json'}
                if auth:headers['Authorization']='Basic '+base64.b64encode(b'admin:fixture-only').decode()
                if origin:headers['Origin']=origin
                conn.request(method,path,json.dumps(data).encode() if data is not None else None,headers)
                r=conn.getresponse();raw=r.read();status=r.status;conn.close();return status,json.loads(raw) if raw else None
            self.assertEqual(req('GET',path,auth=False)[0],401)
            self.assertEqual(req('GET',path)[1],{'revision':0,'details':{}});self.assertFalse(self.path.exists())
            body={'revision':0,'details':{**DEFAULT,'script':'present','note':'direct confirmation'}}
            self.assertEqual(req('POST',path,body,origin='https://other.test')[0],403)
            self.assertEqual(req('POST',path,{**body,'details':{**DEFAULT,'video_subtitles':'burned'}})[0],400)
            self.assertEqual(req('POST',path,{**body,'details':{**DEFAULT,'subtitle_files':'none'}})[0],400)
            self.assertEqual(req('POST',path,body)[0],200)
            self.assertEqual(req('POST',path,body)[0],409)
            self.assertEqual(req('GET','/api/works')[1]['works'][0]['editions'][0]['media_details']['script'],'present')
            self.assertEqual(req('GET','/api/export')[1],{'schema':1,'works':original});self.assertEqual(catalog.works(),original)
            self.path.write_bytes(b'broken')
            self.assertIn('media_details_error',req('GET','/api/works')[1])
            self.assertEqual(req('POST',path,body)[0],400);self.assertEqual(self.path.read_bytes(),b'broken')
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
