"""Destructive conversion checks use temporary generated files ONLY."""
import os
from pathlib import Path
import sys
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploy'))
import archive_in_place as tool
from make_synthetic import create_fixture


class InPlaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.book = self.root / 'Generated comic'
        self.book.mkdir()
        with zipfile.ZipFile(create_fixture(self.root / 'fixture')) as archive:
            for name in archive.namelist():
                (self.book / name).write_bytes(archive.read(name))
        (self.book / 'ComicInfo.xml').write_bytes(b'<ComicInfo/>')
        (self.book / '.notes').write_bytes(b'include even hidden ordinary files')
        self.original = {p.name: p.read_bytes() for p in self.book.iterdir()}

    def convert(self, **kwargs):
        return tool.convert(self.book, stable_seconds=0, **kwargs)

    def test_default_plan_changes_nothing(self):
        before = sorted(self.root.iterdir())
        self.assertFalse(self.convert()['verified'])
        self.assertEqual(sorted(self.root.iterdir()), before)
        self.assertEqual(self.original, {p.name: p.read_bytes() for p in self.book.iterdir()})

    def test_all_files_verified_then_remove_only_exact_book(self):
        other = self.root / 'Other'; other.mkdir(); (other / 'keep').write_bytes(b'keep')
        result = self.convert(apply=True, delete_source=True)
        self.assertTrue(result['verified']); self.assertTrue(result['source_removed'])
        self.assertFalse(self.book.exists())
        with zipfile.ZipFile(str(self.book) + '.cbz') as archive:
            self.assertEqual(self.original, {name: archive.read(name) for name in archive.namelist()})
            self.assertIsNone(archive.testzip())
        self.assertEqual((other / 'keep').read_bytes(), b'keep')

    def test_without_delete_flag_keeps_source(self):
        result = self.convert(apply=True)
        self.assertTrue(result['verified']); self.assertFalse(result['source_removed'])
        self.assertTrue(self.book.is_dir())

    def test_nested_and_empty_directories_preserved_in_archive(self):
        (self.book / 'extras').mkdir(); (self.book / 'extras' / 'empty').mkdir()
        (self.book / 'extras' / 'notes.txt').write_bytes(b'nested')
        self.convert(apply=True, delete_source=True)
        with zipfile.ZipFile(str(self.book) + '.cbz') as archive:
            self.assertEqual(archive.read('extras/notes.txt'), b'nested')
            self.assertIn('extras/empty/', archive.namelist())

    def test_existing_cbz_never_overwritten_or_used_to_delete(self):
        target = Path(str(self.book) + '.cbz'); target.write_bytes(b'existing')
        with self.assertRaisesRegex(ValueError, 'existing_cbz'):
            self.convert(apply=True, delete_source=True)
        self.assertEqual(target.read_bytes(), b'existing'); self.assertTrue(self.book.is_dir())

    def test_symlink_and_hardlink_originals_rejected(self):
        alias = self.book / 'alias'; alias.symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'link_or_special'):
            self.convert(apply=True, delete_source=True)
        alias.unlink(); os.link(self.book / 'ComicInfo.xml', alias)
        with self.assertRaisesRegex(ValueError, 'link_or_special'):
            self.convert(apply=True, delete_source=True)
        self.assertTrue(self.book.is_dir())

    def test_symlink_in_source_path_rejected(self):
        alias = self.root / 'alias'; alias.symlink_to(self.book, target_is_directory=True)
        with self.assertRaises(OSError):
            tool.convert(alias, apply=True, delete_source=True, stable_seconds=0)
        self.assertTrue(self.book.is_dir())

    def test_fifo_and_nas_metadata_refused(self):
        special = self.book / 'fifo'; os.mkfifo(special)
        with self.assertRaisesRegex(ValueError, 'link_or_special'):
            self.convert(apply=True, delete_source=True)
        special.unlink(); (self.book / '@eaDir').mkdir()
        with self.assertRaisesRegex(ValueError, 'nas_system'):
            self.convert(apply=True, delete_source=True)

    def test_crc_or_hash_failure_never_deletes(self):
        with patch.object(tool, 'verify', side_effect=ValueError('synthetic mismatch')):
            with self.assertRaises(ValueError): self.convert(apply=True, delete_source=True)
        self.assertTrue(self.book.is_dir()); self.assertFalse(Path(str(self.book) + '.cbz').exists())

    def test_changed_source_before_publication_preserved(self):
        verify = tool.verify
        def changed(*args):
            verify(*args); (self.book / 'ComicInfo.xml').write_bytes(b'changed')
        with patch.object(tool, 'verify', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'source_changed'):
                self.convert(apply=True, delete_source=True)
        self.assertEqual((self.book / 'ComicInfo.xml').read_bytes(), b'changed')
        self.assertFalse(Path(str(self.book) + '.cbz').exists())

    def test_failure_after_publication_preserves_archive_and_source(self):
        verify = tool.verify; count = 0
        def interrupted(*args):
            nonlocal count
            count += 1
            if count == 2: raise OSError('synthetic interruption')
            return verify(*args)
        with patch.object(tool, 'verify', side_effect=interrupted):
            with self.assertRaises(OSError): self.convert(apply=True, delete_source=True)
        self.assertTrue(self.book.is_dir())
        with zipfile.ZipFile(str(self.book) + '.cbz') as archive:
            self.assertEqual(self.original, {name: archive.read(name) for name in archive.namelist()})

    def test_interruption_during_removal_leaves_complete_archive_no_auto_retry(self):
        unlink = os.unlink; count = 0
        def interrupted(name, **kwargs):
            nonlocal count
            if not name.startswith('.studio-compress-'):
                count += 1
                if count == 2: raise OSError('synthetic power loss')
            return unlink(name, **kwargs)
        with patch.object(tool.os, 'unlink', side_effect=interrupted):
            with self.assertRaises(OSError): self.convert(apply=True, delete_source=True)
        with zipfile.ZipFile(str(self.book) + '.cbz') as archive:
            self.assertEqual(self.original, {name: archive.read(name) for name in archive.namelist()})
        self.assertTrue(self.book.is_dir())
        with self.assertRaisesRegex(ValueError, 'existing_cbz'):
            self.convert(apply=True, delete_source=True)

    def test_currently_changing_files_rejected(self):
        with self.assertRaisesRegex(ValueError, 'not_stable'):
            tool.convert(self.book, apply=True, delete_source=True)

    def test_archive_different_bytes_or_names_refused(self):
        with tool.directory(self.book) as fd:
            expected = tool.inventory(fd, 0)
            wrong = self.root / 'wrong.cbz'
            with zipfile.ZipFile(wrong, 'w') as archive:
                for name, data in self.original.items():
                    archive.writestr(name, bytes(len(data)))
            with self.assertRaisesRegex(ValueError, 'content_mismatch'):
                tool.verify(fd, wrong, expected)
            with zipfile.ZipFile(wrong, 'w') as archive: archive.writestr('wrong', b'x')
            with self.assertRaisesRegex(ValueError, 'file_list_mismatch'):
                tool.verify(fd, wrong, expected)

    def test_batch_finds_books_but_never_converts_collection_root(self):
        source = self.root / 'source'; (source / 'manga' / 'author').mkdir(parents=True)
        (source / 'images').mkdir()
        self.book.rename(source / 'manga' / 'author' / self.book.name)
        (source / 'manga' / 'loose.png').write_bytes(b'collection-root-not-a-book')
        report = tool.batch(source, ['manga', 'images'], apply=True, delete_source=True, stable_seconds=0)
        self.assertEqual(report['source_removed'], 1)
        self.assertTrue((source / 'manga' / 'author' / (self.book.name + '.cbz')).exists())
        self.assertTrue((source / 'manga' / 'loose.png').exists())
        self.assertTrue((source / 'images').is_dir())

    def test_batch_stops_on_fault_and_does_not_remove_later_books(self):
        source = self.root / 'source'; (source / 'manga').mkdir(parents=True)
        self.book.rename(source / 'manga' / 'A')
        (source / 'manga' / 'A.cbz').write_bytes(b'existing')
        later = source / 'manga' / 'B'; later.mkdir(); (later / '1.png').write_bytes(b'generated')
        report = tool.batch(source, ['manga'], apply=True, delete_source=True, stable_seconds=0)
        self.assertEqual(report['errors'], 1)
        self.assertTrue((source / 'manga' / 'A').exists()); self.assertTrue(later.exists())
        self.assertFalse(Path(str(later) + '.cbz').exists())

    def test_database_lock_rejects_pending_imports_without_modifying_db(self):
        database = self.root / 'studio.db'
        with sqlite3.connect(database) as db:
            db.execute('CREATE TABLE folder_jobs (state TEXT)')
            db.execute("INSERT INTO folder_jobs VALUES ('queued')")
        before = database.read_bytes()
        with self.assertRaisesRegex(ValueError, 'finish_or_cancel'):
            with tool.import_lock(database): self.fail('must not enter')
        self.assertEqual(before, database.read_bytes())
        with sqlite3.connect(database) as db: db.execute('DELETE FROM folder_jobs')
        with tool.import_lock(database):
            with self.assertRaises(BlockingIOError):
                with tool.import_lock(database): self.fail('must not acquire twice')

    def test_low_disk_space_never_publishes_or_deletes(self):
        class Full:
            f_bavail = 0
            f_frsize = 4096
        with patch.object(tool.os, 'fstatvfs', return_value=Full()):
            with self.assertRaisesRegex(ValueError, 'insufficient_free_space'):
                self.convert(apply=True, delete_source=True)
        self.assertTrue(self.book.is_dir()); self.assertFalse(Path(str(self.book) + '.cbz').exists())


if __name__ == '__main__': unittest.main()
