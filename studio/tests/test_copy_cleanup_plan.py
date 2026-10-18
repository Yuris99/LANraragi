"""Catalog-aware cleanup plans use generated archives and temp databases only."""
import hashlib
import json
import sqlite3
import importlib.util
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch
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

    def test_wrapper_preview_and_invalid_paths_never_start_nas_actions(self):
        script=Path(__file__).resolve().parents[1]/'deploy/plan-nas-copy-cleanup.sh'
        result=subprocess.run(['sh',str(script),'preview','/volume1/Example/Books'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Preview only',result.stdout)
        for path in ['/','/volumeX/Books','/volume1/../Other','/volume1/Books,readonly=false']:
            self.assertEqual(subprocess.run(['sh',str(script),'preview',path],capture_output=True).returncode,2)

    def test_wrapper_pins_complete_planner_and_read_only_catalog(self):
        deploy=Path(__file__).resolve().parents[1]/'deploy'
        script=(deploy/'plan-nas-copy-cleanup.sh').read_text()
        for name in ['deploy/plan-copy-cleanup.py','deploy/review-library-storage.py','deploy/archive_in_place.py','sources.py']:
            expected=hashlib.sha256((deploy.parent/name).read_bytes()).hexdigest()+'  '+name
            self.assertIn(expected,script)
        self.assertIn('dst=/catalog,readonly',script)
        self.assertIn('dst=/prior-reports,readonly',script)
        self.assertIn('--prior-report latest',script)

    def test_cli_error_identifies_phase_and_errno_without_private_names(self):
        script=Path(__file__).resolve().parents[1]/'deploy/plan-copy-cleanup.py'
        private=self.root/'private-title-never-print.json'
        result=subprocess.run([sys.executable,'-B',str(script),'--prior-report',str(private),
            '--database',self.store.path,'--library-root',str(self.library),'--copies-root',str(self.copies),
            '--output',str(self.root/'plan.json')],capture_output=True,text=True)
        self.assertEqual(result.returncode,1)
        payload=json.loads(result.stdout)
        self.assertEqual(payload['phase'],'read_prior_report')
        self.assertEqual(payload['errno'],2)
        self.assertTrue(payload['media_and_database_unchanged'])
        self.assertNotIn('private-title',result.stdout+result.stderr)
        self.assertFalse((self.root/'plan.json').exists())

    def test_error_details_never_echo_sql_or_filenames(self):
        tool.phase('read_catalog_entries')
        try:
            with sqlite3.connect(':memory:') as db:db.execute('SELECT * FROM private_title_never_print')
        except sqlite3.Error as error:details=tool.failure_details(error)
        self.assertEqual(details['sqlite_error'],'SQLITE_ERROR')
        self.assertNotIn('private_title',json.dumps(details))
        self.assertEqual(tool.failure_details(ValueError('private-title')),{'phase':'read_catalog_entries','error_type':'ValueError'})
        self.assertEqual(tool.failure_details(ValueError('real_database_required'))['reason'],'real_database_required')

    def test_snapshot_preserves_committed_wal_without_touching_source(self):
        with sqlite3.connect(self.store.path) as live:
            live.execute('PRAGMA journal_mode=WAL')
            live.execute("INSERT INTO settings VALUES('wal-marker','committed')");live.commit()
            paths=[Path(self.store.path),Path(self.store.path+'-wal'),Path(self.store.path+'-shm')]
            before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
            with tool.catalog_snapshot(self.store.path,self.root) as snapshot:
                with sqlite3.connect(snapshot.as_uri()+'?mode=ro',uri=True) as db:
                    self.assertEqual(db.execute("SELECT value FROM settings WHERE key='wal-marker'").fetchone()[0],'committed')
            self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
            self.assertFalse(list(self.root.glob('.catalog-snapshot-*')))

    def test_changing_snapshot_is_rejected_after_bounded_retries(self):
        with sqlite3.connect(self.store.path) as live:
            live.execute('PRAGMA journal_mode=WAL');live.execute("INSERT INTO settings VALUES('changing','0')");live.commit()
            real=tool.copy_catalog_file;writes=[]
            def changing(parent,name,target,expected):
                real(parent,name,target,expected)
                if not name.endswith('-wal'):
                    writes.append(1);live.execute("UPDATE settings SET value=? WHERE key='changing'",(str(len(writes)),));live.commit()
            with patch.object(tool,'copy_catalog_file',side_effect=changing):
                with self.assertRaisesRegex(ValueError,'catalog_changed_during_copy'):
                    with tool.catalog_snapshot(self.store.path,self.root):pass
            self.assertEqual(len(writes),3)
            self.assertFalse(list(self.root.glob('.catalog-snapshot-*')))

    def test_snapshot_rejects_wal_symlink(self):
        wal=Path(self.store.path+'-wal')
        self.assertFalse(wal.exists());wal.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError,'catalog_file_type'):
            with tool.catalog_snapshot(self.store.path,self.root):pass

    def test_report_relative_paths_cannot_escape_inputs(self):
        for path in ['../outside.cbz','/absolute.cbz','sub/../outside.cbz','a\\outside.cbz']:
            with self.assertRaises(ValueError):tool.relative_file(self.library,path)


if __name__=='__main__':unittest.main()
