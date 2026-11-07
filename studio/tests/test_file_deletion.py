"""Generated files only; physical deletion, recovery, scope and metadata retention."""
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
import urllib.request
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import Store
from server import Studio,make_server
from file_deletion import FileDeletion,DeletionWorker,blocked
from uploads import Uploads


def archive_bytes():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:archive.writestr('001.png',b'Generated test page')
    return stream.getvalue()


class FixtureLRR:
    def __init__(self,data,name='Generated original.cbz'):
        self.data=data;self.name=name;self.arcid=hashlib.sha1(data[:512000]).hexdigest();self.calls=[]
    def json(self,path,*args):
        self.calls.append((path,args))
        if path=='/api/archives':return [{'arcid':self.arcid}]
        if path.endswith('/metadata'):return {'arcid':self.arcid,'filename':self.name,'title':'Generated backend','pagecount':1,'arcsize':len(self.data),'tags':'language:korean'}
        if path=='/api/info':return {'version':'generated'}
        raise ValueError('No external service in test')
    def open(self,path,*args):
        assert not args,'No upstream DELETE is permitted'
        self.calls.append((path,args));return io.BytesIO(self.data)


class FileDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.originals=self.root/'originals';self.uploads=self.root/'uploads'
        (self.originals/'manga').mkdir(parents=True);(self.originals/'images').mkdir();self.uploads.mkdir()
        self.store=Store(self.root/'studio.db');self.data=archive_bytes();self.lrr=FixtureLRR(self.data)
        self.path=self.originals/'manga'/self.lrr.name;self.path.write_bytes(self.data)
        self.work=self.store.create_work('Generated saved title',artist='Generated artist',lrr_id=self.lrr.arcid,pages=1,tags=['language:korean'])
        self.store.update_work(self.work['id'],{'title_locked':True,'favorite':True,'rating':4})
        self.store.upsert_source(self.work['id'],{'url':'https://hitomi.la/galleries/123.html'})
        self.api=FileDeletion(self.store,self.lrr)
        self.worker=None
        if os.name=='posix':self.worker=DeletionWorker(self.store.path,self.originals,self.uploads)

    def ready(self):
        if self.worker:self.worker.tick()
        else:
            import file_deletion
            with self.store.db() as db:db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('file-deletion-worker',?)",(json.dumps({'seen':__import__('time').time(),'code_sha256':hashlib.sha256(Path(file_deletion.__file__).read_bytes()).hexdigest()}),))

    def queue(self):
        self.ready();value=self.api.preview(self.work['id'])['request']
        self.api.confirm(self.work['id'],value['id'],value['filename']);return value

    def test_no_worker_or_bad_file_identity_never_creates_deletion_request(self):
        with self.assertRaisesRegex(ValueError,'작업자'):self.api.preview(self.work['id'])
        self.ready();self.lrr.data=b'changed response'
        with self.assertRaisesRegex(ValueError,'일치'):self.api.preview(self.work['id'])
        self.assertIsNone(self.api.status(self.work['id'])['request']);self.assertTrue(self.path.exists())

    def test_preview_and_close_leave_bytes_intact_and_confirmation_is_exact_and_expires(self):
        self.ready();value=self.api.preview(self.work['id'])['request']
        self.assertEqual(self.path.read_bytes(),self.data)
        with self.assertRaises(ValueError):self.api.confirm(self.work['id'],value['id'],'wrong.cbz')
        with self.store.db() as db:db.execute('UPDATE file_deletions SET created=0')
        with self.assertRaises(ValueError):self.api.confirm(self.work['id'],value['id'],value['filename'])
        self.assertEqual(self.api.status(self.work['id'])['request']['state'],'preview')

    @unittest.skipUnless(os.name=='posix','Descriptor-anchored filesystem worker is Linux-only')
    def test_real_delete_preserves_other_files_metadata_and_blocks_stale_sync(self):
        other=self.originals/'manga/Other.cbz';other.write_bytes(b'Keep other work')
        before=self.store.get_work(self.work['id']);self.queue();self.worker.tick();self.worker.tick()
        self.assertFalse(self.path.exists());self.assertEqual(other.read_bytes(),b'Keep other work')
        self.assertEqual(self.api.status(self.work['id'])['request']['state'],'complete')
        after=self.store.get_work(self.work['id']);self.assertIsNone(after['lrr_id'])
        for key in ('title','artist','tags','sources','favorite','rating','progress','last_read'):self.assertEqual(after[key],before[key],key)
        self.assertEqual(self.store.sync_lrr([self.lrr.json('/api/archives/'+self.lrr.arcid+'/metadata')]),0)
        self.assertEqual(self.store.list_works()['total'],1)
        self.assertTrue(all(not args for _,args in self.lrr.calls))

    @unittest.skipUnless(os.name=='posix','Linux worker')
    def test_changed_work_or_active_download_is_held_without_deleting(self):
        request=self.queue();self.store.queue('https://hitomi.la/galleries/123.html','nas','command',self.work['id'])
        self.worker.tick();self.assertTrue(self.path.exists());self.assertEqual(self.api.status(self.work['id'])['request']['state'],'failed')
        with self.store.db() as db:db.execute("UPDATE jobs SET state='failed'")
        request=self.api.preview(self.work['id'])['request'];self.api.confirm(self.work['id'],request['id'],request['filename'])
        with self.store.db() as db:db.execute('UPDATE works SET lrr_id=NULL WHERE id=?',(self.work['id'],))
        self.worker.tick();self.assertTrue(self.path.exists());self.assertEqual(self.api.status(self.work['id'])['request']['state'],'failed')

    @unittest.skipUnless(os.name=='posix','Linux worker')
    def test_modified_or_duplicate_or_symlink_file_is_not_deleted(self):
        self.queue();duplicate=self.originals/'images'/self.path.name;duplicate.write_bytes(self.data)
        self.worker.tick();self.assertEqual(self.api.status(self.work['id'])['request']['state'],'failed');self.assertTrue(self.path.exists());self.assertTrue(duplicate.exists())
        duplicate.unlink();self.queue();self.path.write_bytes(b'Changed book');self.worker.tick();self.assertEqual(self.path.read_bytes(),b'Changed book')
        self.path.unlink();outside=self.root/'outside.cbz';outside.write_bytes(self.data);self.path.symlink_to(outside)
        self.queue();self.worker.tick();self.assertTrue(outside.exists());self.assertTrue(self.path.is_symlink())

    @unittest.skipUnless(os.name=='posix','Linux worker')
    def test_parent_symlink_and_durable_path_escape_are_rejected(self):
        self.path.unlink();outside=self.root/'outside';outside.mkdir();(outside/self.path.name).write_bytes(self.data)
        (self.originals/'manga/link').symlink_to(outside,target_is_directory=True)
        self.queue();self.worker.tick();self.assertTrue((outside/self.path.name).exists())
        (self.originals/'manga/link').unlink();self.path.write_bytes(self.data);request=self.queue()
        with self.store.db() as db:db.execute('UPDATE file_deletions SET target=? WHERE id=?',(json.dumps({'root':'originals','path':'../outside/'+self.path.name,'stamp':[]}),request['id']))
        self.worker.tick();self.assertTrue((outside/self.path.name).exists());self.assertTrue(self.path.exists())

    @unittest.skipUnless(os.name=='posix','Linux worker')
    def test_crash_after_unlink_recovers_without_touching_another_file(self):
        self.queue();original_remove=self.worker.remove
        def interrupt(*args):original_remove(*args);raise OSError('Generated crash after unlink')
        with patch.object(self.worker,'remove',side_effect=interrupt),self.assertRaises(OSError):self.worker.tick()
        self.assertFalse(self.path.exists());self.assertEqual(self.api.status(self.work['id'])['request']['state'],'deleting')
        self.worker.tick();self.assertEqual(self.api.status(self.work['id'])['request']['state'],'complete')
        self.assertIsNone(self.store.get_work(self.work['id'])['lrr_id'])

    @unittest.skipUnless(os.name=='posix','Linux worker')
    def test_replacement_after_durable_intent_is_preserved(self):
        request=self.queue()
        with self.store.db() as db:row=dict(db.execute('SELECT * FROM file_deletions WHERE id=?',(request['id'],)).fetchone())
        target=self.worker.find(row)
        with self.store.db() as db:db.execute("UPDATE file_deletions SET state='deleting',target=? WHERE id=?",(json.dumps(target),request['id']))
        self.path.unlink();self.path.write_bytes(b'New replacement')
        self.worker.tick();self.assertEqual(self.path.read_bytes(),b'New replacement');self.assertEqual(self.api.status(self.work['id'])['request']['state'],'failed')

    @unittest.skipUnless(os.name=='posix','Linux worker')
    def test_equal_prefix_ids_do_not_allow_deleting_a_different_full_file(self):
        self.path.write_bytes(b'P'*512000+b'Correct tail');self.lrr.data=self.path.read_bytes();self.lrr.arcid=hashlib.sha1(self.lrr.data[:512000]).hexdigest()
        with self.store.db() as db:db.execute('UPDATE works SET lrr_id=? WHERE id=?',(self.lrr.arcid,self.work['id']))
        other=self.originals/'images'/self.path.name;other.write_bytes(b'P'*512000+b'Another tail')
        self.assertEqual(hashlib.sha1(other.read_bytes()[:512000]).hexdigest(),self.lrr.arcid)
        self.queue();self.worker.tick();self.assertFalse(self.path.exists());self.assertEqual(other.read_bytes()[-12:],b'Another tail')

    @unittest.skipUnless(os.name=='posix','Linux worker')
    def test_old_completed_download_cannot_restore_a_deleted_file(self):
        sha=hashlib.sha256(self.data).hexdigest();filename='hitomi-123.cbz'
        def completed():
            job=self.store.queue('https://hitomi.la/galleries/123.html','nas','command',self.work['id'])
            result={'directory':job['id']+'-'+'a'*16,'archives':[{'file':filename,'sha256':sha}]}
            with self.store.db() as db:db.execute("UPDATE jobs SET state='complete',result=? WHERE id=?",(json.dumps(result),job['id']))
            return job
        old=completed();self.queue();self.worker.tick()
        metadata={'arcid':self.lrr.arcid,'filename':filename,'title':'Generated restored','pagecount':1,'arcsize':len(self.data)}
        with self.assertRaises(ValueError):self.store.index_command_archive(old['id'],metadata,sha)
        self.assertIsNone(self.store.get_work(self.work['id'])['lrr_id'])
        fresh=completed();(self.uploads/filename).write_bytes(self.data)
        self.assertEqual(self.store.index_command_archive(fresh['id'],metadata,sha),self.work['id'])
        self.assertEqual(self.store.list_works()['total'],1)

    @unittest.skipUnless(os.name=='posix','Linux worker')
    def test_uploaded_file_delete_and_explicit_reupload_restore_retained_work(self):
        self.path.unlink();uploads=Uploads(self.store,self.uploads);receipt=uploads.receive(io.BytesIO(self.data),len(self.data),'Generated upload.cbz')
        with self.store.db() as db:db.execute("UPDATE uploads SET lrr_id=?,state='indexed'",(self.lrr.arcid,))
        self.lrr.name=receipt['stored_name'];self.queue();self.worker.tick()
        self.assertFalse((self.uploads/receipt['stored_name']).exists());self.assertIsNone(self.store.get_work(self.work['id'])['lrr_id'])
        uploads.receive(io.BytesIO(self.data),len(self.data),'Generated restored.cbz')
        self.store.sync_lrr([self.lrr.json('/api/archives/'+self.lrr.arcid+'/metadata')])
        self.assertEqual(self.store.list_works()['total'],1);self.assertEqual(self.store.get_work(self.work['id'])['lrr_id'],self.lrr.arcid)
        self.assertEqual(self.store.get_work(self.work['id'])['title'],'Generated saved title')

    def test_http_admin_origin_field_validation_and_media_gate(self):
        self.ready()
        with patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-deletion','STUDIO_PC_WORKER_TOKEN':'generated-worker'}):
            app=Studio(self.store,self.lrr);server=make_server('127.0.0.1',0,app);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port);auth='Basic '+base64.b64encode(b'admin:generated-deletion').decode()
            def call(path,data=None,credential=auth,origin=None):
                headers={'Authorization':credential,'Content-Type':'application/json'}
                if origin:headers['Origin']=origin
                return urllib.request.urlopen(urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers=headers),timeout=5)
            path='/api/works/'+self.work['id']+'/file-deletion'
            try:
                for credential,code in [('',401),('Bearer generated-worker',403)]:
                    with self.assertRaises(urllib.error.HTTPError) as error:call(path+'/preview',{},credential)
                    self.assertEqual(error.exception.code,code)
                with self.assertRaises(urllib.error.HTTPError) as error:call(path+'/preview',{},origin='https://example.invalid')
                self.assertEqual(error.exception.code,403)
                with self.assertRaises(urllib.error.HTTPError) as error:call(path+'/preview',{'path':'/other/book.cbz'})
                self.assertEqual(error.exception.code,400)
                with call(path+'/preview',{}) as response:preview=json.load(response)['request']
                with call(path+'/confirm',{'request_id':preview['id'],'filename':preview['filename']}) as response:self.assertEqual(json.load(response)['request']['state'],'queued')
                with self.assertRaises(urllib.error.HTTPError) as error:call('/api/media/'+self.lrr.arcid+'/download')
                self.assertEqual(error.exception.code,404)
                self.assertTrue(self.path.exists())
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
