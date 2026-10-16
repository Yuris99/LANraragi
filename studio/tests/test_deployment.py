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


class FolderGroupProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        identity=self.root/'id'
        identity.write_text('#!/bin/sh\ncase "$1" in -u) printf "%s\\n" "${STUDIO_TEST_UID:-1026}";; -g) printf "100\\n";; -G) printf "%s\\n" "${STUDIO_TEST_GROUPS:-100 101}";; *) exit 2;; esac\n')
        identity.chmod(0o755)
        self.script=INSTALLER.with_name('probe-folder-groups.sh')

    def probe(self,*args,**values):
        before={path.name for path in self.root.iterdir()}
        result=subprocess.run(['sh',str(self.script),*args],capture_output=True,text=True,
                              env={**os.environ,'PATH':str(self.root)+os.pathsep+os.environ['PATH'],**values})
        self.assertEqual(before,{path.name for path in self.root.iterdir()})
        return result

    def test_preview_uses_only_current_account_memberships_without_nas_mutation(self):
        result=self.probe('preview','/volume1/Selected Share/Library')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Existing NAS account groups: 100 101',result.stdout)
        self.assertIn('Preview only: no downloads, containers or NAS changes.',result.stdout)

    def test_root_execution_import_and_malformed_groups_stop_before_actions(self):
        result=self.probe('preview','/volume1/Selected/Library',STUDIO_TEST_UID='0')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('not with sudo sh',result.stderr)
        for group in ['100 101;touch','100 --privileged','100 2147483648',' ','']:
            with self.subTest(group=group):
                self.assertNotEqual(self.probe('preview','/volume1/Selected/Library',STUDIO_TEST_GROUPS=group or 'invalid').returncode,0)
        self.assertNotEqual(self.probe('import','/volume1/Selected/Library').returncode,0)

    def test_bad_source_or_missing_source_stops_without_downloads_or_containers(self):
        for source in ['/','/volume1','/volumeX/Selected/Library','/volume1/../other','/volume1/Selected,readonly=false',
                       '/volume1/Selected\nother','/volume1/Selected\rother']:
            with self.subTest(source=source):self.assertNotEqual(self.probe('preview',source).returncode,0)
        result=self.probe('diagnose','/volume987654321/Selected/Library')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('no container started',result.stderr)

if __name__=='__main__':unittest.main()
