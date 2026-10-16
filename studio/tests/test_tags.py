import io
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import Store
from backup import copy_database
from server import Studio
from importer import Importer,Snapshot
from uploads import UploadError
from make_synthetic import create_fixture

class TagTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(self.root/'studio.db')
        self.a=self.store.create_work('First',lrr_id='a'*40,tags=['upstream'])
        self.b=self.store.create_work('Second')
        self.source=self.store.upsert_source(self.a['id'],{'url':'https://e-hentai.org/g/123/token/','tags':['original'],'comments':[{'id':'1','text':'kept'}]})
    def test_batch_preserves_remote_metadata_across_sync(self):
        self.store.edit_user_tags([self.a['id'],self.b['id']],['소장','소장','read'])
        self.store.sync_lrr([{'arcid':'a'*40,'title':'Synced','tags':'new upstream'}])
        a=self.store.get_work(self.a['id'])
        self.assertEqual(a['user_tags'],['read','소장'])
        self.assertEqual(a['sources'][0]['tags'],['original'])
        self.assertEqual(a['sources'][0]['comments'][0]['text'],'kept')
        self.assertEqual(self.store.list_works(query='소장')['total'],2)
        self.assertEqual(self.store.list_works(tag='소장')['total'],2)
        self.assertEqual(self.store.list_works(tag='장')['total'],0)
    def test_batch_rolls_back_on_missing_work_or_limit(self):
        with self.assertRaises(KeyError):self.store.edit_user_tags([self.a['id'],'missing'],['x'])
        self.assertEqual(self.store.get_work(self.a['id'])['user_tags'],[])
        self.store.edit_user_tags([self.a['id']],[str(n) for n in range(100)])
        with self.assertRaises(ValueError):self.store.edit_user_tags([self.b['id'],self.a['id']],['overflow'])
        self.assertEqual(self.store.get_work(self.b['id'])['user_tags'],[])
    def test_rename_merge_remove_and_literal_autocomplete(self):
        self.store.edit_user_tags([self.a['id'],self.b['id']],['old','100%'])
        self.store.edit_user_tags([self.a['id']],['new'])
        self.assertEqual(self.store.rename_user_tag('old','new')['updated'],2)
        self.assertEqual(self.store.tag_catalog('%'),[{'tag':'100%','count':2}])
        self.store.edit_user_tags([self.a['id']],remove=['new'])
        self.assertEqual(self.store.tag_catalog('new'),[{'tag':'new','count':1}])
        self.assertIn('original',self.store.get_work(self.a['id'])['all_tags'])
    def test_validation(self):
        for tags in ['x',[None],[''],['a\n'],['x'*121]]:
            with self.subTest(tags=tags),self.assertRaises(ValueError):self.store.edit_user_tags([self.a['id']],tags)
        with self.assertRaises(ValueError):self.store.rename_user_tag('same','same')
    def test_backup_keeps_user_tags_and_schema_reopen(self):
        self.store.edit_user_tags([self.a['id']],['backup'])
        result=copy_database(self.store.path,self.root/'backup.db')
        self.assertEqual(result['counts']['user_tags'],1)
        restored=Store(self.root/'backup.db')
        self.assertEqual(restored.get_work(self.a['id'])['user_tags'],['backup'])
    def test_upload_tags_applied_after_link_and_duplicate_edit(self):
        fixture=create_fixture(self.root/'fixture');app=Studio(self.store,None,upload_dir=self.root/'uploads')
        with fixture.open('rb') as stream:result=app.uploads.receive(stream,fixture.stat().st_size,fixture.name)
        self.store.annotate_upload(result['sha256'],['from upload'])
        self.store.sync_lrr([{'arcid':'b'*40,'filename':result['sha256'],'title':'Book'}])
        work=self.store.list_works(tag='from upload')['items'][0]
        self.store.annotate_upload(result['sha256'],['second'])
        self.assertEqual(self.store.get_work(work['id'])['user_tags'],['from upload','second'])
        self.store.edit_user_tags([work['id']],remove=['from upload'])
        self.store.sync_lrr([{'arcid':'b'*40,'filename':result['sha256'],'title':'Book'}])
        self.assertEqual(self.store.get_work(work['id'])['user_tags'],['second'])
    def test_inbox_is_copy_only_idempotent_and_restart_safe(self):
        inbox=self.root/'inbox';fixture=create_fixture(inbox)
        app=Studio(self.store,None,upload_dir=self.root/'uploads')
        importer=Importer(app,inbox,stable_seconds=0)
        original=fixture.read_bytes()
        self.assertEqual(importer.scan(),1)
        self.assertEqual(importer.scan(),0)
        self.assertEqual(Importer(app,inbox,stable_seconds=0).scan(),0)
        self.assertEqual(fixture.read_bytes(),original)
        (inbox/'link.cbz').symlink_to(fixture)
        self.assertEqual(importer.scan(),0)
        (inbox/'broken.cbz').write_bytes(b'invalid')
        self.assertEqual(importer.scan(),0)
        self.assertEqual(len(app.uploads.list()),1)
    def test_inbox_waits_for_stability_and_rejects_overlap(self):
        inbox=self.root/'inbox';create_fixture(inbox)
        app=Studio(self.store,None,upload_dir=self.root/'uploads')
        self.assertEqual(Importer(app,inbox,stable_seconds=3600).scan(),0)
        with self.assertRaises(ValueError):Importer(app,self.root)

    def test_pending_upload_batches_advance_beyond_recent_100(self):
        app=Studio(self.store,None,upload_dir=self.root/'uploads')
        with self.store.db() as db:
            db.executemany('INSERT INTO uploads(sha256,original_name,stored_name,bytes,created) VALUES(?,?,?,?,?)',[(format(n,'064x'),'x.cbz',format(n,'064x')+'.cbz',1,n) for n in range(102)])
        batch=app.uploads.pending()
        self.assertEqual(len(batch),100)
        remaining=app.uploads.pending(batch[-1]['sha256'])
        self.assertEqual(len(remaining),2)
        self.assertEqual(app.uploads.pending(remaining[-1]['sha256'])[0]['sha256'],batch[0]['sha256'])

    def test_source_changed_during_read_is_not_published(self):
        path=create_fixture(self.root/'inbox')
        app=Studio(self.store,None,upload_dir=self.root/'uploads')
        with path.open('rb') as stream:
            import os
            info=os.fstat(stream.fileno());snapshot=Snapshot(stream,info)
            with path.open('ab') as writer:writer.write(b'changed')
            with self.assertRaises(UploadError):app.uploads.receive(snapshot,info.st_size,path.name)
        self.assertEqual(app.uploads.list(),[])

if __name__=='__main__':unittest.main()
