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

    def test_unsupported_compatibility_limits_stop_before_download_or_container_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);marker=root/'unexpected-mutation'
            scripts={
                'id':'#!/bin/sh\nprintf "0\\n"\n',
                'readlink':'#!/bin/sh\nprintf "%s\\n" "$2"\n',
                'curl':'#!/bin/sh\ntouch "$INSTALL_TEST_MARKER"\nexit 99\n',
                'docker':'''#!/bin/sh
case "$*" in
  *"inspect --type container library-studio-file-deletion") exit 1;;
  *"inspect --type container --format"*"library-studio-nas-pilot-studio-1") printf 'library-studio-nas-pilot|studio|healthy\\n';;
  *"info --format"*) printf '%s\\n' "$INSTALL_TEST_LIMITS";;
  *) touch "$INSTALL_TEST_MARKER";exit 99;;
esac
'''}
            for name,body in scripts.items():
                path=root/name;path.write_text(body);path.chmod(0o755)
            for flags in ['false|true|true|true','true|false|true|true','true|true|false|true','true|true|true|false']:
                env={**os.environ,'PATH':str(root)+os.pathsep+os.environ['PATH'],'INSTALL_TEST_MARKER':str(marker),'INSTALL_TEST_LIMITS':flags}
                result=subprocess.run(['sh',str(SCRIPT),'install','a'*40,'b'*64],env=env,capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0);self.assertIn('Required compatibility limits unavailable',result.stderr)
                self.assertFalse(marker.exists())


if __name__=='__main__':unittest.main()
