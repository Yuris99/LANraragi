"""Preview and rejected installs must never invoke Docker or modify a NAS."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'deploy/install-file-deletion.sh'


@unittest.skipUnless(shutil.which('sh'),'POSIX shell required')
class InstallationTests(unittest.TestCase):
    def test_preview_has_no_network_docker_or_filesystem_side_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ('docker','curl'):
                path=root/name;path.write_text('#!/bin/sh\ntouch "$INSTALL_TEST_MARKER"\nexit 99\n');path.chmod(0o755)
            marker=root/'unexpected-side-effect';env={**os.environ,'PATH':str(root)+os.pathsep+os.environ['PATH'],'INSTALL_TEST_MARKER':str(marker)}
            result=subprocess.run(['sh',str(SCRIPT),'preview'],cwd=root,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('Preview only',result.stdout)
            self.assertFalse(marker.exists())

    def test_bad_modes_and_unpinned_code_are_rejected_before_install(self):
        for args in [('apply',),('install',),('install','main','a'*64),('install','a'*40,'not-a-hash')]:
            with self.subTest(args=args):
                result=subprocess.run(['sh',str(SCRIPT),*args],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)


if __name__=='__main__':unittest.main()
