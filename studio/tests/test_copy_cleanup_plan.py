"""Catalog-aware cleanup plans use generated archives and temp databases only."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy'))
from store import Store
spec=importlib.util.spec_from_file_location('cleanup_plan',Path(__file__).resolve().parents[1]/'deploy/plan-copy-cleanup.py')
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.library=self.root/'library';self.copies=self.root/'copies'
        self.library.mkdir();self.copies.mkdir();self.store=Store(self.root/'studio.db')
        self.source=self.library/'[Artist] Generated [123456].cbz'
        old=self.root/'copy.cbz'
        self.write_archive(self.source,b'original metadata')
        self.write_archive(old,b'copy-only metadata')
        self.sha=hashlib.sha256(old.read_bytes()).hexdigest();self.duplicate=self.copies/(self.sha+'.cbz');old.rename(self.duplicate)
        for path in [self.source,self.duplicate]:
            self.store.sync_lrr([dict(arcid=tool.locator(path),filename=path.name,title=path.stem,tags='')])
        with self.store.db() as db:
            db.execute("INSERT INTO uploads(sha256,original_name,stored_name,bytes,created,lrr_id,state) VALUES(?,?,?,?,?,?,?)",
                (self.sha,'Generated copy.cbz',self.duplicate.name,self.duplicate.stat().st_size,1,tool.locator(self.duplicate),'indexed'))
        self.report=tool.review.review(self.library,self.copies)

    @staticmethod
    def write_archive(path,metadata):
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('1.png',b'generated page data');archive.writestr('notes.json',metadata)

    def plan(self):return tool.build_plan(self.report,self.store.path,self.library,self.copies)

    def test_plan_preserves_both_catalogs_and_never_deletes_or_modifies_db(self):
        old=next(w for w in self.store.list_works()['items'] if w['lrr_id']==tool.locator(self.duplicate))
        self.store.update_work(old['id'],{'favorite':True,'rating':4})
        self.store.upsert_source(old['id'],{'url':'https://nhentai.net/g/123456/','comments':[{'id':'1','text':'Generated comment'}]})
        with self.store.db() as db:db.execute('INSERT INTO user_tags VALUES(?,?)',(old['id'],'Generated tag'))
        before=self.store.export()['works'];hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in [self.source,self.duplicate]]
        plan=self.plan();summary=plan['summary']
        self.assertEqual((summary['candidate_pairs'],summary['distinct_copies'],summary['catalog_pairs'],summary['held_copies']),(1,1,1,0))
        self.assertEqual(summary['copies_with_extra_or_different_metadata'],1)
        self.assertEqual(summary['copies_with_saved_user_state'],1)
        saved=plan['items'][0]['targets'][0]['copy_catalog']
        self.assertEqual(saved['work']['rating'],4);self.assertEqual(saved['user_tags'],['Generated tag'])
        self.assertEqual(len(saved['sources']),1);self.assertTrue(saved['local_numbers'])
        self.assertEqual(before,self.store.export()['works'])
        self.assertEqual(hashes,[hashlib.sha256(p.read_bytes()).hexdigest() for p in [self.source,self.duplicate]])
        self.assertFalse(summary['database_modified']);self.assertEqual(summary['source_removed'],0)

    def test_ambiguous_multiple_survivors_are_held_and_pairs_are_not_copy_count(self):
        another=self.library/'Other.cbz';another.write_bytes(self.source.read_bytes())
        self.report=tool.review.review(self.library,self.copies)
        summary=self.plan()['summary']
        self.assertEqual((summary['candidate_pairs'],summary['distinct_copies'],summary['ambiguous_copies'],summary['held_copies']),(2,1,1,1))

    def test_changed_candidate_is_held(self):
        self.write_archive(self.duplicate,b'changed since review')
        plan=self.plan()
        self.assertEqual(plan['summary']['held_copies'],1)
        self.assertIn('file_or_report_revalidation_failed',plan['items'][0]['holds'])

    def test_missing_survivor_or_unsynchronized_basename_is_held(self):
        with self.store.db() as db:db.execute("UPDATE works SET archive_filename='' WHERE lrr_id=?",(tool.locator(self.source),))
        self.assertIn('survivor_filename_not_confirmed_sync_first',self.plan()['items'][0]['holds'])

    def test_report_relative_paths_cannot_escape_inputs(self):
        for path in ['../outside.cbz','/absolute.cbz','sub/../outside.cbz','a\\outside.cbz']:
            with self.assertRaises(ValueError):tool.relative_file(self.library,path)


if __name__=='__main__':unittest.main()
