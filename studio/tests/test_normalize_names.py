"""Generated-only real rename, interrupted recovery and rollback regression."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sources import filename_hints
spec=importlib.util.spec_from_file_location('normalize_names',Path(__file__).resolve().parents[1]/'deploy/normalize-library-names.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class NormalizeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'library';(self.root/'manga/sub').mkdir(parents=True)
        self.old=self.root/'manga/sub/[Artist] Generated [123456].cbz';self.old.write_bytes(b'generated archive bytes')
        self.workspace=Path(self.temp.name)/'private';self.workspace.mkdir()
        self.arcid=hashlib.sha1(self.old.read_bytes()).hexdigest()
        self.work={'id':'a'*32,'lrr_id':self.arcid,'archive_filename':self.old.stem,'title':self.old.stem,'artist':'Artist','local_number':17,'sources':[]}
    def plan(self):return module.prepare(self.root,[self.work])
    def proof(self,plan):return {'operation_id':plan['operation_id'],'verified':{i['lrr_id']:i['sha256'] for i in plan['items']}}
    def apply(self,plan,**kwargs):return module.apply(self.root,plan,self.proof(plan),self.workspace/'journal.json',**kwargs)

    def test_real_rename_preserves_bytes_inode_collection_and_unresolved_identity(self):
        plan=self.plan();before=self.old.stat();digest=hashlib.sha256(self.old.read_bytes()).hexdigest()
        self.assertEqual(plan['items'][0]['new'],'manga/sub/[Artist] Generated [U123456] [L17].cbz')
        self.assertEqual(self.apply(plan)['renamed'],1)
        target=self.root/plan['items'][0]['new'];self.assertFalse(self.old.exists())
        self.assertEqual(target.stat().st_ino,before.st_ino);self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),digest)
        self.assertEqual(self.apply(plan)['renamed'],0)
        hint=filename_hints(target.name);self.assertEqual(hint['title'],'Generated');self.assertEqual(hint['numbers'],[{'number':'123456','provider':None}])
        work={**self.work,'title':target.stem,'archive_filename':target.stem}
        self.assertEqual(module.prepare(self.root,[work])['unchanged'],1)
        self.assertEqual(self.apply(plan,rollback=True)['renamed'],1);self.assertEqual(self.old.stat().st_ino,before.st_ino)

    def test_interrupted_rename_and_interrupted_rollback_resume(self):
        plan=self.plan()
        def crash(stage,item):
            if stage=='after_rename':raise InterruptedError('generated interruption')
        with self.assertRaises(InterruptedError):self.apply(plan,hook=crash)
        self.assertEqual(self.apply(plan)['renamed'],0)
        with self.assertRaises(InterruptedError):self.apply(plan,rollback=True,hook=crash)
        self.assertEqual(self.apply(plan,rollback=True)['renamed'],0);self.assertTrue(self.old.exists())

    def test_changed_source_and_missing_backend_proof_prevent_changes(self):
        plan=self.plan()
        with self.assertRaises(ValueError):module.apply(self.root,plan,{'operation_id':plan['operation_id'],'verified':{}},self.workspace/'journal.json')
        self.old.write_bytes(b'changed original')
        with self.assertRaises(ValueError):self.apply(plan)
        self.assertTrue(self.old.exists())

    def test_existing_or_concurrent_destination_never_overwritten(self):
        plan=self.plan();target=self.root/plan['items'][0]['new']
        def race(stage,item):
            if stage=='before_rename':target.write_bytes(b'other file')
        with self.assertRaises(OSError):self.apply(plan,hook=race)
        self.assertEqual(target.read_bytes(),b'other file');self.assertTrue(self.old.exists())
        self.assertEqual(self.plan()['items'],[])

    def test_partial_id_collision_and_unconfirmed_artist_are_held(self):
        (self.old.parent/'other.cbz').write_bytes(self.old.read_bytes())
        self.assertEqual(self.plan()['items'],[])
        (self.old.parent/'other.cbz').unlink()
        self.work['artist']='';self.assertEqual(self.plan()['held'],{'artist_confirmation_required':1})

    def test_symlink_and_parent_escape_rejected_and_no_files_removed(self):
        plan=self.plan();plan['items'][0]['new']='../outside.cbz'
        with self.assertRaises(ValueError):self.apply(plan)
        self.assertTrue(self.old.exists())
        target=self.old.parent/'linked.cbz';target.symlink_to(self.old)
        self.assertEqual(self.plan()['held']['symlink_preserved'],1)

    def test_confirmed_provider_priority_and_source_details_untouched(self):
        self.work['sources']=[{'provider':'ehentai','external_id':'222222'},{'provider':'hitomi','external_id':'333333'}]
        before=json.dumps(self.work,sort_keys=True);plan=self.plan()
        self.assertIn('[H333333]',plan['items'][0]['new']);self.assertEqual(json.dumps(self.work,sort_keys=True),before)


if __name__=='__main__':unittest.main()
