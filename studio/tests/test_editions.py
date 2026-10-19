"""Generated-only edition identity, media storage and authenticated streaming tests."""
import base64
import io
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import wave
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backup import copy_database
from editions import VoiceAssets
from server import Studio,make_server
from store import Store


def audio_bytes():
    stream=io.BytesIO()
    with wave.open(stream,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(8000);audio.writeframes(b'\x00\x00'*48000)
    return stream.getvalue()


class EditionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.store=Store(self.root/'studio.db');(self.root/'uploads').mkdir()
        self.assets=VoiceAssets(self.store,self.root/'uploads',1024*1024)
        self.one=self.store.create_work('Original','Artist',lrr_id='a'*40,pages=7)
        self.two=self.store.create_work('Translation','Artist',lrr_id='b'*40,pages=9)
    def upload(self,work=None,name='voice.wav',raw=None):
        raw=audio_bytes() if raw is None else raw
        return self.assets.receive((work or self.one)['id'],io.BytesIO(raw),len(raw),name)

    def test_translation_group_preserves_distinct_files_sources_and_reading_progress(self):
        self.store.upsert_source(self.one['id'],{'url':'https://nhentai.net/g/123456/','comments':[{'id':'1','text':'Original comment'}]})
        self.store.upsert_source(self.two['id'],{'url':'https://hitomi.la/galleries/123456.html'})
        self.store.progress(self.one['id'],2);self.store.progress(self.two['id'],5)
        self.store.configure_edition(self.two['id'],{'language':'한국어','label':'Team A','translator':'Translator'})
        result=self.store.group_edition(self.two['id'],'L'+str(self.one['local_number']))
        self.assertEqual(len(result['edition']['siblings']),2)
        again=Store(self.store.path);first=again.get_work(self.one['id']);second=again.get_work(self.two['id'])
        self.assertEqual((first['lrr_id'],second['lrr_id']),('a'*40,'b'*40))
        self.assertEqual((first['progress'],second['progress']),(2,5))
        self.assertEqual(first['sources'][0]['comments'][0]['text'],'Original comment')
        self.assertEqual(second['edition']['translator'],'Translator')
        self.assertEqual(again.resolve_short_id('123456')['id'],self.two['id'])
        self.assertEqual(again.resolve_short_id('N123456')['id'],self.one['id'])
        self.assertEqual(again.list_works()['total'],2)

    def test_equal_title_number_or_cover_never_groups_works_automatically(self):
        self.store.index_visual([{'work_id':w['id'],'fingerprint':'0'*16} for w in (self.one,self.two)])
        result=self.store.visual_search('0'*16)
        self.assertEqual(len(result['items']),2)
        self.assertIsNone(self.store.get_work(self.one['id'])['edition']['group_id'])
        self.assertIsNone(self.store.get_work(self.two['id'])['edition']['group_id'])
        with self.assertRaises(ValueError):self.store.group_edition(self.one['id'],'L'+str(self.one['local_number']))

    def test_distinct_existing_groups_require_explicit_ungroup_and_keep_configuration(self):
        three=self.store.create_work('Third');four=self.store.create_work('Fourth')
        self.store.group_edition(self.one['id'],'L'+str(self.two['local_number']))
        self.store.group_edition(three['id'],'L'+str(four['local_number']))
        group=self.store.get_work(self.one['id'])['edition']['group_id']
        with self.assertRaises(ValueError):self.store.group_edition(self.one['id'],'L'+str(three['local_number']))
        self.assertEqual(self.store.get_work(self.one['id'])['edition']['group_id'],group)
        self.store.configure_edition(self.one['id'],{'language':'Japanese'})
        self.store.ungroup_edition(self.one['id'])
        self.store.group_edition(self.one['id'],'L'+str(three['local_number']))
        self.assertEqual(self.store.get_work(self.one['id'])['edition']['language'],'Japanese')

    def test_voice_only_work_can_exist_without_comic_or_external_source(self):
        voice=self.store.create_work('Video-only comic')
        self.store.configure_edition(voice['id'],{'kind':'voice_video','language':'한국어'})
        asset=self.upload(voice,'clip.mp4',b'\x00\x00\x00\x18ftypisom'+b'\0'*20)
        result=self.store.get_work(voice['id'])
        self.assertIsNone(result['lrr_id']);self.assertEqual(result['sources'],[])
        self.assertEqual(result['edition']['assets'][0]['id'],asset['id'])
        self.assertEqual(result['edition']['assets'][0]['kind'],'video')

    def test_audio_page_cues_validate_scope_monotonic_time_and_preserve_previous_mapping(self):
        self.store.configure_edition(self.one['id'],{'kind':'voice_pages'})
        asset=self.upload();other=self.upload(self.two)
        self.store.save_voice_cues(self.one['id'],asset['id'],[{'page':1,'second':0},{'page':2,'second':2.5}])
        for cues in ([{'page':8,'second':1}],[{'page':1,'second':float('nan')}],[{'page':1,'second':2},{'page':2,'second':1}],[{'page':1,'second':0},{'page':1,'second':1}]):
            with self.assertRaises(ValueError):self.store.save_voice_cues(self.one['id'],asset['id'],cues)
        with self.assertRaises(KeyError):self.store.save_voice_cues(self.one['id'],other['id'],[])
        self.assertEqual(len(self.store.get_work(self.one['id'])['edition']['assets'][0]['cues']),2)

    def test_audio_can_reference_a_separate_comic_edition_without_copying_its_file(self):
        voice=self.store.create_work('Audio comic edition')
        result=self.store.configure_edition(voice['id'],{'kind':'voice_pages','comic_reference':'L'+str(self.one['local_number'])})
        self.assertEqual(result['edition']['comic_lrr_id'],'a'*40)
        self.assertEqual(result['edition']['comic_pages'],7)
        self.assertIsNone(result['lrr_id'])

    def test_full_file_dedup_does_not_share_positions_between_editions(self):
        first=self.upload();again=self.upload();other=self.upload(self.two)
        self.assertEqual(first['id'],again['id']);self.assertNotEqual(first['id'],other['id'])
        self.assertEqual(len(list(self.assets.root.glob('*.wav'))),1)
        self.store.save_voice_progress(self.one['id'],first['id'],2.25)
        self.assertEqual(self.store.get_work(self.two['id'])['edition']['assets'][0]['position'],0)
        with self.assertRaises(KeyError):self.store.save_voice_progress(self.one['id'],other['id'],2)
        for invalid in (float('nan'),float('inf'),-1,True,'3'):
            with self.assertRaises(ValueError):self.store.save_voice_progress(self.one['id'],first['id'],invalid)

    def test_cover_replacement_preserves_voice_kind_and_original_asset_bytes(self):
        self.store.configure_edition(self.one['id'],{'kind':'voice_pages'})
        first=self.upload(name='cover.png',raw=b'\x89PNG\r\n\x1a\n'+b'generated-first')
        second=self.upload(name='cover.png',raw=b'\x89PNG\r\n\x1a\n'+b'generated-second')
        result=self.store.get_work(self.one['id'])
        self.assertEqual(result['edition']['kind'],'voice_pages')
        self.assertEqual(result['cover_asset_id'],second['id'])
        self.assertEqual(next(w for w in self.store.list_works()['items'] if w['id']==self.one['id'])['cover_asset_id'],second['id'])
        row,stream=self.assets.open(first['id'])
        with stream:self.assertTrue(stream.read().endswith(b'generated-first'))

    def test_invalid_or_interrupted_upload_never_registers_a_partial_asset(self):
        for raw,name,length in [(b'bad','test.mp4',3),(b'bad','test.wav',10),(b'bad','test.exe',3)]:
            with self.assertRaises(ValueError):self.assets.receive(self.one['id'],io.BytesIO(raw),length,name)
        self.assertEqual(self.store.get_work(self.one['id'])['edition']['assets'],[])
        self.assertEqual(list(self.assets.root.glob('*.part')),[])

    def test_media_symlinks_and_existing_conflicting_content_are_never_followed_or_overwritten(self):
        asset=self.upload();row,stream=self.assets.open(asset['id']);stream.close()
        stored=self.assets.root/(row['sha256']+row['extension']);stored.unlink()
        outside=self.root/'outside';outside.write_bytes(audio_bytes());stored.symlink_to(outside)
        with self.assertRaises(OSError):self.assets.open(asset['id'])
        with self.assertRaises(OSError):self.upload()
        self.assertEqual(outside.read_bytes(),audio_bytes())

    def test_backup_restore_keeps_edition_relationships_and_media_resume_metadata(self):
        self.store.group_edition(self.one['id'],'L'+str(self.two['local_number']))
        self.store.configure_edition(self.one['id'],{'kind':'voice_pages','label':'Voice translation'})
        asset=self.upload();self.store.save_voice_progress(self.one['id'],asset['id'],3)
        self.store.save_voice_cues(self.one['id'],asset['id'],[{'page':1,'second':0}])
        result=copy_database(self.store.path,self.root/'backup.db')
        self.assertEqual(result['counts']['voice_assets'],1)
        self.assertEqual(result['counts']['voice_cues'],1)
        restored=Store(self.root/'backup.db').get_work(self.one['id'])
        self.assertEqual(len(restored['edition']['siblings']),2)
        self.assertEqual(restored['edition']['assets'][0]['position'],3)
        self.assertEqual(restored['edition']['assets'][0]['cues'],[{'page':1,'second':0}])

    def test_similarity_ranking_and_query_validation(self):
        self.store.index_visual([{'work_id':self.one['id'],'fingerprint':'0'*16},{'work_id':self.two['id'],'fingerprint':'0000000000000001'}])
        result=self.store.visual_search('0'*16)
        self.assertEqual([x['distance'] for x in result['items']],[0,1])
        self.assertEqual(result['indexed'],2)
        for invalid in ('../outside','0'*15,'x'*16):
            with self.assertRaises(ValueError):self.store.visual_search(invalid)
        with self.assertRaises(ValueError):self.store.index_visual([{'work_id':self.one['id'],'fingerprint':'bad'}])

    def test_copy_cleanup_cannot_silently_merge_a_configured_translation_or_voice_edition(self):
        self.store.configure_edition(self.one['id'],{'language':'Korean'})
        with self.store.db() as db:
            with self.assertRaisesRegex(ValueError,'edition_metadata_requires_review'):
                self.store.consolidate_copy(db,self.one['id'],self.two['id'],'c'*64,'a'*40,{})
        self.assertIsNone(self.store.get_work(self.one['id'])['merged_into'])


class MediaHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'STUDIO_PASSWORD':'synthetic-editions','STUDIO_PC_WORKER_TOKEN':'synthetic-worker'});self.env.start();self.addCleanup(self.env.stop)
        self.store=Store(root/'studio.db');(root/'uploads').mkdir()
        self.work=self.store.create_work('Generated voice-only comic')
        self.app=Studio(self.store,None,root/'uploads');self.server=make_server('127.0.0.1',0,self.app)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
    def request(self,path,data=None,headers=None,auth=True,method=None):
        h={'Authorization':'Basic '+base64.b64encode(b'admin:synthetic-editions').decode()} if auth else {}
        if isinstance(data,dict):h['Content-Type']='application/json';data=json.dumps(data).encode()
        elif data is not None:h['Content-Type']='application/octet-stream'
        return urllib.request.urlopen(urllib.request.Request(self.base+path,data=data,headers={**h,**(headers or {})},method=method),timeout=10)
    def upload(self):
        with self.request('/api/works/'+self.work['id']+'/voice/upload?filename=voice.wav',audio_bytes()) as response:return json.load(response)

    def test_streaming_supports_authenticated_ranges_seek_and_exact_download(self):
        asset=self.upload();url='/api/voice/assets/'+asset['id']
        with self.request(url,headers={'Range':'bytes=10-29'}) as response:
            self.assertEqual(response.status,206);self.assertEqual(response.read(),audio_bytes()[10:30])
            self.assertEqual(response.headers['Content-Type'],'audio/wav')
            self.assertEqual(response.headers['Content-Range'],f'bytes 10-29/{len(audio_bytes())}')
        with self.request(url,method='HEAD') as response:
            self.assertEqual(response.read(),b'');self.assertEqual(int(response.headers['Content-Length']),len(audio_bytes()))
        with self.request(url+'?download=1') as response:
            self.assertEqual(response.read(),audio_bytes());self.assertIn('attachment',response.headers['Content-Disposition'])
        for value in ('bytes=-0','bytes=999999-','bytes=0-1,3-4'):
            with self.assertRaises(urllib.error.HTTPError) as error:self.request(url,headers={'Range':value})
            self.assertEqual(error.exception.code,416)
            self.assertEqual(error.exception.headers['Content-Range'],'bytes */'+str(len(audio_bytes())))

    def test_media_and_visual_actions_require_admin_and_same_origin(self):
        asset=self.upload()
        for headers in ({},{'Authorization':'Bearer synthetic-worker'}):
            with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/voice/assets/'+asset['id'],headers=headers,auth=False)
            self.assertEqual(error.exception.code,403 if 'Authorization' in headers else 401)
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/visual/search',{'fingerprint':'0'*16},headers={'Origin':'https://other.invalid'})
        self.assertEqual(error.exception.code,403)
        # Check rejection at the headers, without racing a large body write
        # against the server intentionally closing an unsupported request.
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        try:
            connection.putrequest('POST','/api/works/'+self.work['id']+'/voice/upload?filename=voice.wav')
            connection.putheader('Authorization','Basic '+base64.b64encode(b'admin:synthetic-editions').decode())
            connection.putheader('Content-Type','application/octet-stream')
            connection.putheader('Transfer-Encoding','chunked');connection.endheaders()
            self.assertEqual(connection.getresponse().status,411)
        finally:connection.close()

    def test_voice_only_file_is_not_reported_as_metadata_only(self):
        self.upload()
        with self.request('/api/library/status') as response:result=json.load(response)
        self.assertEqual(result['metadata_only'],0);self.assertEqual(result['voice_editions'],1)


if __name__=='__main__':unittest.main()
