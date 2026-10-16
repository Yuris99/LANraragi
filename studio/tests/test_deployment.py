"""Installer safety checks: planning/errors never invoke Docker or write a NAS."""
from pathlib import Path
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

if __name__=='__main__':unittest.main()
