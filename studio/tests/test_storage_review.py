"""Duplicate review must never mistake an equal number for equal page bytes."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy'))
spec=importlib.util.spec_from_file_location('storage_review',Path(__file__).resolve().parents[1]/'deploy/review-library-storage.py')
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)


class ReviewTests(unittest.TestCase):
    def test_page_match_retains_metadata_differences_and_never_changes_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);library=root/'library';copies=root/'copies';library.mkdir();copies.mkdir()
            for folder,name,notes in [(library,'[Author] Title [123456].cbz',b'original metadata'),(copies,'hash.cbz',b'copy provenance')]:
                with zipfile.ZipFile(folder/name,'w') as archive:
                    archive.writestr('1.png',b'generated-page-one');archive.writestr('2.webp',b'generated-page-two');archive.writestr('notes.json',notes)
            with zipfile.ZipFile(copies/'same-number-123456.cbz','w') as archive:archive.writestr('1.png',b'different-content')
            before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.cbz')}
            result=tool.review(library,copies)
            self.assertEqual(len(result['candidates']),1)
            candidate=result['candidates'][0]
            self.assertFalse(candidate['same_archive_bytes'])
            self.assertFalse(candidate['delete_authorized_by_report'])
            self.assertNotEqual(candidate['copy_other_members'],candidate['library_other_members'])
            self.assertEqual(result['source_removed'],0)
            self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.cbz')})

    def test_overlapping_roots_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with self.assertRaises(ValueError):tool.review(root,root)

    def test_symlinks_are_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);library=root/'library';copies=root/'copies';library.mkdir();copies.mkdir()
            (library/'linked.cbz').symlink_to(root/'outside.cbz')
            result=tool.review(library,copies)
            self.assertEqual(result['errors'],1)
            self.assertEqual(result['candidates'],[])


if __name__=='__main__':unittest.main()
