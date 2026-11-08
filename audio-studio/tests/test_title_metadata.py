import copy
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from title_metadata import TitleMetadata, title_key
from translation_quality import assess
from catalog import Catalog
from server import make_server


class TitleMetadataTests(unittest.TestCase):
    def test_cache_enriches_views_without_rewriting_originals_or_official_korean(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'titles.json'
            rows = {title_key(t): {'original': t, 'ko': k, 'kind': 'machine'} for t, k in [('原文作品', '한국어 작품'), ('01_耳かき', '01_귀청소')]}
            file.write_text(json.dumps({'schema': 1, 'language': 'ko', 'entries': rows}), encoding='utf-8')
            works = [{'title': '저장된 제목', 'source_info_titles': {'ja': '原文作品'}, 'editions': [{'tracks': [{'id': 't', 'title': '01_耳かき', 'relative_path': '01_耳かき.wav', 'resume': 5}]}]}]
            original = copy.deepcopy(works);cache = TitleMetadata(file)
            response = cache.works(copy.deepcopy(works))
            self.assertEqual(response[0]['title_ko_auto'], '한국어 작품')
            track = response[0]['editions'][0]['tracks'][0]
            self.assertEqual(track['title_ko'], '01_귀청소');self.assertEqual(track['title_translation_kind'], 'machine')
            self.assertEqual(track['title'], original[0]['editions'][0]['tracks'][0]['title'])
            self.assertEqual(track['relative_path'], '01_耳かき.wav');self.assertEqual(track['resume'], 5)
            self.assertEqual(works, original)
            works[0]['source_info_titles']['ko'] = '공식 제목'
            self.assertNotIn('title_ko_auto', cache.works(works)[0])

    def test_missing_corrupt_and_wrong_original_records_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'titles.json';cache = TitleMetadata(file)
            self.assertEqual(cache.read(), {})
            file.write_text('{broken', encoding='utf-8');self.assertEqual(cache.read(), {})
            file.write_text(json.dumps({'schema': 1, 'language': 'ko', 'entries': {'bad-key': {'original': '原文', 'ko': '번역', 'kind': 'machine'}}}), encoding='utf-8')
            self.assertEqual(cache.read(), {})
            self.assertEqual(title_key(' 가 '), title_key('가'))
            neutral = cache.edition({'tracks': [{'id': 'x', 'title': 'ASMR'}]})['tracks'][0]
            self.assertEqual(neutral['title_translation']['kind'], 'original')
            self.assertNotIn('title_ko', neutral, 'Unchanged neutral/original text is not counted as a translation')

    def test_manual_edits_survive_regeneration_and_stale_saves_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'titles.json';cache = TitleMetadata(file);identifier = 'a' * 32
            row = {'original': '原文', 'ko': '자동 번역', 'kind': 'machine', 'issues': ['term_omission']}
            file.write_text(json.dumps({'schema': 1, 'language': 'ko', 'entries': {title_key('原文'): row}}), encoding='utf-8')
            first = cache.save('work', identifier, '原文', '내 번역', 0)
            self.assertEqual(first['kind'], 'manual');self.assertEqual(first['revision'], 1)
            self.assertTrue(first['issues'], 'Unreviewed editing does not silently erase automatic warnings')
            before = cache.override_file.read_bytes()
            with self.assertRaisesRegex(ValueError, '다른 화면'):
                cache.save('work', identifier, '原文', '덮어쓰면 안 됨', 0)
            self.assertEqual(cache.override_file.read_bytes(), before)
            cache.save('work', identifier, '原文', '검수한 내 번역', 1, reviewed=True)
            row['ko'] = '새 자동번역'
            file.write_text(json.dumps({'schema': 1, 'language': 'ko', 'entries': {title_key('原文'): row}}), encoding='utf-8')
            restarted = TitleMetadata(file)
            info = restarted.info('work', identifier, '原文', official='공식 번역')
            self.assertEqual(info['text'], '검수한 내 번역');self.assertEqual(info['issues'], [])
            self.assertEqual(info['revision'], 2);self.assertEqual(info['status'], 'reviewed')
            self.assertEqual(len(restarted.overrides()['work:' + identifier]['history']), 1)
            changed = restarted.info('work', identifier, '変わった原文')
            self.assertEqual(changed['issues'][0]['code'], 'source_changed')

    def test_concurrent_different_targets_and_corrupt_manual_file_preserve_saved_data(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = TitleMetadata(Path(directory) / 'titles.json')
            threads = [threading.Thread(target=cache.save, args=('track', format(i, '032x'), '原文', '직접 입력', 0)) for i in range(10)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(len(cache.overrides()), 10)
            cache.override_file.write_text('{broken', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '읽지 못했습니다'):
                cache.save('track', 'f' * 32, '原文', '덮지 않음', 0)
            self.assertEqual(cache.override_file.read_text(encoding='utf-8'), '{broken')

    def test_quality_checks_flag_refusal_omissions_and_incomplete_results(self):
        self.assertIn('refused', assess('原文', '죄송하지만 번역할 수 없습니다.'))
        self.assertIn('untranslated', assess('耳かき', '耳かき'))
        self.assertIn('term_omission', assess('01_耳かき', '01_소리'))
        self.assertIn('missing_number', assess('12_雨の夜', '비 오는 밤'))
        self.assertIn('truncated', assess('雨の夜', '비 오는 밤', 'length'))
        self.assertIn('wrong_language', assess('雨の夜', 'Rainy night'))
        self.assertEqual(assess('01_耳かき', '01_귀청소'), [])

    def test_authenticated_editor_api_preserves_database_titles_and_file_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);catalog = Catalog(root / 'library.db')
            work = catalog.create_work('原文作品');edition = catalog.create_edition(work['id'], '원본', 'audio')
            track = catalog.add_track(edition['id'], '01_耳かき', 'original.wav', 10)
            server = make_server(catalog, root / 'media', port=0, password='fixture-only')
            thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
            import base64
            headers = {'Authorization': 'Basic ' + base64.b64encode(b'admin:fixture-only').decode(), 'Content-Type': 'application/json'}
            base = f'http://127.0.0.1:{server.server_port}'
            def post(path, body, extra=None):
                request = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={**headers, **(extra or {})})
                with urllib.request.urlopen(request) as response: return json.load(response)
            try:
                path = '/api/tracks/' + track['id'] + '/title-translation'
                body = {'original': track['title'], 'text': '01_귀청소', 'revision': 0, 'reviewed': True}
                with self.assertRaises(urllib.error.HTTPError) as error: post(path, body, {'Authorization': ''})
                self.assertEqual(error.exception.code, 401)
                with self.assertRaises(urllib.error.HTTPError) as error: post(path, body, {'Origin': 'https://other.test'})
                self.assertEqual(error.exception.code, 403)
                self.assertEqual(post(path, body)['kind'], 'manual')
                post('/api/works/' + work['id'] + '/title-translation', {'original': work['title'], 'text': '직접 입력한 작품', 'revision': 0})
                with urllib.request.urlopen(urllib.request.Request(base + '/api/works', headers=headers)) as response:
                    view = json.load(response)['works'][0]
                self.assertEqual(view['title_ko_manual'], '직접 입력한 작품')
                self.assertEqual(view['editions'][0]['tracks'][0]['title_ko'], '01_귀청소')
                self.assertEqual(catalog.works()[0]['title'], '原文作品')
                self.assertEqual(catalog.track(track['id'])['title'], '01_耳かき')
                self.assertEqual(catalog.track(track['id'])['relative_path'], 'original.wav')
                with urllib.request.urlopen(urllib.request.Request(base + '/api/export', headers=headers)) as response:
                    self.assertNotIn('title_ko_manual', json.load(response)['works'][0])
            finally:
                server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    unittest.main()
