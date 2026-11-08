import base64
import contextlib
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog import Catalog
from library_files import LibraryFiles, LibraryConflict, browse, decode_text, voice_path
from server import make_server


class LibraryFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = LibraryFiles(self.root / 'data')
        self.identifier = 'a' * 32
        self.track = 'b' * 32

    def test_read_does_not_create_data(self):
        self.assertEqual(self.files.read()['revision'], 0)
        self.assertFalse(self.files.root.exists())

    def test_playlist_save_copy_remove_and_reload_never_moves_tracks(self):
        value = self.files.playlist(0, '', '밤', [self.track])
        original = value['playlists'][0]
        value = self.files.playlist(1, '', '복사', original['track_ids'])
        self.assertEqual(len(value['playlists']), 2)
        value = self.files.playlist(2, original['id'], None, None, True)
        reopened = LibraryFiles(self.files.root).read()
        self.assertEqual(reopened, value)
        self.assertEqual(reopened['playlists'][0]['track_ids'], [self.track])

    def test_stale_revision_and_corrupt_state_do_not_overwrite(self):
        self.files.playlist(0, '', 'A', [])
        before = self.files.file.read_bytes()
        with self.assertRaises(LibraryConflict):
            self.files.playlist(0, '', 'B', [])
        self.assertEqual(self.files.file.read_bytes(), before)
        self.files.file.write_bytes(b'bad')
        with self.assertRaises(ValueError):
            self.files.playlist(1, '', 'B', [])
        self.assertEqual(self.files.file.read_bytes(), b'bad')

    def test_upload_raw_bytes_preserved_and_duplicate_names_do_not_replace(self):
        raw = '説明\n原文'.encode('cp932')
        value = self.files.upload(0, self.identifier, '', '説明.txt', base64.b64encode(raw).decode(), 'cp932')
        first = value['uploads'][0]
        value = self.files.upload(1, self.identifier, '', '説明.txt', base64.b64encode(b'new').decode())
        self.assertNotEqual(first['id'], value['uploads'][1]['id'])
        row, path = self.files.uploaded(first['id'])
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(decode_text(raw, row['encoding'])[0], '説明\n原文')

    def test_subtitle_requires_explicit_track_and_valid_parser(self):
        encoded = base64.b64encode(b'1\n00:00:00,000-->00:00:01,000\ncaption').decode()
        with self.assertRaises(ValueError):
            self.files.upload(0, self.identifier, '', 'a.srt', encoded)
        self.assertFalse(self.files.root.exists())
        with self.assertRaises(ValueError):
            self.files.upload(0, self.identifier, self.track, 'a.srt', base64.b64encode(b'not subtitles').decode())
        value = self.files.upload(0, self.identifier, self.track, 'a.srt', encoded)
        works = [{'editions': [{'tracks': [{'id': self.track, 'subtitles': []}]}]}]
        self.files.attach(works)
        linked = works[0]['editions'][0]['tracks'][0]['subtitles'][0]
        self.assertEqual(linked['id'], value['uploads'][0]['id'])
        self.assertEqual(linked['language'], 'und')
        self.assertFalse(linked['sync_verified'])

    def test_invalid_names_pdf_and_encoding_create_nothing(self):
        for name, raw in [('../a.txt', b'text'), ('a.html', b'<script>'), ('a.pdf', b'not pdf'), ('a.txt', b'\x00\x00')]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.files.upload(0, self.identifier, '', name, base64.b64encode(raw).decode())
        self.assertFalse(self.files.root.exists())

    def test_browse_is_one_level_whitelisted_and_blocks_escape(self):
        folder = self.root / 'Voice'; folder.mkdir()
        (folder / '説明.txt').write_text('Read', encoding='utf-8')
        (folder / '.env').write_text('PRIVATE', encoding='utf-8')
        (folder / 'config.json').write_text('PRIVATE', encoding='utf-8')
        (folder / '作品').mkdir()
        (folder / '作品' / 'deep.pdf').write_bytes(b'%PDF-')
        rows = browse(folder)['items']
        self.assertEqual([r['name'] for r in rows], ['作品', '説明.txt'])
        for relative in ['../', '/etc', 'C:/x', '作品/../説明.txt', '.env', 'a\\b', 'a:b']:
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                voice_path(folder, relative, file=True)

    def test_symlink_is_never_browsed_or_opened(self):
        folder = self.root / 'Voice'; folder.mkdir()
        outside = self.root / 'outside'; outside.mkdir(); (outside / 'x.txt').write_text('secret')
        try:
            (folder / 'link').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('symlink creation unavailable')
        self.assertEqual(browse(folder)['items'], [])
        with self.assertRaises(ValueError):
            voice_path(folder, 'link/x.txt', True)


class LibraryFilesHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name); self.media = root / 'media'; self.media.mkdir()
        self.catalog = Catalog(root / 'data' / 'fixture.db')
        self.work = self.catalog.create_work('Fixture')
        self.edition = self.catalog.create_edition(self.work['id'], 'Original', 'audio')
        self.track = self.catalog.add_track(self.edition['id'], 'Track', 'track.wav', 10)
        self.catalog.progress(self.track['id'], 3)
        self.original = self.catalog.works()
        self.server = make_server(self.catalog, self.media, port=0, password='fixture-only')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.stop)
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, path, data=None, headers=None, status=200):
        h = {'Authorization': 'Basic ' + base64.b64encode(b'admin:fixture-only').decode()}
        if data is not None:
            h['Content-Type'] = 'application/json'
        h.update(headers or {})
        request = urllib.request.Request(self.url + path, json.dumps(data).encode() if data is not None else None, h)
        try:
            result = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            result = error
        with contextlib.closing(result):
            self.assertEqual(result.status, status)
            return result.headers, result.read()

    def test_auth_origin_missing_track_and_static_mime(self):
        self.request('/api/files', headers={'Authorization': ''}, status=401)
        data = {'revision': 0, 'name': 'List', 'track_ids': [self.track['id']]}
        self.request('/api/playlists', data, headers={'Origin': 'https://evil.test'}, status=403)
        self.request('/api/playlists', data | {'track_ids': ['f' * 32]}, status=404)
        h, _ = self.request('/audio/files-playlists.js')
        self.assertIn('text/javascript', h['Content-Type'])
        self.assertIn("script-src 'self'", h['Content-Security-Policy'])
        self.assertFalse(self.server.library_files.file.exists())

    def test_upload_subtitles_api_catalog_export_and_progress_preserved(self):
        data = {'revision': 0, 'edition_id': self.edition['id'], 'track_id': self.track['id'],
                'name': 'translation.srt', 'content': base64.b64encode(b'1\n00:00:00,000 --> 00:00:01,000\nfixture').decode()}
        _, raw = self.request('/audio/api/uploads', data, status=201)
        identifier = json.loads(raw)['uploads'][0]['id']
        _, raw = self.request('/api/subtitles/' + identifier)
        self.assertEqual(json.loads(raw)['cues'][0]['text'], 'fixture')
        _, raw = self.request('/api/works')
        linked = json.loads(raw)['works'][0]['editions'][0]['tracks'][0]['subtitles']
        self.assertEqual(linked[0]['origin'], 'upload')
        _, raw = self.request('/api/export')
        self.assertEqual(json.loads(raw)['works'], self.original)
        self.assertEqual(self.catalog.works(), self.original)
        self.request('/api/uploads', data, status=409)
        self.assertEqual(len(list(self.server.library_files.uploads.iterdir())), 1)

    def test_pdf_range_text_encoding_and_attachment_mime(self):
        raw = b'%PDF-1.4\n' + b'0' * 100
        (self.media / 'explain.pdf').write_bytes(raw)
        (self.media / 'readme.txt').write_bytes('説明'.encode('cp932'))
        h, value = self.request('/api/files/content?path=explain.pdf', headers={'Range': 'bytes=0-4'}, status=206)
        self.assertEqual(value, b'%PDF-')
        self.assertEqual(h['Content-Type'], 'application/pdf')
        self.assertIn('sandbox', h['Content-Security-Policy'])
        _, value = self.request('/api/files/text?path=readme.txt&encoding=cp932')
        self.assertEqual(json.loads(value)['text'], '説明')
        self.request('/api/files/text?path=../fixture.db', status=400)
        self.assertFalse(self.server.library_files.file.exists())


if __name__ == '__main__':
    unittest.main()
