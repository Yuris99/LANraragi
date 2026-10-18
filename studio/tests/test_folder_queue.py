"""Bounded folder jobs: permissions, restart accounting, receipts and restore."""
import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from folder_importer import FolderImporter,queue_import
from server import Studio,make_server
from store import Store
from uploads import Uploads
from backup import copy_database
from make_synthetic import create_fixture


class FolderQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source'
        (self.source/'manga').mkdir(parents=True);(self.source/'images').mkdir()
        with zipfile.ZipFile(create_fixture(self.root/'generated')) as archive:png=archive.read('01.png')
        for i in range(12):
            book=self.source/'manga'/f'Generated {i:02}';book.mkdir()
            (book/'1.png').write_bytes(png)
        for p in [self.source,*self.source.rglob('*')]:os.utime(p,(time.time()-120,)*2)
        self.store=Store(self.root/'studio.db');self.destination=self.root/'uploads'

    def tick(self):return queue_import(self.source,['manga','images'],self.store.path,self.destination,require_read_only=False)
    def request(self,key='a'*32,collections=None):return self.store.queue_folder_import(collections or ['manga'],key)

    def test_no_worker_no_request_and_invalid_scope_or_limit(self):
        with self.assertRaises(ValueError):self.request()
        self.assertEqual(self.tick(),{'worker':'ready'})
        for value in [['../other'],['manga','manga'],[{}],['/manga']]:
            with self.assertRaises(ValueError):self.request(collections=value)
        self.assertEqual(self.store.folder_status()['jobs'],[])

    def test_ten_then_two_copies_dedup_and_source_bytes_unchanged(self):
        before={p.relative_to(self.source):p.read_bytes() for p in self.source.rglob('*.png')}
        self.tick();self.request();self.assertEqual(self.request()['id'],self.request()['id'])
        with self.assertRaises(ValueError):self.request('b'*32)
        self.assertEqual(self.tick()['worker'],'complete')
        status=self.store.folder_status();self.assertEqual(status['jobs'][0]['imported'],10)
        self.assertEqual(len(Uploads(self.store,self.destination).list()),10)
        self.request('b'*32);self.tick()
        self.assertEqual(len(Uploads(self.store,self.destination).list()),12)
        self.request('c'*32);self.tick()
        self.assertEqual(self.store.folder_status()['jobs'][0]['imported'],0)
        self.assertEqual(len(Uploads(self.store,self.destination).list()),12)
        self.assertEqual(before,{p.relative_to(self.source):p.read_bytes() for p in self.source.rglob('*.png')})
        self.assertEqual(len(list(self.root.glob('folder-import-backups/*.db'))),3)

    def test_crash_after_third_receipt_resumes_same_request_with_max_ten_total(self):
        self.tick();self.request()
        original=FolderImporter.package;count=0
        def crash(importer,*args):
            nonlocal count
            result=original(importer,*args);count+=1
            if count==3:raise KeyboardInterrupt('synthetic power loss')
            return result
        with patch.object(FolderImporter,'package',crash):
            with self.assertRaises(KeyboardInterrupt):self.tick()
        self.assertEqual(self.store.folder_status()['jobs'][0]['imported'],3)
        self.assertEqual(self.store.folder_status()['jobs'][0]['state'],'running')
        self.tick();row=self.store.folder_status()['jobs'][0]
        self.assertEqual((row['state'],row['imported']),('complete',10))
        self.assertEqual(len(Uploads(self.store,self.destination).list()),10)

    def test_receipt_and_job_count_roll_back_together_on_lost_lease(self):
        self.tick();job=self.request()
        original=FolderImporter.package
        def invalidate(importer,*args):
            with self.store.db() as db:db.execute("UPDATE folder_jobs SET lease='changed' WHERE id=?",(job['id'],))
            return original(importer,*args)
        with patch.object(FolderImporter,'package',invalidate):self.tick()
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM folder_imports').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT imported FROM folder_jobs').fetchone()[0],0)
        # A deterministic published archive may remain, but the same request
        # recovers it without another physical copy and never exceeds ten.
        self.tick();self.assertEqual(len(Uploads(self.store,self.destination).list()),10)

    def test_tampered_source_or_limit_is_rejected_before_copy(self):
        for column,value in [('source_id','other'),('limit_count',100),('collections','["../other"]')]:
            self.tick();job=self.request(os.urandom(16).hex())
            with self.store.db() as db:db.execute('UPDATE folder_jobs SET '+column+'=? WHERE id=?',(value,job['id']))
            self.assertEqual(self.tick()['worker'],'rejected')
        self.assertFalse(self.destination.exists())

    def test_queue_cancel_offline_and_private_fields(self):
        self.tick();job=self.request();self.store.cancel_folder_import(job['id'])
        with self.store.db() as db:
            row=json.loads(db.execute("SELECT value FROM settings WHERE key='folder-worker'").fetchone()[0]);row['seen']=0
            db.execute("UPDATE settings SET value=? WHERE key='folder-worker'",(json.dumps(row),))
        with self.assertRaises(ValueError):self.request('b'*32)
        status=self.store.folder_status();self.assertFalse(status['connected'])
        self.assertFalse({'lease','lease_until','source_id','request_key'}&set(status['jobs'][0]))
        self.assertNotIn(str(self.source),json.dumps(status))

    def test_backup_restore_does_not_replay_old_queued_jobs(self):
        self.tick();self.request();path=self.root/'restored.db'
        result=copy_database(self.store.path,path,restore=True)
        self.assertEqual(result['counts']['folder_jobs'],1)
        restored=Store(path);self.assertEqual(restored.folder_status()['jobs'][0]['state'],'failed')

    def test_live_folder_lock_is_not_stolen_or_counted_as_a_new_job(self):
        import fcntl
        self.tick();self.request()
        with (self.root/'folder-pilot.lock').open('r+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.tick(),{'worker':'busy'})
            self.assertEqual(self.store.folder_status()['jobs'][0]['state'],'queued')
            self.assertFalse(self.destination.exists())
        self.tick();self.assertEqual(self.store.folder_status()['jobs'][0]['imported'],10)

    def test_real_http_admin_worker_and_cross_origin_boundaries(self):
        self.tick()
        with patch.dict(os.environ,{'STUDIO_PASSWORD':'synthetic-folder-admin','STUDIO_NAS_WORKER_TOKEN':'synthetic-worker'}):
            server=make_server('127.0.0.1',0,Studio(self.store,None));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                def request(auth,path='/api/folders',body=None,origin=None):
                    headers={'Authorization':auth,'Content-Type':'application/json'}
                    if origin:headers['Origin']=origin
                    req=urllib.request.Request(base+path,headers=headers,data=None if body is None else json.dumps(body).encode())
                    try:
                        with urllib.request.urlopen(req) as r:return r.status,json.load(r)
                    except urllib.error.HTTPError as e:return e.code,json.load(e) if e.code!=401 else {}
                admin='Basic '+base64.b64encode(b'admin:synthetic-folder-admin').decode()
                self.assertEqual(request('Bearer synthetic-worker')[0],403)
                self.assertEqual(request('')[0],401)
                payload=dict(collections=['manga'],request_key='a'*32)
                self.assertEqual(request(admin,body={**payload,'root':'/other'})[0],400)
                self.assertEqual(request(admin,body=payload,origin='https://example.invalid')[0],403)
                self.assertEqual(request(admin,body=payload)[0],202)
                self.assertEqual(request(admin,body=payload)[1]['id'],request(admin)[1]['jobs'][0]['id'])
            finally:server.shutdown();server.server_close();thread.join()


class FolderQueueDeploymentTests(unittest.TestCase):
    def test_installer_pins_the_fixed_worker_and_complete_runtime_manifest(self):
        deploy=Path(__file__).resolve().parents[1]/'deploy'
        text=(deploy/'install-folder-queue.sh').read_text()
        # This separately installed reader stays pinned when app-only releases advance.
        self.assertIn('revision=e328e8fe828cf1288bf728d6ce4954b273a78244',text)
        pinned=Path(__file__).with_name('fixtures')/'folder-worker-runtime.sha256'
        self.assertIn('manifest_sha='+hashlib.sha256(pinned.read_bytes()).hexdigest(),text)
        self.assertEqual({line.split()[1] for line in pinned.read_text().splitlines()},
            {line.split()[1] for line in (deploy/'runtime-manifest.sha256').read_text().splitlines()})
        self.assertIn('tick_sha='+hashlib.sha256((deploy/'tick-folder-queue.sh').read_bytes()).hexdigest(),text)

    def test_preview_has_no_nas_actions_and_rejects_path_escape(self):
        script=Path(__file__).resolve().parents[1]/'deploy/install-folder-queue.sh'
        result=subprocess.run(['sh',str(script),'preview','/volume1/Approved/Root'],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Preview only: no network, Docker or NAS changes',result.stdout)
        for path in ['/','/volume1','/volumeX/Root','/volume1/../other','/volume1/Root,readonly=false','/volume1/Root\nother']:
            self.assertNotEqual(subprocess.run(['sh',str(script),'preview',path],capture_output=True).returncode,0)

    def test_tick_never_accepts_web_command_or_source_arguments(self):
        script=Path(__file__).resolve().parents[1]/'deploy/tick-folder-queue.sh'
        for args in [['/other'],['--source','/other'],['sh','-c','touch /tmp/not-created']]:
            self.assertEqual(subprocess.run(['sh',str(script),*args],capture_output=True).returncode,2)


if __name__=='__main__':unittest.main()
