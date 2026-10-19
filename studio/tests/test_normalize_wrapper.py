"""Offline fixed NAS launcher regression; no NAS connection."""
from pathlib import Path
import subprocess
import unittest
import hashlib
import json


class WrapperTests(unittest.TestCase):
    def test_launcher_pins_exact_executor_parser_and_compatible_runtime(self):
        studio=Path(__file__).resolve().parents[1]
        text=(studio/'deploy/normalize-nas-library.sh').read_text()
        for name,variable in [('deploy/normalize-library-names.py','helper_sha'),('sources.py','sources_sha'),('deploy/runtime-manifest.sha256','manifest_sha')]:
            source=Path(__file__).parent/'fixtures/name-normalization-runtime.sha256' if name=='deploy/runtime-manifest.sha256' else studio/name
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertIn(variable+'='+digest,text)
        release=json.loads((Path(__file__).parent/'fixtures/name-normalization-release.json').read_text())
        self.assertIn('revision='+release['revision'],text)
        self.assertNotIn('CORE_REVISION',text)

    def test_preview_is_offline_and_apply_rejects_unsafe_or_unrelated_roots(self):
        script=Path(__file__).resolve().parents[1]/'deploy/normalize-nas-library.sh'
        result=subprocess.run(['sh',str(script),'preview','/volume1/generated-library','/volume1/docker/example-app','generated-check'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Preview only: no network, Docker, files or services changed.',result.stdout)
        for path in ['/','/volumeX/media','/volume1/../etc','/volume1/media,other','/volume1/media\nother']:
            self.assertNotEqual(subprocess.run(['sh',str(script),'apply',path,'/volume1/docker/example-app','generated-check'],capture_output=True).returncode,0)
        text=script.read_text()
        self.assertIn('--network none --read-only --memory 256m',text)
        self.assertIn('source|bind|false',text)
        self.assertNotIn('/volume1/docker/library-studio',text)
        self.assertNotIn('library-studio-nas-pilot',text)
        self.assertNotIn('1026:100',text)
        self.assertNotIn('--privileged',text)
        self.assertNotIn('docker.sock,dst=',text)


if __name__=='__main__':unittest.main()
