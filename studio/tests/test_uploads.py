import base64
import hashlib
import io
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
import zipfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import Store
from server import Studio,make_server
from uploads import Uploads,UploadError
from make_synthetic import create_fixture


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(self.root/'studio.db')
        self.uploads=Uploads(self.store,self.root/'uploads')
        self.content=create_fixture(self.root/'fixtures').read_bytes()

    def test_completed_upload_download_bytes_and_duplicate_are_preserved(self):
        result=self.uploads.receive(io.BytesIO(self.content),len(self.content),'내 만화.cbz')
        duplicate=self.uploads.receive(io.BytesIO(self.content),len(self.content),'other-name.zip')
        self.assertEqual(result['sha256'],hashlib.sha256(self.content).hexdigest())
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(len(list((self.root/'uploads').glob('*.cbz'))),1)
        _,stream=self.uploads.open(result['sha256'])
        with stream:self.assertEqual(stream.read(),self.content)
        self.assertEqual(duplicate['original_name'],'내 만화.cbz')

    def test_same_name_different_content_never_overwrites(self):
        first=self.uploads.receive(io.BytesIO(self.content),len(self.content),'same.cbz')
        other=io.BytesIO(self.content)
        with zipfile.ZipFile(other,'a') as archive:archive.writestr('note.txt','another edition')
        content=other.getvalue()
        second=self.uploads.receive(io.BytesIO(content),len(content),'same.cbz')
        self.assertNotEqual(first['sha256'],second['sha256'])
        _,stream=self.uploads.open(first['sha256'])
        with stream:self.assertEqual(stream.read(),self.content)

    def test_interrupted_and_invalid_files_do_not_publish(self):
        for content,name,length in [(self.content[:50],'incomplete.cbz',len(self.content)),(b'<html>login</html>','fake.cbz',18)]:
            with self.subTest(name=name),self.assertRaises(UploadError):self.uploads.receive(io.BytesIO(content),length,name)
        self.assertEqual(self.uploads.list(),[])
        self.assertEqual(list((self.root/'uploads'/'.staging').iterdir()),[])
        self.assertFalse(list((self.root/'uploads').glob('*.cbz')))

    def test_size_paths_and_unsafe_archive_entries_are_rejected(self):
        for name in ['../escape.cbz','x\\evil.zip','header\r\n.cbz','script.html']:
            with self.subTest(name=name),self.assertRaises(UploadError):self.uploads.receive(io.BytesIO(self.content),len(self.content),name)
        with self.assertRaises(UploadError):Uploads(self.store,self.root/'uploads',10).receive(io.BytesIO(self.content),len(self.content),'book.cbz')
        content=io.BytesIO()
        with zipfile.ZipFile(content,'w') as archive:archive.writestr('../outside.png',b'fixture')
        data=content.getvalue()
        with self.assertRaises(UploadError):self.uploads.receive(io.BytesIO(data),len(data),'unsafe.zip')
        self.assertEqual(self.uploads.list(),[])

    def test_existing_upstream_archive_is_linked_only_after_full_hash_match(self):
        saved=self.uploads.receive(io.BytesIO(self.content),len(self.content),'uploaded.cbz')
        arcid=hashlib.sha1(self.content[:512000]).hexdigest()
        content=self.content
        class Upstream:
            def json(self,path):
                if path=='/api/archives':return [{'arcid':arcid,'filename':'previous-local-file'}]
                return {'arcid':arcid,'filename':'previous-local-file','title':'Existing title','pagecount':3}
            def open(self,path):return io.BytesIO(content)
        app=Studio(self.store,Upstream(),upload_dir=self.root/'uploads')
        self.assertEqual(app.sync_uploads()['synced'],1)
        self.assertEqual(self.uploads.list()[0]['lrr_id'],arcid)
        self.assertEqual(self.store.list_works()['items'][0]['title'],'Existing title')

    def test_upstream_partial_id_collision_does_not_merge_distinct_uploads(self):
        saved=self.uploads.receive(io.BytesIO(self.content),len(self.content),'uploaded.cbz')
        arcid=hashlib.sha1(self.content[:512000]).hexdigest()
        class Upstream:
            def json(self,path):return [{'arcid':arcid,'filename':'another-file'}]
            def open(self,path):return io.BytesIO(b'different archive bytes')
        app=Studio(self.store,Upstream(),upload_dir=self.root/'uploads')
        self.assertEqual(app.sync_uploads()['synced'],0)
        self.assertEqual(self.uploads.list()[0]['state'],'conflict')
        self.assertIsNone(self.uploads.list()[0]['lrr_id'])
        self.assertEqual(self.store.list_works()['total'],0)

    def test_sync_links_only_exact_stored_hash_and_preserves_display_name(self):
        result=self.uploads.receive(io.BytesIO(self.content),len(self.content),'Original title.cbz')
        self.store.sync_lrr([{'arcid':'a'*40,'filename':result['sha256'],'title':result['sha256'],'pagecount':3}])
        self.assertEqual(self.uploads.list()[0]['lrr_id'],'a'*40)
        self.assertEqual(self.store.list_works()['items'][0]['title'],'Original title')
        self.store.sync_lrr([{'arcid':'b'*40,'filename':'same-looking-name','title':'Another book'}])
        self.assertEqual(self.uploads.list()[0]['lrr_id'],'a'*40)


class UploadHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.content=create_fixture(root/'fixtures').read_bytes()
        self.env=patch.dict(os.environ,{'STUDIO_PASSWORD':'upload-test','STUDIO_WORKER_TOKEN':'worker-upload-test'})
        self.env.start();self.addCleanup(self.env.stop)
        self.app=Studio(Store(root/'catalog.db'),None,upload_dir=root/'uploads')
        self.server=make_server('127.0.0.1',0,self.app)
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.auth='Basic '+base64.b64encode(b'admin:upload-test').decode()

    def request(self,path,body=None,headers=None):
        return urllib.request.urlopen(urllib.request.Request(self.base+path,data=body,headers={'Authorization':self.auth,**(headers or {})}),timeout=5)

    def test_binary_upload_range_download_and_duplicate_over_real_http(self):
        path='/api/uploads?filename='+urllib.parse.quote('Synthetic 업로드.cbz')
        with self.request(path,self.content,{'Content-Type':'application/octet-stream'}) as response:
            self.assertEqual(response.status,201);value=json.load(response)
        url='/api/uploads/'+value['sha256']+'/download'
        with self.request(url) as response:
            self.assertEqual(response.read(),self.content)
            self.assertIn('filename*=UTF-8',response.headers['Content-Disposition'])
        with self.request(url,headers={'Range':'bytes=10-29'}) as response:
            self.assertEqual(response.status,206);self.assertEqual(response.read(),self.content[10:30])
        with self.request(path,self.content,{'Content-Type':'application/octet-stream'}) as response:
            self.assertEqual(response.status,200);self.assertTrue(json.load(response)['duplicate'])

    def test_upload_auth_csrf_worker_scope_and_json_routes_stay_separate(self):
        path='/api/uploads?filename=test.cbz'
        for headers,code in [({'Authorization':''},401),({'Authorization':'Bearer worker-upload-test'},403),({'Origin':'https://other.invalid'},403),({'Content-Type':'application/json'},415)]:
            with self.subTest(headers=headers),self.assertRaises(urllib.error.HTTPError) as error:
                self.request(path,self.content,{'Content-Type':'application/octet-stream',**headers})
            self.assertEqual(error.exception.code,code)
        self.assertEqual(self.app.uploads.list(),[])
