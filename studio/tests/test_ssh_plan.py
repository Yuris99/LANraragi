"""Real OpenSSH config parsing with synthetic host keys; no daemon/listener."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy'))
from ssh_forwarding_plan import proposal,validate,effective

@unittest.skipUnless(shutil.which('sshd') and shutil.which('ssh-keygen'),'OpenSSH tools needed')
class SSHPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);key=root/'synthetic_host'
        subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True)
        self.original=root/'original';self.candidate=root/'candidate'
        self.base='HostKey '+str(key)+'\nPidFile '+str(root/'unused.pid')+'\nUsePAM no\nAllowTcpForwarding no\nPermitOpen any\n'
        self.original.write_text(self.base)
    def test_only_target_user_and_address_get_one_local_destination(self):
        self.candidate.write_text(proposal(self.base,'studio_test','192.0.2.50'))
        self.assertTrue(validate(self.original,self.candidate,'studio_test','192.0.2.50')['unrelated_contexts_unchanged'])
        target=effective(self.candidate,'studio_test','192.0.2.50')
        self.assertEqual(target['allowtcpforwarding'],'local')
        self.assertEqual(target['permitopen'],'127.0.0.1:43120')
    def test_earlier_matching_denial_stops_instead_of_changing_policy_globally(self):
        original=self.base+'\nMatch User studio_test\n    AllowTcpForwarding no\n'
        self.original.write_text(original);self.candidate.write_text(proposal(original,'studio_test','192.0.2.50'))
        with self.assertRaises(ValueError):validate(self.original,self.candidate,'studio_test','192.0.2.50')
    def test_blanket_disabling_stops_proposal(self):
        original=self.base+'DisableForwarding yes\n'
        self.original.write_text(original);self.candidate.write_text(proposal(original,'studio_test','192.0.2.50'))
        with self.assertRaises(ValueError):validate(self.original,self.candidate,'studio_test','192.0.2.50')
    def test_effective_validation_uses_actual_server_address(self):
        original=self.base+'\nMatch User studio_test LocalAddress 192.0.2.1\n    AllowTcpForwarding no\n'
        self.original.write_text(original);self.candidate.write_text(proposal(original,'studio_test','192.0.2.50'))
        with self.assertRaises(ValueError):validate(self.original,self.candidate,'studio_test','192.0.2.50',server='192.0.2.1',port=22)

    def test_wildcards_injection_and_duplicate_blocks_are_rejected(self):
        for user,address in [('studio*','192.0.2.50'),('studio\nMatch all','192.0.2.50'),('studio','192.0.2.0/24'),('studio','*')]:
            with self.subTest(user=user,address=address),self.assertRaises(ValueError):proposal(self.base,user,address)
        with self.assertRaises(ValueError):proposal(proposal(self.base,'studio','192.0.2.50'),'studio','192.0.2.50')

class SSHApplyGuardTests(unittest.TestCase):
    def run_script(self,*args):
        script=Path(__file__).resolve().parents[1]/'deploy/configure-tunnel.sh'
        return subprocess.run(['sh',str(script),*args],capture_output=True,text=True)
    def test_plan_only_has_exact_user_client_and_fixed_destination(self):
        result=self.run_script('plan','studio_test','192.0.2.50','192.0.2.1','22')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Match User studio_test Address 192.0.2.50',result.stdout)
        self.assertIn('PermitOpen 127.0.0.1:43120',result.stdout)
        self.assertIn('Plan only: no NAS changes.',result.stdout)
    def test_rejects_wildcards_root_and_multiline_scope_injection(self):
        for user,client in [('studio*','192.0.2.50'),('root','192.0.2.50'),('studio','192.0.2.0/24'),('studio','192.0.2.50\n192.0.2.51'),('studio\nMatch','192.0.2.50')]:
            with self.subTest(user=user,client=client):
                self.assertNotEqual(self.run_script('plan',user,client,'192.0.2.1','22').returncode,0)
    def test_rollback_rejects_other_directories_and_traversal(self):
        for path in ['/','/etc/ssh','/etc/ssh/.studio-tunnel.x/../other','/tmp/studio']:
            with self.subTest(path=path):self.assertNotEqual(self.run_script('rollback',path).returncode,0)
    @unittest.skipIf(__import__('os').getuid()==0,'Requires non-root execution to exercise guard')
    def test_apply_refuses_before_any_nas_config_write_without_root(self):
        result=self.run_script('apply','studio_test','192.0.2.50','192.0.2.1','22')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Use sudo',result.stderr)

if __name__=='__main__':unittest.main()
