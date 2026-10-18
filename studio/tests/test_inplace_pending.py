"""An interrupted NAS proposal must not authorize an unknown/live connection."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PendingConnectionTests(unittest.TestCase):
    def check_rejected(self,case):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);root=folder/'library-studio';root.mkdir()
            control=Path(str(root)+'-deploy');control.mkdir(mode=0o700)
            source=folder/'source';source.mkdir();(source/'keep').write_bytes(b'generated')
            for name in ['compose.nas.yaml','compose.import.yaml','compose.pilot.yaml','.env.nas','compose.ui.yaml']:(root/name).write_text('# generated fixture\n')
            (control/'fixed').write_text('fixture')
            (control/'controller.sha256').write_text(hashlib.sha256(b'fixture').hexdigest()+'  fixed\n')
            overlay=root/'compose.archive.yaml'
            proposed={'services':{'lanraragi':{'environment':{'LRR_UID':'0','LRR_GID':'0'},'volumes':[{'type':'bind','source':str(source if case!='different' else folder/'other'),'target':'/home/koyomi/lanraragi/content/NASOriginals','read_only':True,'bind':{'create_host_path':False}}]}}}
            overlay.write_text(json.dumps(proposed));overlay.chmod(0o600);original=overlay.read_bytes()
            files=[root/n for n in ['compose.nas.yaml','compose.import.yaml','compose.pilot.yaml','.env.nas']]
            if case=='registered':files.append(overlay)
            (control/'configs.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p)+'\n' for p in files))
            if case=='enabled':(control/'enabled').touch()
            stubs=folder/'bin';stubs.mkdir()
            (stubs/'id').write_text('#!/bin/sh\nprintf "0\\n"\n');(stubs/'id').chmod(0o755)
            docker=stubs/'docker'
            docker.write_text('#!'+sys.executable+'\n'+'''import json,os,sys
a=sys.argv[1:];project="library-studio-nas-pilot"
web="sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0"
lrr="sha256:b76c792a43846f0755d0dadf98c8dd46123e8d244045e2f9b6834d9b45988957"
if "volume" in a:
 logical=a[-1].split(project+"_")[1];print("local|"+project+"|"+logical)
elif "inspect" in a:
 fmt=a[a.index("--format")+1]
 if "Health" in fmt:
  service="studio" if a[-1].endswith("studio-1") else "lanraragi"
  print(project+"|"+service+"|"+(web if service=="studio" else lrr)+"|healthy")
 elif "Config.User" in fmt:print("1026:100")
 elif "Mounts" in fmt:print("present" if os.environ["CASE"]=="live" else "")
 else:raise SystemExit(90)
elif "exec" in a:print("0" if os.environ["CASE"]=="root" else "1026")
elif "run" in a:
 for index,value in enumerate(a):
  if value=="--env":
   key,content=a[index+1].split("=",1);os.environ[key]=content
 exec(compile(a[a.index("-c")+1],"<pending-validator>","exec"))
else:raise SystemExit(91)
''');docker.chmod(0o755)
            text=(Path(__file__).resolve().parents[1]/'deploy/connect-inplace-library.sh').read_text()
            text=text.replace('root=/volume1/docker/library-studio','root='+str(root))
            text=text.replace('case "$source" in /volume[0-9]*/*)','case "$source" in '+str(source)+')')
            text=text.replace('number=${source#/volume};number=${number%%/*}','number=1')
            for mode in ['700','600']:text=text.replace('= 0:'+mode+' ]','= '+str(os.getuid())+':'+mode+' ]')
            text=text.replace('"$(stat -c \'%u\' "$overlay")" = 0','"$(stat -c \'%u\' "$overlay")" = '+str(os.getuid()))
            script=folder/'connect.sh';script.write_text(text)
            env=dict(os.environ,PATH=str(stubs)+os.pathsep+os.environ['PATH'],CASE=case)
            result=subprocess.run(['/bin/sh',str(script),'apply',str(source)],env=env,text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            expected_error={'different':'Pending overlay differs','live':'Source already attached','root':'unchanged nonroot reader','registered':'Existing registered connection','enabled':'enabled updates'}[case]
            self.assertIn(expected_error,result.stderr)
            self.assertEqual(overlay.read_bytes(),original)
            self.assertEqual((source/'keep').read_bytes(),b'generated')
            self.assertFalse(list(root.glob('archive-connection.*/compose.archive.unapplied.yaml')))
            self.assertEqual((control/'enabled').exists(),case=='enabled')
            self.assertFalse((control/'poll.lock').exists());self.assertFalse((root/'.studio-ui-update.lock').exists())

    def test_different_source_is_not_adopted(self):self.check_rejected('different')
    def test_live_mount_is_not_replaced(self):self.check_rejected('live')
    def test_root_reader_is_not_reconfigured(self):self.check_rejected('root')
    def test_registered_overlay_is_not_replaced(self):self.check_rejected('registered')
    def test_enabled_channel_is_not_assumed_interrupted(self):self.check_rejected('enabled')

if __name__=='__main__':unittest.main()
