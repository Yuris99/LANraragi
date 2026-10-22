"""Exercise frozen service controller with generated files and mocked Docker/network."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
spec = importlib.util.spec_from_file_location("service_release", DEPLOY / "service-release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.request = json.loads((DEPLOY / "nas-services.json").read_text())

    def test_valid_and_every_source_hash(self):
        self.assertEqual(release.parse(json.dumps(self.request)), self.request)
        for name, digest in self.request["files"].items():
            source=subprocess.check_output(['git','show',self.request['revision']+':studio/'+name],cwd=DEPLOY)
            self.assertEqual(hashlib.sha256(source).hexdigest(), digest)

    def test_arbitrary_commands_paths_and_duplicate_fields_rejected(self):
        for field, value in (("command", "sh"), ("image", "unreviewed"), ("root", "/other")):
            r = {**self.request, field: value}
            with self.assertRaises(ValueError): release.parse(json.dumps(r))
        for field, value in (("generation", True), ("worker", 1), ("revision", "x/../../")):
            with self.assertRaises(ValueError): release.parse(json.dumps({**self.request, field: value}))
        r = copy.deepcopy(self.request);r["files"]["../../Dockerfile"] = "0"*64
        with self.assertRaises(ValueError): release.parse(json.dumps(r))
        with self.assertRaises(ValueError): release.parse('{"schema":1,' + json.dumps(self.request)[1:])
        with self.assertRaises(ValueError): release.parse(" " * 4097)

    def test_frozen_recipes_have_no_host_socket_or_cpu_quota(self):
        result = subprocess.run(["sha256sum", "-c", "service-controller.sha256"], cwd=DEPLOY, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("compose.login.yaml", "compose.worker-sessions.yaml"):
            source = (DEPLOY / "service-recipes" / name).read_text()
            self.assertEqual(source,(DEPLOY.parent/name).read_text())
            for forbidden in ("docker.sock", "privileged:", "cpus:", "ports:", "/volume1/"):
                self.assertNotIn(forbidden, source)
        self.assertEqual((DEPLOY/'service-recipes/deploy/install-site-login.sh').read_bytes(),(DEPLOY/'install-site-login.sh').read_bytes())


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.control = self.root / "library-studio-deploy"
        self.control.mkdir(mode=0o700);self.bin = self.root / "bin";self.bin.mkdir()
        self.remote = self.root / "remote";self.remote.mkdir()
        self.env = {**os.environ, "PATH":str(self.bin)+os.pathsep+os.environ["PATH"],
                    "TEST_ROOT":str(self.root), "TEST_PYTHON":sys.executable}
        script = (DEPLOY / "poll-studio-services.sh").read_text().replace("/volume*/docker/library-studio)", str(self.root / "library-studio") + ")")
        script = script.replace('[ "$(id -u)" -eq 0 ]', '[ "$(id -u)" -eq '+str(os.getuid())+' ]').replace('= 0:700 ]', '= '+str(os.getuid())+':700 ]')
        (self.control / "poll-studio-services.sh").write_text(script)
        shutil.copy(DEPLOY / "service-release.py", self.control)
        recipes = self.control / "service-recipes";shutil.copytree(DEPLOY / "service-recipes", recipes)
        (recipes / "deploy/install-site-login.sh").write_text('#!/bin/sh\nset -eu\nprintf "%s\\n" "$1" >> "$TEST_ROOT/actions"\n[ ! -e "$TEST_ROOT/fail_install" ]\n')
        (self.control / "enabled").touch()
        (self.control / "fixture.config").write_text('generated')
        (self.control / "configs.sha256").write_text(hashlib.sha256(b'generated').hexdigest()+'  fixture.config\n')
        self.freeze()
        request = json.loads((DEPLOY / "nas-services.json").read_text())
        for name in release.FILES:
            source=subprocess.check_output(['git','show',request['revision']+':studio/'+name],cwd=DEPLOY)
            (self.remote/name).write_bytes(source)
        (self.remote / "nas-services.json").write_text(json.dumps(request))
        self.write_tool("curl", '''import os,pathlib,sys
r=pathlib.Path(os.environ['TEST_ROOT']); args=sys.argv[1:]
url=next(a for a in args if a.startswith('https://'));name=url.rsplit('/',1)[1]
if (r/'fail_fetch').exists():sys.exit(22)
pathlib.Path(args[args.index('-o')+1]).write_bytes((r/'remote'/name).read_bytes())
''')
        self.write_tool("docker", '''import json,os,pathlib,subprocess,sys
r=pathlib.Path(os.environ['TEST_ROOT']);a=sys.argv[1:]
with (r/'docker_calls').open('a') as f:f.write(json.dumps(a)+'\\n')
if 'run' in a:
 assert '--network' in a and a[a.index('--network')+1]=='none'
 assert not any('docker.sock:' in x for x in a)
 sys.exit(subprocess.call([os.environ['TEST_PYTHON'],'-c',a[a.index('-c')+1]]))
if 'build' in a and (r/'fail_build').exists():sys.exit(17)
if 'inspect' in a:print('sha256:'+'a'*64)
''')

    def write_tool(self, name, body):
        path=self.bin/name;path.write_text('#!'+sys.executable+'\n'+body);path.chmod(0o755)

    def freeze(self):
        paths=[p for p in self.control.rglob('*') if p.is_file() and p.name not in ('controller.sha256','configs.sha256','enabled')]
        (self.control/'controller.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(self.control))+'\n' for p in paths))

    def tick(self):
        return subprocess.run(['sh',str(self.control/'poll-studio-services.sh')],env=self.env,capture_output=True,text=True)

    def test_success_worker_once_stale_generation_and_local_revoke(self):
        r=self.tick();self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('services=healthy',(self.control/'services.result').read_text())
        self.assertEqual((self.root/'actions').read_text().splitlines(),['update-login','start-worker'])
        self.assertEqual(self.tick().returncode,0)
        self.assertEqual(len((self.root/'actions').read_text().splitlines()),2)
        (self.control/'enabled').unlink();(self.root/'fail_fetch').touch()
        self.assertEqual(self.tick().returncode,0)

    def test_failed_build_stops_before_install_and_quarantines(self):
        (self.root/'fail_build').touch();r=self.tick()
        self.assertNotEqual(r.returncode,0)
        self.assertFalse((self.root/'actions').exists())
        self.assertIn('services=failed_or_interrupted',(self.control/'services.result').read_text())
        (self.root/'fail_build').unlink();self.assertEqual(self.tick().returncode,0)
        self.assertFalse((self.root/'actions').exists())

    def test_hash_mismatch_never_builds_or_mutates(self):
        (self.remote/'worker.py').write_text('modified')
        self.assertNotEqual(self.tick().returncode,0)
        self.assertFalse((self.control/'services.attempted').exists())
        self.assertNotIn('build',(self.root/'docker_calls').read_text())

    def test_network_failure_before_attempt_can_retry(self):
        (self.root/'fail_fetch').touch();self.assertNotEqual(self.tick().returncode,0)
        self.assertFalse((self.control/'services.attempted').exists())
        (self.root/'fail_fetch').unlink();self.assertEqual(self.tick().returncode,0)

    def test_install_failure_does_not_start_worker(self):
        (self.root/'fail_install').touch();self.assertNotEqual(self.tick().returncode,0)
        self.assertEqual((self.root/'actions').read_text().splitlines(),['update-login'])
        self.assertIn('failed_or_interrupted',(self.control/'services.result').read_text())

    def test_login_only_does_not_start_worker(self):
        p=self.remote/'nas-services.json';r=json.loads(p.read_text());r['worker']=False;p.write_text(json.dumps(r))
        self.assertEqual(self.tick().returncode,0)
        self.assertEqual((self.root/'actions').read_text().splitlines(),['update-login'])

    def test_live_lock_and_frozen_code_tampering_stop(self):
        (self.control/'services.lock').mkdir()
        self.assertEqual(self.tick().returncode,75)
        (self.control/'services.lock').rmdir()
        (self.control/'service-release.py').write_text('changed')
        self.assertNotEqual(self.tick().returncode,0)
        self.assertFalse((self.root/'docker_calls').exists())

    def bootstrap_fixture(self):
        for name in ('service-recipes','poll-studio-services.sh','service-release.py'):
            path=self.control/name
            if path.is_dir():shutil.rmtree(path)
            else:path.unlink()
        legacy=b'#!/bin/sh\nprintf "deployment=legacy_fixture\\n"\n'
        (self.control/'poll.sh').write_bytes(legacy)
        (self.control/'update-studio-ui.sh').write_text('#!/bin/sh\nexit 0\n')
        self.freeze()
        for line in (DEPLOY/'service-controller.sha256').read_text().splitlines():
            _,name=line.split('  ')
            shutil.copy(DEPLOY/name,self.remote/Path(name).name)
        shutil.copy(DEPLOY/'service-controller.sha256',self.remote)
        script=(DEPLOY/'install-service-channel.sh').read_text().replace('/volume*/docker/library-studio)',str(self.root/'library-studio')+')')
        script=script.replace('[ "$(id -u)" -eq 0 ]','[ "$(id -u)" -eq '+str(os.getuid())+' ]').replace('= 0:700 ]','= '+str(os.getuid())+':700 ]')
        installer=self.root/'install.sh';installer.write_text(script)
        return installer,legacy

    def install_extension(self, installer, digest):
        return subprocess.run(['sh',str(installer),str(self.root/'library-studio'),'a'*40,digest,'install'],env=self.env,capture_output=True,text=True)

    def test_bootstrap_preserves_scheduled_path_and_legacy_and_refuses_reinstall(self):
        installer,legacy=self.bootstrap_fixture()
        digest=hashlib.sha256((DEPLOY/'service-controller.sha256').read_bytes()).hexdigest()
        result=self.install_extension(installer,digest);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((self.control/'poll-app-legacy.sh').read_bytes(),legacy)
        self.assertEqual((self.control/'before-service-channel/poll.sh').read_bytes(),legacy)
        status=subprocess.run(['sh',str(self.control/'poll.sh'),'status'],env=self.env,capture_output=True,text=True)
        self.assertEqual(status.returncode,0,status.stderr)
        self.assertIn('deployment=legacy_fixture',status.stdout)
        self.assertIn('services=not_attempted',status.stdout)
        self.assertNotEqual(self.install_extension(installer,digest).returncode,0)

    def test_bootstrap_rejects_manifest_before_replacing_existing_controller(self):
        installer,legacy=self.bootstrap_fixture()
        self.assertNotEqual(self.install_extension(installer,'0'*64).returncode,0)
        self.assertEqual((self.control/'poll.sh').read_bytes(),legacy)
        self.assertFalse((self.control/'poll-app-legacy.sh').exists())
        self.assertFalse((self.control/'poll.lock').exists())


class LoginUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.app=self.root/'app';self.app.mkdir()
        downloads=self.app/'library/downloads';downloads.mkdir(parents=True)
        (self.app/'.env.nas').write_text('STUDIO_LIBRARY='+str(downloads.parent)+'\nSTUDIO_DOWNLOADS='+str(downloads)+'\n')
        studio=self.root/'studio';(studio/'deploy').mkdir(parents=True)
        for name in ('compose.login.yaml','compose.worker-sessions.yaml'):shutil.copy(DEPLOY.parent/name,studio)
        script=(DEPLOY/'install-site-login.sh').read_text().replace('/volume*/docker/*)',str(self.app)+')')
        script=script.replace('[ "$(id -u)" -eq 0 ]','[ "$(id -u)" -eq '+str(os.getuid())+' ]')
        self.script=studio/'deploy/install-site-login.sh';self.script.write_text(script)
        self.bin=self.root/'bin';self.bin.mkdir()
        self.env={**os.environ,'PATH':str(self.bin)+os.pathsep+os.environ['PATH'],'TEST_ROOT':str(self.root)}
        tool=self.bin/'docker';tool.write_text('#!'+sys.executable+'''\nimport os,pathlib,sys
r=pathlib.Path(os.environ['TEST_ROOT']);a=sys.argv[1:]
if 'volume' in a:print('local|fixture|studio-data')
elif 'network' in a:print('fixture')
elif 'image' in a:print(a[-1])
elif 'inspect' in a:
 print('volume|fixture_studio-data|true' if 'Mounts' in ' '.join(a) else 'fixture|studio|healthy')
elif 'compose' in a:
 with (r/'calls').open('a') as f:f.write((r/'app/site-login-deploy/.env.images').read_text().splitlines()[0]+'\\n')
elif 'exec' in a and (r/'rpc_fail').exists():sys.exit(1)
''');tool.chmod(0o755)
        sleep=self.bin/'sleep';sleep.write_text('#!/bin/sh\nexit 0\n');sleep.chmod(0o755)
        self.old='sha256:'+'a'*64;self.new='sha256:'+'b'*64

    def run_helper(self, mode, image):
        return subprocess.run(['sh',str(self.script),mode,str(self.app),'fixture',image,image],env=self.env,capture_output=True,text=True)

    def test_update_health_failure_restores_exact_previous_image_and_hashes(self):
        self.assertEqual(self.run_helper('apply-login',self.old).returncode,0)
        dest=self.app/'site-login-deploy';before=(dest/'.env.images').read_bytes();checks=(dest/'installation.sha256').read_bytes()
        (self.root/'rpc_fail').touch();r=self.run_helper('update-login',self.new)
        self.assertNotEqual(r.returncode,0,r.stderr)
        self.assertEqual((dest/'.env.images').read_bytes(),before)
        self.assertEqual((dest/'installation.sha256').read_bytes(),checks)
        self.assertTrue((self.root/'calls').read_text().splitlines()[-1].endswith(self.old))

    def test_healthy_update_retains_previous_configuration_for_recovery(self):
        self.assertEqual(self.run_helper('apply-login',self.old).returncode,0)
        r=self.run_helper('update-login',self.new);self.assertEqual(r.returncode,0,r.stderr)
        dest=self.app/'site-login-deploy'
        self.assertIn(self.new,(dest/'.env.images').read_text())
        self.assertIn(self.old,(dest/'.env.images.previous').read_text())
        self.assertEqual(subprocess.run(['sha256sum','-c','installation.sha256'],cwd=dest,capture_output=True).returncode,0)


if __name__ == '__main__':unittest.main()
