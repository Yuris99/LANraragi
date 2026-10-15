import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backup import copy_database
from prepare_nas import prepare
from init_volumes import initialize,NAMES
from store import Store
from gallery_engine import engine_argv,package_images
from make_synthetic import create_fixture
import zipfile


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_nas_config_is_new_private_and_does_not_create_nas_paths(self):
        destination=self.root/'.env.nas'
        digest='sha256:'+'a'*64
        prepare(destination,'/verified/new-studio','/verified/new-studio/downloads',9001,9001,digest,digest)
        self.assertEqual(destination.stat().st_mode&0o777,0o600)
        self.assertIn('STUDIO_PC_WORKER_TOKEN=',destination.read_text())
        with self.assertRaises(FileExistsError):prepare(destination,'/verified/new-studio','/verified/new-studio/downloads',9001,9001,digest,digest)
        with self.assertRaises(ValueError):prepare(self.root/'bad.env','/','/downloads',9001,9001,digest,digest)
        with self.assertRaises(ValueError):prepare(self.root/'bad.env','/verified/new-studio','/other',9001,9001,'latest',digest)

    def test_live_wal_backup_restore_preserves_catalog_and_rejects_overwrite(self):
        store=Store(self.root/'live.db')
        # Keep an actual WAL connection open across the backup.
        db=sqlite3.connect(store.path);self.addCleanup(db.close)
        work=store.create_work('Synthetic restore book')
        store.upsert_source(work['id'],{'url':'https://nhentai.net/g/123/','comments':[{'id':'1','text':'synthetic archived comment'}]})
        queued=store.queue('https://nhentai.net/g/123/','pc','command')
        result=copy_database(store.path,self.root/'backup.db')
        self.assertEqual(result['counts']['works'],1)
        self.assertEqual((self.root/'backup.db').stat().st_mode&0o777,0o600)
        store.update_work(work['id'],{'title':'Newer live title'})
        copy_database(self.root/'backup.db',self.root/'restored.db')
        restored=Store(self.root/'restored.db')
        self.assertEqual(restored.get_work(work['id'])['title'],'Synthetic restore book')
        self.assertEqual(restored.get_work(work['id'])['sources'][0]['comments'][0]['text'],'synthetic archived comment')
        self.assertEqual(restored.job(queued['id'])['state'],'queued')
        with self.assertRaises(FileExistsError):copy_database(self.root/'backup.db',store.path)
        self.assertEqual(store.get_work(work['id'])['title'],'Newer live title')

    def test_restore_revokes_leases_and_blocks_previously_running_jobs(self):
        store=Store(self.root/'live.db')
        job=store.queue('https://nhentai.net/g/123/','pc','command')
        claim=store.claim('pc','command')
        copy_database(store.path,self.root/'backup.db')
        copy_database(self.root/'backup.db',self.root/'restored.db',restore=True)
        restored=Store(self.root/'restored.db')
        self.assertEqual(restored.job(job['id'])['state'],'blocked')
        self.assertIsNone(restored.job(job['id'])['lease'])
        with self.assertRaises(ValueError):restored.report(job['id'],claim['lease'],'running')
        self.assertEqual(store.job(job['id'])['state'],'running')

    def test_invalid_database_is_not_published(self):
        source=self.root/'wrong.db'
        with sqlite3.connect(source) as db:db.execute('CREATE TABLE wrong(x)')
        with self.assertRaises(ValueError):copy_database(source,self.root/'copy.db')
        self.assertFalse((self.root/'copy.db').exists())

    def test_volume_preflight_rejects_unmarked_existing_data_before_any_chown(self):
        for name in NAMES:(self.root/name).mkdir()
        (self.root/'plugins'/'existing.txt').write_text('keep')
        with patch('init_volumes.os.chown') as chown:
            with self.assertRaises(ValueError):initialize(self.root,9001,9001)
            chown.assert_not_called()
        self.assertEqual((self.root/'plugins'/'existing.txt').read_text(),'keep')

    def test_volume_marker_rejects_unreviewed_uid_change(self):
        for name in NAMES:
            directory=self.root/name;directory.mkdir()
            (directory/'.studio-volume.json').write_text(json.dumps({'format':1,'name':name,'uid':9001,'gid':9001}))
        with patch('init_volumes.os.chown') as chown:
            with self.assertRaises(ValueError):initialize(self.root,9002,9001)
            chown.assert_not_called()

    def test_list_batch_matches_individual_hydration_and_source_order(self):
        store=Store(self.root/'catalog.db')
        work=store.create_work('Synthetic book',tags=['local:tag'])
        store.upsert_source(work['id'],{'url':'https://nhentai.net/g/123/','tags':['source:tag']})
        store.upsert_source(work['id'],{'url':'https://hitomi.la/galleries/123.html'})
        self.assertEqual(store.list_works()['items'][0],store.get_work(work['id']))


class GalleryEngineTests(unittest.TestCase):
    def test_exhentai_never_silently_falls_back_to_another_source(self):
        with self.assertRaises(ValueError):engine_argv('https://exhentai.org/g/123/abc123/','/tmp/unused')

    def test_engine_preserves_source_url_and_has_no_bypass_flags(self):
        url='https://hitomi.la/doujinshi/synthetic-123.html'
        args=engine_argv(url,'/tmp/unused')
        self.assertEqual(args[-1],url)
        self.assertIn('--config-ignore',args)
        self.assertNotIn('--cookies-from-browser',args)
        self.assertNotIn('--no-check-certificate',args)
        self.assertNotIn('--xff',args)

    def test_html_response_is_not_packaged_as_a_comic(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root,'01.jpg').write_bytes(b'<html>Login required</html>')
            with self.assertRaises(ValueError):package_images(root)
            self.assertFalse(Path(root,'gallery.cbz').exists())

    def test_cbz_preserves_original_metadata_and_full_source_url(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);fixture=create_fixture(root/'fixture')
            output=root/'output';output.mkdir()
            with zipfile.ZipFile(fixture) as source:
                (output/'01.png').write_bytes(source.read('01.png'))
            original={'title':'Synthetic metadata','tags':{'artist':['fixture']},'original_field':'preserve','source':'original-provider-field'}
            (output/'info.json').write_text(json.dumps(original))
            source={'provider':'hitomi','external_id':'123','url':'https://hitomi.la/doujinshi/synthetic-123.html'}
            package_images(output,source)
            with zipfile.ZipFile(output/'hitomi-123.cbz') as comic:
                saved=json.loads(comic.read('info.json'))
                self.assertEqual(json.loads(comic.read('gallery-dl-original.json')),original)
            self.assertEqual(saved,{**original,'source':source['url']})
            self.assertEqual(json.loads((output/'info.json').read_text()),original)

    def test_downloaded_images_form_a_readable_cbz_without_deleting_images(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);fixture=create_fixture(root/'fixture')
            output=root/'output';output.mkdir()
            with zipfile.ZipFile(fixture) as source:
                for name in source.namelist():(output/name).write_bytes(source.read(name))
            self.assertEqual(package_images(output),3)
            with zipfile.ZipFile(output/'gallery.cbz') as comic:self.assertEqual(comic.namelist(),['01.png','02.png','03.png'])
            self.assertTrue((output/'01.png').exists())
