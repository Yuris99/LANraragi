"""Read-only folder import: source integrity, restart/dedup and race guards."""
import base64
import contextlib
import hashlib
import json
import os
import sqlite3
from pathlib import Path,PurePosixPath
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from folder_importer import FolderImporter,pilot_import,root_pilot_import
from make_synthetic import create_fixture
from store import Store
from uploads import Uploads
from backup import copy_database


class FolderImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir()
        self.book=self.source/'manga'/'Book';self.book.mkdir(parents=True)
        self.images=self.source/'images';self.images.mkdir()
        fixture=create_fixture(self.root/'fixture')
        with zipfile.ZipFile(fixture) as cbz:
            for index,name in enumerate(['10.png','2.png','1.png'],1):
                (self.book/name).write_bytes(cbz.read(f'{index:02d}.png'))
        self.store=Store(self.root/'studio.db');self.uploads=Uploads(self.store,self.root/'uploads')

    def importer(self,**kwargs):
        return FolderImporter(self.source,['manga','images'],self.uploads,stable_seconds=0,**kwargs)

    def contents(self):
        return {str(p.relative_to(self.source)):(p.read_bytes(),p.stat().st_mtime_ns,p.stat().st_mode)
                for p in self.source.rglob('*') if p.is_file() and not p.is_symlink()}

    def test_plan_reads_metadata_without_database_or_target_writes(self):
        before=self.contents();importer=FolderImporter(self.source,['manga','images'],stable_seconds=0)
        with patch.object(self.store,'db',side_effect=AssertionError('Plan must not open a DB')):
            result=importer.scan()
        self.assertEqual(result['ready'],1);self.assertEqual(result['pages'],3)
        self.assertFalse((self.root/'uploads').exists());self.assertEqual(before,self.contents())

    def test_diagnosis_reports_access_metadata_without_personal_paths_or_writes(self):
        importer=FolderImporter(self.source,['manga','images'],stable_seconds=0)
        before=self.contents()
        result=importer.diagnose()
        self.assertEqual(result['errors'],0)
        self.assertEqual(result['uid'],os.getuid())
        self.assertEqual(result['paths'][0]['matching_collection_names'],['images','manga'])
        self.assertTrue(all(p['opened'] for p in result['paths']))
        self.assertNotIn('Book',json.dumps(result));self.assertNotIn(str(self.source),json.dumps(result))
        self.assertFalse((self.root/'uploads').exists());self.assertEqual(before,self.contents())

    def test_permission_failure_has_errno_without_leaking_exception_filenames(self):
        importer=FolderImporter(self.source,['manga','images'],stable_seconds=0)
        error=PermissionError(13,'private exception text','private-book.png')
        with patch.object(importer,'directory',side_effect=error):
            report=importer.diagnose();scan=importer.scan()
        self.assertEqual(report['errors'],3);self.assertEqual(scan['errors'],2)
        self.assertEqual(scan['issues'][0]['errno'],13)
        self.assertNotIn('private',json.dumps([report,scan]))

    def test_diagnosis_distinguishes_missing_paths_and_page_limits(self):
        importer=FolderImporter(self.source,['missing','manga/Book'],stable_seconds=0,max_pages=2)
        report=importer.diagnose()
        self.assertEqual(report['paths'][1]['error']['errno'],2)
        self.assertTrue(report['paths'][2]['opened'])
        self.assertEqual(report['paths'][2]['error']['code'],'validation_failed')
        self.assertNotIn('1.png',json.dumps(report))

    def test_natural_order_generated_archive_and_source_bytes_are_preserved(self):
        before=self.contents();self.assertEqual(self.importer().scan()['imported'],1)
        row=self.uploads.list()[0]
        with zipfile.ZipFile(self.uploads.root/row['stored_name']) as cbz:
            self.assertEqual(json.loads(cbz.read('studio-folder.json'))['pages'],['1.png','2.png','10.png'])
            self.assertEqual(cbz.read('000001.png'),(self.book/'1.png').read_bytes())
            self.assertEqual(cbz.testzip(),None)
        self.assertEqual(row['original_name'],'Book.cbz');self.assertEqual(before,self.contents())
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT tag FROM upload_tags').fetchone()[0],'folder:manga/Book')

    def test_restart_skips_receipts_and_preserves_manually_deleted_tags(self):
        self.importer().scan()
        with self.store.db() as db:db.execute('DELETE FROM upload_tags')
        self.assertEqual(self.importer().scan()['imported'],0)
        self.assertEqual(len(self.uploads.list()),1)
        with self.store.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM upload_tags').fetchone()[0],0)

    def test_crash_after_publish_before_receipt_has_deterministic_duplicate_recovery(self):
        self.importer().scan();sha=self.uploads.list()[0]['sha256']
        with self.store.db() as db:db.execute('DELETE FROM folder_imports')
        self.importer().scan()
        self.assertEqual([row['sha256'] for row in self.uploads.list()],[sha])

    def test_staging_never_exposes_a_partial_archive_to_the_shared_watcher(self):
        receive=self.uploads.receive
        def guarded(*args):
            self.assertFalse(list((self.uploads.root/'.staging').rglob('*.cbz')))
            return receive(*args)
        with patch.object(self.uploads,'receive',side_effect=guarded):
            self.assertEqual(self.importer().scan()['imported'],1)

    def test_source_revision_keeps_previous_archive(self):
        self.importer().scan();first=self.uploads.list()[0]
        (self.book/'2.png').write_bytes((self.book/'1.png').read_bytes())
        # Finish the saved traversal before the next full source-change scan.
        for _ in range(3):self.importer().scan()
        self.assertEqual(len(self.uploads.list()),2)
        self.assertEqual(hashlib.sha256((self.uploads.root/first['stored_name']).read_bytes()).hexdigest(),first['sha256'])

    def test_symlinks_hidden_and_synology_thumbnail_directories_are_skipped(self):
        for name in ['@eaDir','.hidden','#recycle']:
            directory=self.source/'manga'/name;directory.mkdir();(directory/'page.png').write_bytes((self.book/'1.png').read_bytes())
        (self.book/'symlink.png').symlink_to(self.book/'1.png')
        (self.source/'manga'/'outside').symlink_to(self.root/'fixture',target_is_directory=True)
        result=self.importer().scan(limit=100)
        self.assertEqual(result['imported'],1);self.assertEqual(result['pages'],3)

    def test_real_synthetic_webp_is_kept_as_webp(self):
        content=base64.b64decode('UklGRjgAAABXRUJQVlA4ICwAAADQAQCdASoEAAQAAUAmJaACdLoB+AADsAD+rhf/M0M8lHlw/8wSvyDcqAAAAA==')
        (self.book/'11.webp').write_bytes(content)
        self.assertEqual(self.importer().scan()['pages'],4)
        with zipfile.ZipFile(self.uploads.root/self.uploads.list()[0]['stored_name']) as cbz:
            self.assertEqual(cbz.read('000004.webp'),content)

    def test_invalid_images_and_changing_source_are_not_published(self):
        (self.book/'2.png').write_bytes(b'<html>not an image</html>')
        self.assertEqual(self.importer().scan()['errors'],1);self.assertEqual(self.uploads.list(),[])
        (self.book/'2.png').write_bytes((self.book/'1.png').read_bytes())
        importer=self.importer();snapshot=importer.snapshot;count=0
        def changed(fd):
            nonlocal count
            result=snapshot(fd);count+=1
            if count>=3:return (*result[:3],'different',result[4])
            return result
        with patch.object(importer,'snapshot',side_effect=changed):self.assertEqual(importer.scan()['errors'],1)
        self.assertEqual(self.uploads.list(),[])

    def test_stability_and_space_limits_defer_without_publishing(self):
        importer=FolderImporter(self.source,['manga','images'],self.uploads,stable_seconds=3600)
        self.assertEqual(importer.scan()['deferred'],1)
        with patch('folder_importer.shutil.disk_usage',return_value=type('Space',(),{'free':1})()):
            self.assertEqual(self.importer().scan()['errors'],1)
        self.assertEqual(self.uploads.list(),[])

    def test_bounded_scans_resume_instead_of_starving_later_directories(self):
        importer=self.importer()
        self.assertTrue(importer.scan(max_directories=1)['bounded'])
        self.assertEqual(self.importer().scan(max_directories=1)['imported'],1)
        self.assertEqual(self.importer().scan(max_directories=1)['directories'],1)
        self.assertEqual(len(self.uploads.list()),1)

    def test_root_escape_overlap_and_bad_cursor_are_rejected(self):
        for roots in [['../outside'],['/absolute'],['manga','manga/Book'],['manga//Book'],['@eaDir']]:
            with self.subTest(roots=roots),self.assertRaises(ValueError):FolderImporter(self.source,roots)
        importer=self.importer()
        with self.store.db() as db:db.execute('INSERT INTO settings VALUES(?,?)',(importer.cursor_key,'["../outside"]'))
        with self.assertRaises(ValueError):importer.scan()

    def test_backup_restore_preserves_folder_receipts_and_scan_progress(self):
        self.importer().scan()
        result=copy_database(self.store.path,self.root/'backup.db')
        self.assertEqual(result['counts']['folder_imports'],1)
        restored=Store(self.root/'backup.db')
        with restored.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM folder_imports').fetchone()[0],1)

    def age_source(self):
        old=time.time()-120
        for path in [self.source,*self.source.rglob('*')]:os.utime(path,(old,old))

    def run_pilot(self,**kwargs):
        return pilot_import(self.source,['manga'],self.store.path,self.uploads.root,require_read_only=False,**kwargs)

    def test_pilot_pins_one_folder_on_retries_and_backs_up_before_database_migration(self):
        another=self.source/'manga'/'Later';another.mkdir();(another/'1.png').write_bytes((self.book/'1.png').read_bytes())
        self.age_source();before=self.contents()
        first=self.run_pilot();second=self.run_pilot()
        self.assertEqual(first['imported'],1);self.assertEqual(second['unchanged'],1)
        self.assertEqual(len(self.uploads.list()),1);self.assertEqual(before,self.contents())
        self.assertNotIn('Book',json.dumps(first));self.assertNotIn(str(self.source),json.dumps(first))
        state=Path(self.store.path).parent/'folder-pilot.json'
        self.assertEqual(json.loads(state.read_text())['relative'],'manga/Book')
        self.assertEqual(state.stat().st_mode&0o777,0o600)
        with sqlite3.connect(self.root/first['backup']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM uploads').fetchone()[0],0)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='folder_imports'").fetchone())
        self.assertEqual((self.root/first['backup']).stat().st_mode&0o777,0o600)

    def test_pilot_backup_failure_stops_before_store_migrations_or_archive_writes(self):
        self.age_source()
        with patch('folder_importer.copy_database',side_effect=OSError(28,'backup disk full')):
            with self.assertRaises(OSError):self.run_pilot()
        self.assertFalse(self.uploads.root.exists())
        with self.store.db() as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='folder_imports'").fetchone())

    def test_pilot_refuses_changed_source_or_a_different_collection_without_advancing(self):
        self.age_source();self.run_pilot()
        (self.book/'1.png').write_bytes((self.book/'2.png').read_bytes())
        with self.assertRaises(ValueError):self.run_pilot()
        with self.assertRaises(ValueError):
            pilot_import(self.source,['images'],self.store.path,self.uploads.root,require_read_only=False)
        self.assertEqual(len(self.uploads.list()),1)
        self.assertEqual(len(list((self.root/'folder-pilot-backups').glob('*.db'))),1)

    def test_pilot_rejects_selection_escape_and_symlink_before_more_writes(self):
        self.age_source();self.run_pilot();state=self.root/'folder-pilot.json'
        saved=json.loads(state.read_text());saved['relative']='../outside'
        state.write_text(json.dumps(saved))
        with self.assertRaises(ValueError):self.run_pilot()
        state.unlink();state.symlink_to(self.root/'studio.db')
        with self.assertRaises(OSError):self.run_pilot()
        self.assertEqual(len(self.uploads.list()),1)

    def test_pilot_requires_readonly_source_and_exclusive_pilot_lock(self):
        self.age_source()
        with self.assertRaisesRegex(ValueError,'읽기 전용'):
            pilot_import(self.source,['manga'],self.store.path,self.uploads.root)
        self.assertFalse((self.root/'folder-pilot.json').exists())
        import fcntl
        with (self.root/'folder-pilot.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'실행 중'):self.run_pilot()
        self.assertFalse(self.uploads.root.exists())

    def test_source_privilege_context_never_encloses_destination_writes(self):
        active=[];entries=[]
        @contextlib.contextmanager
        def source_identity():
            active.append(True);entries.append(True)
            try:yield
            finally:active.pop()
        importer=FolderImporter(self.source,['manga'],self.uploads,stable_seconds=0,source_identity=source_identity)
        receive=self.uploads.receive
        def receive_as_app(*args,**kwargs):
            self.assertFalse(active,'Source privileges leaked into upload/database writes')
            return receive(*args,**kwargs)
        with patch.object(self.uploads,'receive',side_effect=receive_as_app):
            with importer.directory(PurePosixPath('manga/Book')) as fd:
                self.assertFalse(active,'Directory yielded with source privileges')
            result=importer.scan()
        self.assertEqual(result['imported'],1);self.assertTrue(entries);self.assertFalse(active)

    def test_root_pilot_rejects_nonroot_and_invalid_output_identity_before_writes(self):
        with patch('folder_importer.os.getuid',return_value=1026):
            with self.assertRaisesRegex(ValueError,'UID0'):
                root_pilot_import(self.source,['manga'],self.store.path,self.uploads.root,1026,100)
        with patch('folder_importer.os.getuid',return_value=0),patch('folder_importer.os.geteuid',return_value=0,create=True):
            for uid,gid in [(0,100),(1026,0),(-1,100),(True,100),(2147483648,100)]:
                with self.subTest(uid=uid,gid=gid),self.assertRaises(ValueError):
                    root_pilot_import(self.source,['manga'],self.store.path,self.uploads.root,uid,gid)
        self.assertFalse((self.root/'folder-pilot.json').exists());self.assertFalse(self.uploads.root.exists())


if __name__=='__main__':unittest.main()
