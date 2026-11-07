import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import Store
from server import Studio,make_server


class PresetTests(unittest.TestCase):
    def test_and_filter_and_preset_lifecycle_preserve_original_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'studio.db')
            a=store.create_work('Both',tags=['female:glasses','language:korean'])
            store.create_work('Only glasses',tags=['female:glasses','language:english'])
            store.create_work('Only Korean',tags=['male:glasses','language:korean'])
            d=store.create_work('Different origins');store.edit_user_tags([d['id']],['female:glasses'])
            store.upsert_source(d['id'],{'url':'https://hitomi.la/galleries/123.html','tags':['language:korean']})
            snapshot=json.dumps(store.list_works(),sort_keys=True)
            tags=['female:glasses','language:korean']
            self.assertEqual({w['id'] for w in store.list_works(all_tags=tags)['items']},{a['id'],d['id']})
            preset=store.save_tag_preset('안경 + 한국어',tags)
            self.assertEqual(Store(store.path).tag_presets(),[preset])
            edited=store.save_tag_preset('번역본 찾기',tags+[tags[0]],preset['id'])
            self.assertEqual(edited['tags'],tags)
            self.assertEqual(edited['id'],preset['id'])
            with self.assertRaises(ValueError):store.save_tag_preset('번역본 찾기',tags)
            for bad in [[],[''],['date_added:123'],[None],['x\n'],['x'*301],['tag'+str(n) for n in range(13)],'not a list']:
                with self.subTest(tags=bad),self.assertRaises(ValueError):store.save_tag_preset('Invalid',bad)
            self.assertEqual(store.tag_presets(),[edited])
            store.delete_tag_preset(preset['id']);self.assertEqual(store.tag_presets(),[])
            self.assertEqual(json.dumps(store.list_works(),sort_keys=True),snapshot)

    def test_clean_routes_are_authenticated_and_audio_is_not_claimed(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'STUDIO_PASSWORD':'generated-routes','STUDIO_PC_WORKER_TOKEN':'generated-worker'}):
            store=Store(Path(directory)/'studio.db');server=make_server('127.0.0.1',0,Studio(store,None))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                auth='Basic '+base64.b64encode(b'admin:generated-routes').decode()
                def request(path,data=None,credential=auth):
                    return urllib.request.urlopen(urllib.request.Request(base+path,
                        data=None if data is None else json.dumps(data).encode(),
                        headers={'Authorization':credential,'Content-Type':'application/json'}),timeout=5)
                for path in ['/manga','/manga/','/manga?q=example','/manga/E123','/manga/E123/7','/manga/downloads','/manga/works/'+'a'*32+'/read/6',
                             '/library?q=example','/E123','/E123/7','/downloads','/works/'+'a'*32+'/read/6']:
                    with request(path) as response:self.assertIn(b'Library Studio',response.read())
                    with self.assertRaises(urllib.error.HTTPError) as error:request(path,credential='Bearer generated-worker')
                    self.assertEqual(error.exception.code,403)
                for path in ['/audio','/audio/','/audio/api/health','/api/missing','/.env','/unrecognized','/manga/audio/','/manga/api/missing','/mangaverse']:
                    with self.assertRaises(urllib.error.HTTPError) as error:request(path)
                    self.assertEqual(error.exception.code,404)
                with request('/api/tag-presets',{'name':'Generated','tags':['female:glasses']}) as response:preset=json.load(response)
                with request('/api/tag-presets') as response:self.assertEqual(json.load(response),[preset])
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/tag-presets',{'name':'Worker','tags':['x']},'Bearer generated-worker')
                self.assertEqual(error.exception.code,403)
                with request('/api/tag-presets/'+preset['id']+'/delete',{}) as response:self.assertTrue(json.load(response)['deleted'])
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
