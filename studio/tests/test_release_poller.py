"""Fixed NAS pull-controller boundaries with synthetic config/release payloads.

NAS path/root identity and Docker transport are fixture adapters. The actual
shell controller and its exact immutable-image JSON parser execute unchanged.
The separate UI-update Docker rehearsal covers real backup/recreate/rollback.
"""
import hashlib
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

DEPLOY=Path(__file__).resolve().parents[1]/'deploy'


class ReleasePollerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.root=self.base/'library-studio';self.root.mkdir()
        self.control=self.base/'library-studio-deploy';self.control.mkdir(mode=0o700)
        self.bin=self.base/'bin';self.bin.mkdir()
        text=(DEPLOY/'poll-studio-release.sh').read_text()
        text=text.replace('case "$control" in /volume*/docker/library-studio-deploy)',
                          'case "$control" in '+str(self.control)+')')
        text=text.replace('volume=${root%/docker/library-studio};number=${volume#/volume}',
                          'volume=/volume1;number=1')
        text=text.replace('= 0:700 ]','= '+str(os.getuid())+':700 ]')
        self.script=self.control/'poll.sh';self.script.write_text(text)
        helper=self.control/'update-studio-ui.sh'
        helper.write_text('''#!/bin/sh
set -eu
printf '%s\\n' "$*" >> calls
printf 'synthetic local helper output\\n'
[ "${FIXTURE_FAIL_UPDATE:-0}" != 1 ]
''')
        checks=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in [self.script,helper])
        (self.control/'controller.sha256').write_text(checks)
        checks=''
        for name in ['compose.nas.yaml','compose.import.yaml','compose.pilot.yaml','.env.nas']:
            path=self.root/name;path.write_text('synthetic-private-config-value\n')
            checks+=hashlib.sha256(path.read_bytes()).hexdigest()+'  '+str(path)+'\n'
        (self.control/'configs.sha256').write_text(checks)
        (self.control/'enabled').touch()
        self.release=self.base/'release.json'
        self.payload=dict(schema=1,enabled=True,generation=1,revision='a'*40,manifest_sha256='b'*64)
        self.release.write_text(json.dumps(self.payload))
        self.stub('id','#!/bin/sh\n[ "$1" = -u ] && printf "0\\n"\n')
        self.stub('curl','#!'+sys.executable+'\n'+'''
import os,shutil,sys
a=sys.argv[1:]
assert next(x for x in a if x.startswith('https://'))=='https://raw.githubusercontent.com/Yuris99/LANraragi/refs/heads/feature/library-studio/studio/deploy/nas-release.json'
assert '--max-filesize' in a and a[a.index('--max-filesize')+1]=='4096'
if os.environ.get('FIXTURE_NETWORK_FAIL')=='1':sys.exit(22)
shutil.copyfile(os.environ['FIXTURE_RELEASE'],a[a.index('-o')+1])
''')
        self.stub('docker','#!'+sys.executable+'\n'+'''
import subprocess,sys
a=sys.argv[1:]
assert a[0]=='--host=unix:///var/run/docker.sock' and a[1]=='run'
assert not any(x in a for x in ['--mount','-v','--privileged'])
for flag,value in [('--user','65534:65534'),('--network','none'),('--cap-drop','ALL'),('--security-opt','no-new-privileges:true')]:
 assert a[a.index(flag)+1]==value
assert '--read-only' in a and '--pull=never' in a
sys.exit(subprocess.run([sys.executable,'-c',a[a.index('-c')+1]],stdin=sys.stdin).returncode)
''')
        self.env={**os.environ,'PATH':str(self.bin)+os.pathsep+os.environ['PATH'],
                  'FIXTURE_RELEASE':str(self.release)}

    def stub(self,name,text):
        path=self.bin/name;path.write_text(text);path.chmod(0o755)

    def run_poller(self,*args,**values):
        result=subprocess.run(['sh',str(self.script),*args],env={**self.env,**values},
                              text=True,capture_output=True,timeout=15)
        self.assertNotIn('synthetic-private-config-value',result.stdout+result.stderr)
        return result

    def calls(self):
        path=self.control/'calls'
        return path.read_text().splitlines() if path.exists() else []

    def publish(self,**changes):
        self.payload.update(changes);self.release.write_text(json.dumps(self.payload))

    def test_success_duplicates_and_stale_generations_never_repeat_or_run_shell(self):
        result=self.run_poller('tick');self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('deployment=healthy',result.stdout)
        self.assertEqual(self.calls(),['apply-release '+str(self.root)+' '+'a'*40+' '+'b'*64])
        self.assertFalse((self.control/'poll.lock').exists())
        self.assertEqual(self.run_poller('tick').returncode,0)
        self.publish(revision='c'*40)  # changed bytes cannot reuse a generation
        self.assertEqual(self.run_poller('tick').returncode,0)
        self.assertEqual(len(self.calls()),1)
        self.publish(generation=2)
        self.assertEqual(self.run_poller('tick').returncode,0)
        self.assertEqual(len(self.calls()),2)
        self.publish(generation=1)
        self.assertEqual(self.run_poller('tick').returncode,0)
        self.assertEqual(len(self.calls()),2)

    def test_remote_disable_and_nas_local_revocation(self):
        self.publish(enabled=False)
        self.assertEqual(self.run_poller('tick').returncode,0)
        self.assertFalse((self.control/'attempted').exists())
        self.assertEqual(self.run_poller('disable').returncode,0)
        self.publish(enabled=True)
        self.assertEqual(self.run_poller('tick').returncode,0)
        self.assertEqual(self.calls(),[])
        self.assertIn('local_updates=disabled',self.run_poller('status').stdout)
        self.assertEqual(self.run_poller('enable').returncode,0)
        self.assertEqual(self.run_poller('tick').returncode,0)
        self.assertEqual(len(self.calls()),1)

    def test_failure_quarantined_across_restart_until_new_generation(self):
        result=self.run_poller('tick',FIXTURE_FAIL_UPDATE='1')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('deployment=failed_or_interrupted',result.stdout)
        self.assertEqual(self.run_poller('tick').returncode,0)
        self.assertEqual(len(self.calls()),1)
        self.publish(generation=2)
        self.assertEqual(self.run_poller('tick').returncode,0)
        self.assertEqual(len(self.calls()),2)

    def test_network_failure_is_retryable_without_attempt_or_restart(self):
        self.assertNotEqual(self.run_poller('tick',FIXTURE_NETWORK_FAIL='1').returncode,0)
        self.assertEqual(self.calls(),[])
        self.assertFalse((self.control/'attempted').exists())
        self.assertFalse((self.control/'poll.lock').exists())
        self.assertEqual(self.run_poller('tick').returncode,0)

    def test_frozen_config_and_controller_tampering_fail_closed(self):
        env=self.root/'.env.nas';before=env.read_text();env.write_text(before+'changed\n')
        self.assertNotEqual(self.run_poller('tick').returncode,0)
        env.write_text(before)
        with (self.control/'update-studio-ui.sh').open('a') as stream:stream.write('echo changed\n')
        self.assertNotEqual(self.run_poller('tick').returncode,0)
        self.assertEqual(self.calls(),[])

    def test_malformed_request_cannot_supply_commands_paths_or_other_services(self):
        original=dict(self.payload)
        for changes in [dict(command='touch /tmp/injected'),dict(root='/volume1/docker/stash'),
                        dict(url='https://example.invalid/other'),dict(revision='a'*39+';'),
                        dict(revision='../../etc/passwd'),dict(manifest_sha256='b'*63+'\n'),
                        dict(schema=True),dict(enabled=1),dict(generation=True),dict(generation=0),
                        dict(generation=2147483648)]:
            with self.subTest(changes=changes):
                self.release.write_text(json.dumps({**original,**changes}))
                self.assertNotEqual(self.run_poller('tick').returncode,0)
                self.assertEqual(self.calls(),[])
                self.assertFalse((self.control/'attempted').exists())
        self.release.write_text('{"enabled":true,"enabled":false}')
        self.assertNotEqual(self.run_poller('tick').returncode,0)
        self.release.write_text(' '*4097)
        self.assertNotEqual(self.run_poller('tick').returncode,0)

    def test_live_lock_cannot_be_stolen_and_dead_lock_has_local_recovery(self):
        lock=self.control/'poll.lock';lock.mkdir()
        (lock/'pid').write_text(str(os.getpid()))
        self.assertEqual(self.run_poller('tick').returncode,75)
        self.assertNotEqual(self.run_poller('recover-locks').returncode,0)
        self.assertTrue(lock.exists())
        (lock/'pid').write_text('2147483647')
        self.assertEqual(self.run_poller('recover-locks').returncode,0)
        self.assertFalse(lock.exists())
        self.assertEqual(self.calls(),[])


class ReleaseInstallerGuardTests(unittest.TestCase):
    def test_installer_pins_exact_controller_bytes(self):
        source=(DEPLOY/'install-release-poller.sh').read_text()
        self.assertRegex(source,r'(?m)^revision=[0-9a-f]{40}$')
        for variable,name in [('poll_sha','poll-studio-release.sh'),('updater_sha','update-studio-ui.sh')]:
            digest=hashlib.sha256((DEPLOY/name).read_bytes()).hexdigest()
            self.assertIn(variable+'='+digest,source)

    def test_installer_creates_only_new_control_files_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);root=base/'library-studio';root.mkdir()
            control=base/'library-studio-deploy'
            for name in ['compose.nas.yaml','compose.import.yaml','compose.pilot.yaml','.env.nas']:
                (root/name).write_text('synthetic-private-config-value\n')
            before={p.name:p.read_bytes() for p in root.iterdir()}
            text=(DEPLOY/'install-release-poller.sh').read_text()
            text=text.replace('case "$root" in /volume*/docker/library-studio)','case "$root" in '+str(root)+')')
            text=text.replace('volume=${root%/docker/library-studio};number=${volume#/volume}',
                              'volume='+str(base)+';number=1')
            text=text.replace('"$volume/docker"','"$volume"')
            installer=base/'installer.sh';installer.write_text(text)
            stubs=base/'bin';stubs.mkdir()
            (stubs/'id').write_text('#!/bin/sh\n[ "$1" = -u ] && printf "0\\n"\n')
            (stubs/'id').chmod(0o755)
            (stubs/'curl').write_text('#!'+sys.executable+'\n'+
                'from pathlib import Path\nimport re,shutil,sys\n'+
                'a=sys.argv[1:];url=next(x for x in a if x.startswith("https://"))\n'+
                'assert re.fullmatch(r"https://raw.githubusercontent.com/Yuris99/LANraragi/[0-9a-f]{40}/studio/deploy/(poll-studio-release|update-studio-ui)\\.sh",url)\n'+
                'shutil.copyfile(Path('+repr(str(DEPLOY))+')/url.rsplit("/",1)[1],a[a.index("-o")+1])\n')
            (stubs/'curl').chmod(0o755)
            env={**os.environ,'PATH':str(stubs)+os.pathsep+os.environ['PATH']}
            def run():return subprocess.run(['sh',str(installer),'install',str(root)],env=env,text=True,capture_output=True)
            result=run();self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('no scheduler created',result.stdout)
            self.assertNotIn('synthetic-private-config-value',result.stdout+result.stderr)
            self.assertEqual(control.stat().st_mode&0o777,0o700)
            self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()},before)
            self.assertEqual((control/'poll.sh').read_bytes(),(DEPLOY/'poll-studio-release.sh').read_bytes())
            self.assertTrue((control/'enabled').is_file())
            self.assertNotEqual(run().returncode,0)

    def test_real_compose_scope_parser_refuses_expanded_container_privileges(self):
        source=(DEPLOY/'update-studio-ui.sh').read_text()
        parser=source[source.index('import json,os,sys\nc=json.load'):]
        parser=parser[:parser.index('print("compose_scope=verified")')]+ 'print("compose_scope=verified")'
        root='/volume1/docker/library-studio'
        env={**os.environ,'EXPECTED_CODE':'','EXPECTED_ROOT':root,'EXPECTED_USER':'1026:100','EXPECTED_IMAGE':'sha256:'+'a'*64}
        service=dict(image=env['EXPECTED_IMAGE'],user='1026:100',mem_limit='268435456',
                     ports=[dict(host_ip='127.0.0.1',published='43120',target=8090)],
                     volumes=[dict(target='/data',type='volume',source='studio-data'),
                              dict(target='/uploads',type='volume',source='studio-uploads'),
                              dict(target='/inbox',type='bind',source=root+'/inbox',read_only=True)])
        document=dict(services=dict(studio=service),volumes={n:dict(name='library-studio-nas-pilot_'+n)
                                                           for n in ['studio-data','studio-uploads']})
        def check(data,settings=env):
            return subprocess.run([sys.executable,'-c',parser],env=settings,input=json.dumps(data),
                                  text=True,capture_output=True).returncode
        self.assertEqual(check(document),0)
        changed=copy.deepcopy(document);changed['services']['studio']['mem_limit']=268435456
        self.assertEqual(check(changed),0)  # Compose versions emit string or integer
        mutations=[lambda s:s.update(privileged=True),lambda s:s.update(user='0:0'),
                   lambda s:s.update(image='different:latest'),lambda s:s.update(cap_add=['SYS_ADMIN']),
                   lambda s:s.update(group_add=['101']),lambda s:s.update(network_mode='host'),
                   lambda s:s['ports'][0].update(host_ip='0.0.0.0'),
                   lambda s:s['volumes'].append(dict(target='/var/run/docker.sock',type='bind',source='/var/run/docker.sock')),
                   lambda s:s['volumes'][2].update(source='/volume1/Originals'),
                   lambda s:s['volumes'][2].update(read_only=False),
                   lambda s:s['volumes'][0].update(source='stash-data')]
        for mutate in mutations:
            changed=copy.deepcopy(document);mutate(changed['services']['studio'])
            self.assertNotEqual(check(changed),0)

    def test_preview_and_invalid_roots_have_no_side_effects(self):
        script=DEPLOY/'install-release-poller.sh'
        result=subprocess.run(['sh',str(script),'preview'],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Preview only: no network, Docker or NAS changes',result.stdout)
        for root in ['/','/volume1/docker/stash','/volume1/../docker/library-studio','/volumeX/docker/library-studio']:
            result=subprocess.run(['sh',str(script),'install',root],text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)

    def test_updater_refuses_untrusted_release_arguments_before_privilege_or_writes(self):
        script=DEPLOY/'update-studio-ui.sh'
        for extra in [[],['a'*40],['../../other','b'*64],['a'*40,'b'*63+';'],['a'*40,'b'*64,'command']]:
            result=subprocess.run(['sh',str(script),'apply-release','/volume1/docker/library-studio',*extra],
                                  text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('Apply:',result.stdout)


if __name__=='__main__':unittest.main()
