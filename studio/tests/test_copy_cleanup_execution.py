"""Real unlink tests operate ONLY on disposable generated archives and DBs."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy'))
import test_copy_cleanup_plan as plan_tests
from server import verify_cleanup_downloads
spec=importlib.util.spec_from_file_location('cleanup_executor',Path(__file__).resolve().parents[1]/'deploy/execute-copy-cleanup.py')
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        fixture=plan_tests.PlanTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        for name in ('root','library','copies','store','source','sha','duplicate','report'):setattr(self,name,getattr(fixture,name))
        self.workspace=self.root/'execution';self.workspace.mkdir()
        self.prior=self.root/'review.json';self.prior.write_text(json.dumps(self.report))
        self.uid=os.geteuid();self.gid=os.getegid()
        self.old=self.store.get_work(next(w['id'] for w in self.store.list_works()['items'] if w['lrr_id']==tool.planner.locator(self.duplicate)))
        self.original=self.store.get_work(next(w['id'] for w in self.store.list_works()['items'] if w['lrr_id']==tool.planner.locator(self.source)))

    def operation(self):return tool.prepare(self.prior,self.store.path,self.library,self.copies,self.workspace)
    def proof(self,operation):return {'created':time.time(),'operation_id':operation['operation_id'],'verified':{r['lrr_id']:r['sha256'] for r in operation['proof_request']['items']}}
    def execute(self,operation,interrupt=None):return tool.apply(operation,self.proof(operation),self.store.path,self.library,self.copies,self.workspace,self.uid,self.gid,interrupt)

    def test_actual_copy_unlink_keeps_original_backup_sources_and_old_links(self):
        self.store.update_work(self.old['id'],{'favorite':True,'rating':4})
        self.store.upsert_source(self.old['id'],{'url':'https://nhentai.net/g/123456/','comments':[{'id':'1','text':'Generated comment'}]})
        with self.store.db() as db:db.execute('INSERT INTO user_tags VALUES(?,?)',(self.old['id'],'custom'))
        original_bytes=self.source.read_bytes();copy_bytes=self.duplicate.read_bytes()
        result=self.execute(self.operation())
        self.assertEqual(result['removed'],1);self.assertFalse(self.duplicate.exists())
        self.assertEqual(self.source.read_bytes(),original_bytes)
        self.assertEqual((self.workspace/'archives'/(self.sha+'.cbz')).read_bytes(),copy_bytes)
        self.assertTrue(list(self.workspace.glob('database-before-*.db')))
        work=self.store.get_work(self.old['id'])
        self.assertEqual(work['id'],self.original['id']);self.assertTrue(work['favorite']);self.assertEqual(work['rating'],4)
        self.assertEqual(work['sources'][0]['comments'][0]['text'],'Generated comment')
        self.assertIn('custom',work['user_tags'])
        self.assertEqual(self.store.resolve_short_id('L'+str(self.old['local_number']))['id'],work['id'])
        self.assertEqual(self.store.resolve_short_id('N123456')['id'],work['id'])
        self.assertEqual(self.store.list_works()['total'],1)
        self.store.sync_lrr([dict(arcid=self.old['lrr_id'],filename=self.duplicate.name,title='Stale index',tags='')])
        self.assertEqual(self.store.list_works()['total'],1)
        self.store.update_work(self.old['id'],{'artist':'Updated through old URL'})
        self.assertEqual(self.store.get_work(self.original['id'])['artist'],'Updated through old URL')
        self.assertEqual(self.operation()['already_removed'],1)
        from uploads import Uploads
        self.assertEqual(Uploads(self.store,self.copies).list(),[])

    def test_crash_after_merge_or_after_unlink_resumes_without_data_loss(self):
        def crash(current):
            if current=='after_catalog_merge':raise RuntimeError('simulated interruption')
        with self.assertRaises(RuntimeError):self.execute(self.operation(),crash)
        self.assertTrue(self.duplicate.exists())
        result=self.execute(self.operation());self.assertEqual(result['removed'],1)
        self.assertEqual(self.store.list_works()['total'],1)

    def test_crash_after_unlink_finalizes_existing_journal(self):
        def crash(current):
            if current=='after_copy_unlink':raise RuntimeError('simulated interruption')
        with self.assertRaises(RuntimeError):self.execute(self.operation(),crash)
        self.assertFalse(self.duplicate.exists())
        result=self.execute(self.operation());self.assertEqual(result['removed'],0)
        self.assertEqual(self.operation()['already_removed'],1)

    def test_missing_or_expired_backend_proof_prevents_delete(self):
        operation=self.operation();proof=self.proof(operation);proof['verified']={}
        with self.assertRaisesRegex(ValueError,'backend_proof_incomplete'):
            tool.apply(operation,proof,self.store.path,self.library,self.copies,self.workspace,self.uid,self.gid)
        self.assertTrue(self.duplicate.exists());self.assertEqual(self.store.list_works()['total'],2)

    def test_changed_original_or_copy_is_never_removed(self):
        operation=self.operation();self.source.write_bytes(b'changed')
        with self.assertRaises(Exception):self.execute(operation)
        self.assertTrue(self.duplicate.exists());self.assertEqual(self.store.list_works()['total'],2)

    def test_upstream_extensionless_basename_is_supported_with_full_proof(self):
        with self.store.db() as db:db.execute('UPDATE works SET archive_filename=? WHERE id=?',(self.source.stem,self.original['id']))
        result=self.execute(self.operation())
        self.assertEqual(result['removed'],1)
        self.assertFalse(self.duplicate.exists())

    def test_conflicting_manual_titles_block_retirement(self):
        self.store.update_work(self.old['id'],{'title':'Manual old','title_locked':True})
        self.store.update_work(self.original['id'],{'title':'Manual survivor','title_locked':True})
        result=self.execute(self.operation())
        self.assertEqual(result['held'],1)
        self.assertEqual(result['hold_reasons']['manual_metadata_conflict'],1)
        self.assertTrue(self.duplicate.exists());self.assertEqual(self.store.list_works()['total'],2)


class BackendProofTests(unittest.TestCase):
    def test_full_backend_hash_required_for_the_exact_archive_id(self):
        content=b'generated backend bytes';sha=hashlib.sha256(content).hexdigest()
        class Backend:
            def open(self,path):
                if path!='/api/archives/'+'a'*40+'/download':raise AssertionError(path)
                return io.BytesIO(content)
        request={'operation_id':'generated','items':[{'lrr_id':'a'*40,'sha256':sha,'bytes':len(content)}]}
        self.assertEqual(verify_cleanup_downloads(Backend(),request)['verified']['a'*40],sha)
        request['items'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'cleanup_backend_hash_mismatch'):verify_cleanup_downloads(Backend(),request)


if __name__=='__main__':unittest.main()
