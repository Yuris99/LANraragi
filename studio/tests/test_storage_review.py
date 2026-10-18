"""Duplicate review must never mistake an equal number for equal page bytes."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import subprocess
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

    def test_nas_wrapper_preview_rejects_paths_and_has_no_docker_or_network_actions(self):
        script=Path(__file__).resolve().parents[1]/'deploy/review-nas-copies.sh'
        result=subprocess.run(['sh',str(script),'preview','/volume1/Example/Books'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Preview only',result.stdout)
        for path in ['/','/volumeX/Books','/volume1/../Other','/volume1/Books,readonly=false']:
            self.assertEqual(subprocess.run(['sh',str(script),'preview',path],capture_output=True).returncode,2)

    def test_nas_wrapper_pins_exact_review_source_hashes(self):
        deploy=Path(__file__).resolve().parents[1]/'deploy'
        script=(deploy/'review-nas-copies.sh').read_text()
        for name in ['deploy/review-library-storage.py','deploy/archive_in_place.py','sources.py']:
            # Immutable NAS tools keep their archived filename parser.
            source=Path(__file__).parent/'fixtures/legacy-review-sources.py' if name=='sources.py' else deploy.parent/name
            expected=hashlib.sha256(source.read_bytes()).hexdigest()+'  '+name
            self.assertIn(expected,script)
        self.assertIn('--network none --read-only',script)
        self.assertIn('dst=/nas-library,readonly',script)
        self.assertIn('dst=/copies,readonly',script)

    def test_symlinks_are_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);library=root/'library';copies=root/'copies';library.mkdir();copies.mkdir()
            (library/'linked.cbz').symlink_to(root/'outside.cbz')
            result=tool.review(library,copies)
            self.assertEqual(result['errors'],1)
            self.assertEqual(result['candidates'],[])


if __name__=='__main__':unittest.main()
