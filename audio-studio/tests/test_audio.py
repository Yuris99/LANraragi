import base64
import contextlib
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog import Catalog
from server import make_server, media_path

TEST_ROOT = Path(__file__).resolve().parents[1] / 'test-results'
TEST_ROOT.mkdir(exist_ok=True)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'audio.db'
        self.store = Catalog(self.path)
        self.work = self.store.create_work('同じ作品')
        self.edition = self.store.create_edition(self.work['id'], '音声版', 'audio', 'ja', {'voice': ['声優']})

    def source(self, edition=None, provider='dlsite', external_id='123', metadata=None):
        return self.store.add_source(edition or self.edition['id'], provider, external_id,
                                     'https://example.test/product/123?locale=ja#original', metadata or {'title': '原題'})

    def test_four_editions_share_original_without_merging(self):
        for kind in ('comic', 'translation', 'voice_comic'):
            self.store.create_edition(self.work['id'], '同じ題名', kind, 'ko')
        editions = self.store.works()[0]['editions']
        self.assertEqual({e['kind'] for e in editions}, {'comic', 'translation', 'voice_comic', 'audio'})
        self.assertEqual(len({e['id'] for e in editions}), 4)

    def test_equal_titles_do_not_merge(self):
        duplicate = self.store.create_work('同じ作品')
        self.assertNotEqual(duplicate['id'], self.work['id'])
        edition = self.store.create_edition(self.work['id'], '音声版', 'audio')
        self.assertNotEqual(edition['id'], self.edition['id'])
        self.assertEqual(len(self.store.works()), 2)

    def test_provider_namespaces_are_distinct(self):
        self.source()
        self.source(provider='dmm')
        self.assertEqual(len(self.store.edition(self.edition['id'])['sources']), 2)

    def test_conflict_rejects_even_within_same_original(self):
        self.source()
        other = self.store.create_edition(self.work['id'], '翻訳', 'translation')
        with self.assertRaises(ValueError):
            self.source(other['id'])
        self.assertEqual(self.store.edition(other['id'])['sources'], [])
        self.assertEqual(len(self.store.works()), 1)

    def test_metadata_is_append_only_lossless_json(self):
        original = {'id': '00123', 'title': '原題', 'nested': {'tags': ['声', None, 3]}, 'unknown': True}
        self.source(metadata=original)
        self.source(metadata={'title': '修正版'})
        source = self.store.edition(self.edition['id'])['sources'][0]
        self.assertEqual(len(source['snapshots']), 2)
        self.assertEqual(source['snapshots'][0]['raw_metadata'], original)
        self.assertEqual(source['snapshots'][0]['submitted_url'], 'https://example.test/product/123?locale=ja#original')
        self.assertEqual(self.store.edition(self.edition['id'])['title'], '音声版')

    def test_ids_preserve_leading_zeroes_and_prefixes(self):
        self.source(external_id='00123')
        self.source(external_id='RJ00123')
        ids = {s['external_id'] for s in self.store.edition(self.edition['id'])['sources']}
        self.assertEqual(ids, {'00123', 'RJ00123'})

    def test_reopen_preserves_catalog(self):
        self.source()
        self.assertEqual(Catalog(self.path).works(), self.store.works())

    def test_reject_existing_foreign_db_without_modification(self):
        old = self.root / 'comic.db'
        with contextlib.closing(sqlite3.connect(old)) as db:
            with db:
                db.execute('CREATE TABLE works (title TEXT)')
                db.execute("INSERT INTO works VALUES('preserved')")
        before = hashlib.sha256(old.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            Catalog(old)
        self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(), before)

    def test_reject_newer_schema_without_modification(self):
        with self.store.db() as db:
            db.execute('PRAGMA user_version=2')
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            Catalog(self.path)
        self.assertEqual(before, self.path.read_bytes())

    def test_track_order_duplicate_and_edition_resume_isolation(self):
        a = self.store.add_track(self.edition['id'], 'First', 'a.wav', 10)
        b = self.store.add_track(self.edition['id'], 'Second', 'b.wav', 0)
        self.store.progress(a['id'], 3.75)
        self.assertEqual(self.store.track(a['id'])['resume'], 3.75)
        self.assertEqual(self.store.track(b['id'])['resume'], 0)
        self.assertEqual([t['position'] for t in self.store.edition(self.edition['id'])['tracks']], [1, 2])
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.add_track(self.edition['id'], 'Duplicate', 'a.wav', 10)
        for seconds in (-1, float('nan'), float('inf'), True, 11):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                self.store.progress(a['id'], seconds)

    def test_unknown_parents_and_comic_tracks_rejected(self):
        with self.assertRaises(KeyError):
            self.store.create_edition('f' * 32, 'Missing', 'audio')
        comic = self.store.create_edition(self.work['id'], 'Comic', 'comic')
        with self.assertRaises(ValueError):
            self.store.add_track(comic['id'], 'Track', 'a.wav')
        with self.assertRaises(ValueError):
            self.store.create_edition(self.work['id'], 'Bad', 'other')

    def test_invalid_metadata_does_not_create_source(self):
        for raw in ([], {'number': float('nan')}):
            with self.assertRaises(ValueError):
                self.store.add_source(self.edition['id'], 'dlsite', '1', 'https://example.test/1', raw)
        self.assertEqual(self.store.edition(self.edition['id'])['sources'], [])

    def test_search_export_retain_metadata_and_credits(self):
        self.source(metadata={'original': 'rare word'})
        found = self.store.works('rare word')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['editions'][0]['credits'], {'voice': ['声優']})
        self.assertEqual(self.store.works('not present'), [])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / 'media'
        self.media.mkdir()
        with wave.open(str(self.media / 'test.wav'), 'wb') as output:
            output.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            output.writeframes(b'\x00\x00' * 8000)
        self.raw = (self.media / 'test.wav').read_bytes()
        self.store = Catalog(self.root / 'catalog.db')
        self.server = make_server(self.store, self.media, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def request(self, path, data=None, headers=None, method=None):
        raw = None if data is None else json.dumps(data).encode()
        headers = {**({'Content-Type': 'application/json'} if data is not None else {}), **(headers or {})}
        request = urllib.request.Request(self.base + path, data=raw, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as response:
            return response.code, response.headers, response.read()

    def post(self, path, data):
        code, _, body = self.request(path, data)
        self.assertEqual(code, 201, body)
        return json.loads(body)

    def track(self):
        work = self.post('/api/works', {'title': 'Synthetic fixture'})
        edition = self.post('/api/editions', {'work_id': work['id'], 'title': 'Audio', 'kind': 'audio'})
        return self.post('/api/editions/' + edition['id'] + '/tracks',
                         {'title': 'Silent WAV', 'relative_path': 'test.wav', 'duration': 1})

    def test_full_catalog_flow_export_and_progress(self):
        track = self.track()
        self.post('/api/editions/' + track['edition_id'] + '/sources',
                  {'provider': 'dlsite', 'external_id': 'RJ00001', 'url': 'https://example.test/RJ00001',
                   'raw_metadata': {'name': 'Original', 'nested': ['one', 'two']}})
        code, _, _ = self.request('/api/tracks/' + track['id'] + '/progress', {'seconds': 0.5})
        self.assertEqual(code, 200)
        code, _, raw = self.request('/api/export')
        self.assertEqual(code, 200)
        edition = json.loads(raw)['works'][0]['editions'][0]
        self.assertEqual(edition['tracks'][0]['resume'], 0.5)
        self.assertEqual(edition['sources'][0]['snapshots'][0]['raw_metadata']['nested'], ['one', 'two'])

    def test_media_full_range_suffix_head_and_invalid_range(self):
        track = self.track()
        path = '/api/tracks/' + track['id'] + '/media'
        code, headers, raw = self.request(path)
        self.assertEqual((code, raw), (200, self.raw))
        for value, expected in [('bytes=0-43', self.raw[:44]), ('bytes=44-', self.raw[44:]),
                                ('bytes=-12', self.raw[-12:]), ('bytes=0-99999', self.raw)]:
            code, headers, raw = self.request(path, headers={'Range': value})
            self.assertEqual((code, raw), (206, expected))
            self.assertEqual(int(headers['Content-Length']), len(expected))
            self.assertIn('Content-Range', headers)
        code, headers, raw = self.request(path, method='HEAD')
        self.assertEqual((code, raw), (200, b''))
        self.assertEqual(int(headers['Content-Length']), len(self.raw))
        for value in ('bytes=999999-', 'bytes=5-2', 'bytes=-0', 'bytes=0-1,3-4', 'nonsense'):
            code, headers, _ = self.request(path, headers={'Range': value})
            self.assertEqual(code, 416, value)
            self.assertEqual(headers['Content-Range'], f'bytes */{len(self.raw)}')
        self.assertEqual((self.media / 'test.wav').read_bytes(), self.raw)

    def test_media_path_escape_extension_and_symlink_rejected(self):
        (self.root / 'outside.wav').write_bytes(self.raw)
        for value in ('../outside.wav', str(self.root / 'outside.wav'), 'C:/outside.wav',
                      '//server/file.wav', 'test.wav:stream', 'test.txt', 'missing.wav', '..\\outside.wav'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                media_path(self.media, value)
        try:
            (self.media / 'link.wav').symlink_to(self.root / 'outside.wav')
        except OSError:
            return  # Windows may lack developer mode symlink privilege.
        with self.assertRaises(ValueError):
            media_path(self.media, 'link.wav')

    def test_registration_rejects_escaping_file(self):
        track = self.track()
        code, _, _ = self.request('/api/editions/' + track['edition_id'] + '/tracks',
                                  {'title': 'bad', 'relative_path': '../outside.wav'})
        self.assertEqual(code, 400)

    def test_auth_host_csrf_and_json_requirements(self):
        self.assertEqual(self.request('/api/health', headers={'Host': 'evil.test'})[0], 403)
        self.assertEqual(self.request('/api/works', {'title': 'bad'}, headers={'Origin': 'https://evil.test'})[0], 403)
        self.assertEqual(self.request('/api/works', {'title': 'bad'}, headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertEqual(self.request('/api/works', {'title': 'bad'}, headers={'Content-Type': 'text/plain'})[0], 415)
        self.server.password = 'test-only-password'
        self.assertEqual(self.request('/api/health')[0], 401)
        auth = 'Basic ' + base64.b64encode(b'admin:test-only-password').decode()
        self.assertEqual(self.request('/api/health', headers={'Authorization': auth})[0], 200)

    def test_assets_and_unavailable_upstream_routes(self):
        for path in ('/', '/app.js', '/style.css'):
            code, headers, _ = self.request(path)
            self.assertEqual(code, 200)
            self.assertIn("default-src 'self'", headers['Content-Security-Policy'])
            if path == '/app.js':
                self.assertTrue(headers['Content-Type'].startswith('text/javascript'))
        self.assertFalse(json.loads(self.request('/api/health')[2])['upstream_access'])
        for path in ('/api/sync', '/api/jobs', '/api/media/anything'):
            self.assertEqual(self.request(path)[0], 404)

    def test_refuses_port_already_owned_by_another_server(self):
        with self.assertRaises(OSError):
            make_server(self.store, self.media, port=self.server.server_port)
        self.assertEqual(self.request('/api/health')[0], 200)


if __name__ == '__main__':
    unittest.main()
