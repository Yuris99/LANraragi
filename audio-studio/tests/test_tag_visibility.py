import base64
import concurrent.futures
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog import Catalog
from server import make_server
from tag_visibility import TagVisibility, TagVisibilityConflict


class TagVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root/'tag-visibility.json'
        self.store = TagVisibility(self.path)

    def test_persistence_normalization_noop_and_stale_revision(self):
        self.assertEqual(self.store.read()['hidden_rplay_tags'], [])
        self.assertFalse(self.path.exists())
        self.assertEqual(self.store.save(0, [])['revision'], 0)
        self.assertFalse(self.path.exists())
        result = self.store.save(0, ['  행사 ', '가', '가'])
        self.assertEqual(result['hidden_rplay_tags'], ['행사', '가'])
        self.assertEqual(TagVisibility(self.path).read(), result)
        original = self.path.read_bytes()
        with self.assertRaises(TagVisibilityConflict):
            self.store.save(0, ['old screen'])
        self.assertEqual(original, self.path.read_bytes())
        self.assertEqual(self.store.save(1, [])['revision'], 2)

    def test_invalid_inputs_never_replace_saved_settings(self):
        self.store.save(0, ['keep'])
        original = self.path.read_bytes()
        for values in (None, 'tag', [None], [''], ['a\nb'], ['a'*301], ['a']*2001):
            with self.subTest(values_type=type(values).__name__), self.assertRaises(ValueError):
                self.store.save(1, values)
            self.assertEqual(self.path.read_bytes(), original)
        with self.assertRaises(ValueError):
            self.store.save(True, [])

    def test_legacy_settings_and_client_preserve_dlsite_selection(self):
        self.path.write_text(json.dumps({'schema': 1, 'revision': 4, 'hidden_rplay_tags': ['old']}), encoding='utf-8')
        self.assertEqual(self.store.read()['hidden_dlsite_tags'], [])
        result = self.store.save(4, ['old'], ['耳かき'])
        self.assertEqual(result['revision'], 5)
        self.assertEqual(TagVisibility(self.path).read()['hidden_dlsite_tags'], ['耳かき'])
        result = self.store.save(5, ['new'])
        self.assertEqual(result['hidden_dlsite_tags'], ['耳かき'], 'Old RPLAY-only clients cannot erase DLsite settings')
        with self.assertRaises(ValueError):
            self.store.save(6, ['new'], None)

    def test_both_providers_save_in_one_revision(self):
        result = self.store.save(0, ['ASMR'], ['癒し'])
        self.assertEqual(result['revision'], 1)
        self.assertEqual(result['hidden_rplay_tags'], ['ASMR'])
        self.assertEqual(result['hidden_dlsite_tags'], ['癒し'])
        self.assertEqual(self.store.save(1, [], [])['revision'], 2)

    def test_names_merges_favorites_and_old_clients_preserve_metadata(self):
        result = self.store.save(0, tag_names={'힐링': {'ko': '휴식', 'original': 'Relax'}},
                                 tag_aliases={'rest': 'relax', 'relax': '힐링'}, favorite_tags=['힐링'], hidden_tags=['event'])
        self.assertEqual(result['tag_aliases'], {'rest': '힐링', 'relax': '힐링'})
        self.assertEqual(TagVisibility(self.path).read(), result)
        result = self.store.save(1, ['legacy'], [])
        self.assertEqual(result['tag_names']['힐링']['ko'], '휴식')
        self.assertEqual(result['favorite_tags'], ['힐링'])
        self.assertEqual(result['hidden_tags'], ['event'])
        self.assertEqual(result['tag_aliases']['rest'], '힐링')

    def test_cycles_and_invalid_names_leave_existing_file_intact(self):
        self.store.save(0, tag_names={'keep': {'ko': '보존'}})
        original = self.path.read_bytes()
        for update in ({'tag_aliases': {'a': 'b', 'b': 'a'}}, {'tag_aliases': {'a': 'a'}},
                       {'tag_names': {'a': {'ko': 'x\ny'}}}, {'tag_names': {'a': {'ko': None}}},
                       {'tag_names': {'a': {'unknown': 'x'}}}, {'favorite_tags': [None]}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.store.save(1, **update)
            self.assertEqual(self.path.read_bytes(), original)

    def test_display_name_reset_keeps_other_fields(self):
        self.store.save(0, tag_names={'a': {'ko': '수정'}}, favorite_tags=['a'])
        result = self.store.save(1, tag_names={'a': {'ko': '', 'original': ''}})
        self.assertEqual(result['tag_names'], {})
        self.assertEqual(result['favorite_tags'], ['a'])

    def test_corrupt_settings_cannot_be_overwritten(self):
        self.path.write_bytes(b'broken original')
        with self.assertRaises(ValueError):
            self.store.read()
        with self.assertRaises(ValueError):
            self.store.save(0, [])
        self.assertEqual(self.path.read_bytes(), b'broken original')

    def test_concurrent_save_has_one_winner(self):
        barrier = threading.Barrier(2)
        def save(tag):
            barrier.wait()
            try:
                self.store.save(0, [tag]); return 'saved'
            except TagVisibilityConflict:
                return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            self.assertCountEqual(pool.map(save, ['first', 'second']), ['saved', 'conflict'])
        self.assertEqual(self.store.read()['revision'], 1)

    def test_api_authentication_origin_export_and_other_data_preserved(self):
        catalog = Catalog(self.root/'audio.sqlite3')
        work = catalog.create_work('Original')
        edition = catalog.create_edition(work['id'], 'Original edition', 'audio')
        catalog.add_source(edition['id'], 'rplay', '0'*24, 'https://rplay.live/play/'+'0'*24, {'tags': ['행사']})
        original = catalog.works()
        sentinel = self.root/'title-overrides.json'; sentinel.write_bytes(b'unchanged fixture')
        server = make_server(catalog, self.root, port=0, password='fixture-only')
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            def request(method, path, data=None, auth=True, origin=None):
                conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
                headers = {'Content-Type': 'application/json'}
                if auth:
                    headers['Authorization'] = 'Basic '+base64.b64encode(b'admin:fixture-only').decode()
                if origin:
                    headers['Origin'] = origin
                conn.request(method, path, json.dumps(data).encode() if data is not None else None, headers)
                response = conn.getresponse(); raw = response.read(); status = response.status; conn.close()
                return status, json.loads(raw) if raw else None
            self.assertEqual(request('GET', '/api/tag-visibility', auth=False)[0], 401)
            self.assertEqual(request('POST', '/api/tag-visibility', {'revision': 0, 'hidden_rplay_tags': []}, origin='https://other.test')[0], 403)
            status, result = request('POST', '/audio/api/tag-visibility', {'revision': 0, 'hidden_rplay_tags': ['행사']})
            self.assertEqual(status, 200)
            self.assertEqual(result['revision'], 1)
            self.assertEqual(request('GET', '/api/works')[1]['tag_visibility'], result)
            status, result = request('POST', '/api/tag-visibility', {'revision': 1,
                                    'tag_names': {'rest': {'ko': '휴식'}}, 'tag_aliases': {'relax': 'rest'},
                                    'favorite_tags': ['rest'], 'hidden_tags': ['event']})
            self.assertEqual(status, 200)
            self.assertEqual(result['revision'], 2)
            self.assertEqual(request('GET', '/api/works')[1]['tag_visibility'], result)
            self.assertEqual(result['hidden_rplay_tags'], ['행사'])
            self.assertEqual(result['tag_names']['rest']['ko'], '휴식')
            self.assertEqual(request('POST', '/api/tag-visibility', {'revision': 2, 'tag_aliases': {'a':'b','b':'a'}})[0], 400)
            self.assertEqual(request('POST', '/api/tag-visibility', {'revision': 0, 'hidden_rplay_tags': []})[0], 409)
            self.assertEqual(request('GET', '/api/export')[1], {'schema': 1, 'works': original})
            self.assertEqual(catalog.works(), original)
            self.assertEqual(sentinel.read_bytes(), b'unchanged fixture')
            server.tag_visibility.file.write_bytes(b'broken')
            status, result = request('GET', '/api/works')
            self.assertEqual(status, 200)
            self.assertIn('tag_visibility_error', result)
            self.assertEqual(request('POST', '/api/tag-visibility', {'revision': 0, 'hidden_rplay_tags': []})[0], 400)
            self.assertEqual(server.tag_visibility.file.read_bytes(), b'broken')
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
