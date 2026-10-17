"""Installer safety checks: planning/errors never invoke Docker or write a NAS."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

INSTALLER=Path(__file__).resolve().parents[1]/'deploy/install-pilot.sh'

class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);shutil.copyfile(INSTALLER,self.root/'install-pilot.sh')
        (self.root/'images.ids').write_text('web=sha256:'+'a'*64+'\nlanraragi=sha256:'+'b'*64+'\n')
        self.before={path.name for path in self.root.iterdir()}
    def run_installer(self,*args):
        result=subprocess.run(['sh',str(self.root/'install-pilot.sh'),*args],capture_output=True,text=True)
        self.assertEqual({path.name for path in self.root.iterdir()},self.before)
        return result
    def test_plan_only_accepts_verified_profile_without_installation(self):
        result=self.run_installer('plan','/volume1/docker/library-studio','1026','100')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Plan only: no files, images or services changed.',result.stdout)
        self.assertIn('full fork build is NOT verified',result.stdout)
    def test_refuses_path_escape_existing_service_paths_and_invalid_ids(self):
        for root in ['/','/volume1/media','/volume1/docker/stash','/volume1/../docker/library-studio','/volumeX/docker/library-studio']:
            with self.subTest(root=root):self.assertNotEqual(self.run_installer('plan',root,'1026','100').returncode,0)
        for uid in ['','0','-1','1026;echo injected','2147483648']:
            with self.subTest(uid=uid):self.assertNotEqual(self.run_installer('plan','/volume1/docker/library-studio',uid,'100').returncode,0)
    def test_refuses_malformed_image_manifest_before_any_install(self):
        (self.root/'images.ids').write_text('web=not-reviewed:latest\nlanraragi=sha256:'+'b'*64+'\n')
        self.assertNotEqual(self.run_installer('plan','/volume1/docker/library-studio','1026','100').returncode,0)
    def test_install_cannot_start_from_an_unverified_volume_parent(self):
        # Impossible parent in the cloud; install exits before Docker/image/directory changes.
        result=self.run_installer('install','/volume987654321/docker/library-studio','1026','100')
        self.assertNotEqual(result.returncode,0)

class RecoveryTests(unittest.TestCase):
    def test_recovery_plan_does_not_require_or_mutate_a_nas(self):
        script=INSTALLER.with_name('resume-pilot.sh')
        result=subprocess.run(['sh',str(script),'plan','/volume1/docker/library-studio'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Plan only: no changes.',result.stdout)
        self.assertIn('No secret regeneration, data deletion or DSM changes.',result.stdout)

    def test_recovery_rejects_unrelated_paths_before_apply(self):
        script=INSTALLER.with_name('resume-pilot.sh')
        for root in ['/','/volume1/docker/stash','/volume1/../docker/library-studio','/volumeX/docker/library-studio']:
            with self.subTest(root=root):
                result=subprocess.run(['sh',str(script),'apply',root],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn('Own Compose backed up',result.stdout)


class DedicatedAccountTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        identity=self.root/'id'
        identity.write_text("""#!/bin/sh
if [ "$2" != library-studio ];then exit 99;fi
[ "${STUDIO_TEST_MISSING:-0}" = 0 ] || exit 1
case "$1" in
  -u) printf '%s\\n' "${STUDIO_TEST_UID:-1030}";;
  -g) printf '%s\\n' "${STUDIO_TEST_GID:-100}";;
  -G) printf '%s\\n' "${STUDIO_TEST_GROUPS:-100}";;
  -Gn) printf '%s\\n' "${STUDIO_TEST_NAMES:-users}";;
  *) exit 2;;
esac
""")
        identity.chmod(0o755)
        self.script=INSTALLER.with_name('check-service-account.sh')

    def check(self,*args,**values):
        before={path.name for path in self.root.iterdir()}
        result=subprocess.run(['sh',str(self.script),*args],capture_output=True,text=True,
                              env={**os.environ,'PATH':str(self.root)+os.pathsep+os.environ['PATH'],**values})
        self.assertEqual(before,{path.name for path in self.root.iterdir()})
        return result

    def test_preview_has_no_account_lookup_or_nas_changes(self):
        result=self.check('preview',STUDIO_TEST_MISSING='1')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('No account, ACL, files or services changed',result.stdout)

    def test_named_nonadministrator_service_identity_passes_without_source_access(self):
        result=self.check('check','1030','100')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('account=library-studio',result.stdout)
        self.assertIn('service_uid=1030',result.stdout)
        self.assertIn('source_access=not_checked',result.stdout)
        self.assertIn('nas_changes=none',result.stdout)

    def test_personal_root_admin_docker_and_malformed_identities_are_refused(self):
        for values in [dict(STUDIO_TEST_UID='1026'),dict(STUDIO_TEST_UID='0'),dict(STUDIO_TEST_GID='101'),
                       dict(STUDIO_TEST_GROUPS='100 101'),dict(STUDIO_TEST_GROUPS='100 0'),
                       dict(STUDIO_TEST_NAMES='users docker'),dict(STUDIO_TEST_NAMES='users administrators'),
                       dict(STUDIO_TEST_UID='1030;touch'),dict(STUDIO_TEST_GROUPS='100 --privileged'),
                       dict(STUDIO_TEST_UID='2147483648')]:
            with self.subTest(values=values):
                result=self.check('check',**values)
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn('identity_check=passed',result.stdout)

    def test_missing_account_and_mismatched_requested_ids_are_refused(self):
        self.assertNotEqual(self.check('check',STUDIO_TEST_MISSING='1').returncode,0)
        self.assertNotEqual(self.check('check','1026','100').returncode,0)
        self.assertNotEqual(self.check('install').returncode,0)

    def test_retired_personal_account_helpers_never_start_or_inspect_anything(self):
        for name in ('probe-folder-groups.sh','import-one-folder.sh'):
            self.script=INSTALLER.with_name(name)
            for mode in ('preview','diagnose','plan','run','import'):
                with self.subTest(script=name,mode=mode):
                    result=self.check(mode,'/volume1/Selected/Library')
                    self.assertNotEqual(result.returncode,0)
                    self.assertIn('personal-account execution is withdrawn',result.stderr)


if __name__=='__main__':unittest.main()
