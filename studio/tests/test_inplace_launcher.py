"""Pinned NAS migration bootstrap: fail closed before writes on plan/hash errors."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

class InPlaceLauncherTests(unittest.TestCase):
    def run_case(self, plan_status=0, corrupt=False):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source';source.mkdir()
            original=source/'keep.bin';original.write_bytes(b'generated sentinel')
            repo=Path(__file__).resolve().parents[2];deploy=repo/'studio/deploy'
            script=(deploy/'migrate-inplace-library.sh').read_text()
            script=script.replace('case "$source" in /volume[0-9]*/*)', 'case "$source" in '+str(source)+')')
            script=script.replace('number=${source#/volume};number=${number%%/*}', 'number=1')
            wrapper=root/'migrate.sh';wrapper.write_text(script)
            for name in ['archive_in_place.py','connect-inplace-library.sh']:
                expected=hashlib.sha256((deploy/name).read_bytes()).hexdigest()
                self.assertIn(expected,script)
            stubs=root/'bin';stubs.mkdir()
            (stubs/'id').write_text('#!/bin/sh\nprintf "0\\n"\n')
            (stubs/'curl').write_text('#!/usr/bin/env python3\nimport os,pathlib,sys\na=sys.argv[1:];target=pathlib.Path(a[a.index("-o")+1]);name=pathlib.Path(a[a.index("-o")-1]).name\ndata=(pathlib.Path(os.environ["TEST_DEPLOY"])/name).read_bytes()\nif os.environ["TEST_CORRUPT"]=="1":data+=b"wrong"\ntarget.write_bytes(data)\n')
            (stubs/'docker').write_text('#!/usr/bin/env python3\nimport json,os,pathlib,sys\na=sys.argv[1:];p=pathlib.Path(os.environ["TEST_LOG"]);p.write_text(p.read_text()+json.dumps(a)+"\\n")\nif "inspect" in a:print("library-studio-nas-pilot|studio|sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0|healthy")\nelse:\n print(json.dumps({"operation":"plan","errors":int(os.environ["TEST_STATUS"])}));sys.exit(int(os.environ["TEST_STATUS"]))\n')
            for p in stubs.iterdir():p.chmod(0o755)
            log=root/'calls';log.write_text('')
            env=dict(os.environ,PATH=str(stubs)+os.pathsep+os.environ['PATH'],TEST_DEPLOY=str(deploy),TEST_LOG=str(log),TEST_CORRUPT=str(int(corrupt)),TEST_STATUS=str(plan_status))
            result=subprocess.run(['sh',str(wrapper),'apply' if plan_status or corrupt else 'plan',str(source)],env=env,text=True,capture_output=True)
            self.assertEqual(original.read_bytes(),b'generated sentinel')
            self.assertEqual(list(source.iterdir()),[original])
            return result,log.read_text()

    def test_plan_error_blocks_connection_and_original_writes(self):
        result,log=self.run_case(plan_status=1)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(log.count('"run"'),1)
        self.assertIn('readonly',log)
        self.assertNotIn('content/NASOriginals',result.stdout)
        self.assertNotIn('--delete-source',log)

    def test_hash_error_blocks_even_plan_container(self):
        result,log=self.run_case(corrupt=True)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('"run"',log)

    def test_plan_never_connects_or_mounts_source_writable(self):
        result,log=self.run_case()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Plan only',result.stdout)
        self.assertEqual(log.count('"run"'),1)
        self.assertNotIn('--delete-source',log)

if __name__=='__main__':unittest.main()
