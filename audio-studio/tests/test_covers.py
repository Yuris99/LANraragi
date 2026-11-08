import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog import Catalog
from covers import CoverUnavailable, IMAGE_LIMIT, NoRedirect, RplayCovers, allowed_url, public_get
from server import make_server

ID = '612bbf2c16d4881b2056bb44'
PAGE = 'https://rplay.live/play/' + ID
IMAGE = 'https://pb3.rplay.live/thumbnail/' + ID + '_ko'
JPEG = b'\xff\xd8\xff\xdb' + bytes(16)
RJ = 'RJ051890'
DLSITE_API = 'https://www.dlsite.com/maniax/api/=/product.json?workno=' + RJ
DLSITE_IMAGE = 'https://img.dlsite.jp/modpub/images2/work/doujin/RJ052000/' + RJ + '_img_main.jpg'


def dlsite_product(external_id=RJ):
    return json.dumps([{'workno': external_id, 'image_main': {'url': DLSITE_IMAGE.removeprefix('https:')},
                       'genres_replaced': [{'name': 'ASMR'}, {'name': '睡眠'}, {'name': 'ASMR'}],
                       'custom_genres': [{'name': 'campaign'}]}]).encode()


def dlsite_edition():
    return {'credits': {'nas_import': {'provider': 'dlsite', 'source_id': RJ, 'root': 'dlsite/work'}}, 'sources': []}


def edition(metadata=None, url=PAGE):
    return {'sources': [{'provider': 'rplay', 'external_id': ID, 'snapshots': [
        {'submitted_url': url, 'raw_metadata': metadata or {}}]}]}


class CoversTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'test-results')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_original_page_fallback_cache_and_concurrent_readers(self):
        calls = []
        def fetch(url, limit):
            calls.append(url)
            return ('<meta content="' + IMAGE + '" property="og:image">').encode() if url == PAGE else JPEG
        covers = RplayCovers(self.root / 'covers', fetch)
        results = []
        threads = [threading.Thread(target=lambda: results.append(covers.get(edition()))) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(results, [(JPEG, 'image/jpeg')] * 4)
        self.assertEqual(calls, [PAGE, IMAGE])
        self.assertEqual(RplayCovers(self.root / 'covers', lambda *_: self.fail('Cache was not reused')).get(edition()), (JPEG, 'image/jpeg'))

    def test_existing_metadata_image_avoids_page_fetch(self):
        calls = []
        covers = RplayCovers(self.root / 'covers', lambda url, limit: calls.append(url) or JPEG)
        covers.get(edition({'sidecars': {'thumbnail_url': IMAGE}}))
        self.assertEqual(calls, [IMAGE])

    def test_unavailable_cover_does_not_retry_on_each_render(self):
        calls = []
        covers = RplayCovers(self.root / 'covers', lambda url, limit: calls.append(url) or b'<html></html>')
        for _ in range(2):
            with self.assertRaises(CoverUnavailable): covers.get(edition())
        self.assertEqual(calls, [PAGE])
        self.assertFalse((self.root / 'covers').exists())

    def test_private_or_unrelated_urls_and_redirects_are_rejected(self):
        for url in ['http://rplay.live/play/' + ID, PAGE + '?token=x', 'https://rplay.live.evil.test/play/' + ID,
                    'https://admin:secret@rplay.live/play/' + ID, 'https://127.0.0.1/play/' + ID]:
            self.assertFalse(allowed_url(url, ID))
        self.assertFalse(allowed_url(IMAGE.replace(ID, '0' * 24), ID, image=True))
        with self.assertRaises(CoverUnavailable): NoRedirect().redirect_request(None, None, None, None, None, None)
        private_address = [(2, 1, 6, '', ('127.0.0.1', 443))]
        with patch('covers.socket.getaddrinfo', return_value=private_address), patch('covers.urllib.request.build_opener') as opener:
            with self.assertRaises(CoverUnavailable): public_get(PAGE, 100)
            opener.assert_not_called()

    def test_svg_html_oversized_images_and_unrelated_source_are_not_cached(self):
        for data in [b'<svg onload="alert(1)"></svg>', b'<html>login</html>', JPEG + bytes(IMAGE_LIMIT)]:
            covers = RplayCovers(self.root / 'covers', lambda *_: data)
            with self.assertRaises(CoverUnavailable): covers.get(edition({'thumbnail': IMAGE}))
        called = []
        covers = RplayCovers(self.root / 'covers', lambda *_: called.append(True))
        with self.assertRaises(CoverUnavailable): covers.get(edition(url='https://example.test/play/' + ID))
        self.assertEqual(called, [])

    def test_http_auth_head_and_missing_cover(self):
        catalog = Catalog(self.root / 'test.db')
        work = catalog.create_work('표지 검증')
        row = catalog.create_edition(work['id'], '원본', 'audio')
        catalog.add_source(row['id'], 'rplay', ID, PAGE, {})
        server = make_server(catalog, self.root / 'media', port=0, password='fixture-only')
        server.covers = RplayCovers(self.root / 'covers', lambda url, limit: ('<meta property="og:image" content="' + IMAGE + '">').encode() if url == PAGE else JPEG)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        self.addCleanup(thread.join);self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}/api/editions/{row["id"]}/cover'
        with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(url)
        self.assertEqual(error.exception.code, 401)
        import base64
        headers = {'Authorization': 'Basic ' + base64.b64encode(b'admin:fixture-only').decode()}
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as response:
            self.assertEqual(response.read(), JPEG)
            self.assertEqual(response.headers['Content-Type'], 'image/jpeg')
            self.assertIn('private', response.headers['Cache-Control'])
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers, method='HEAD')) as response:
            self.assertEqual(response.read(), b'')
            self.assertEqual(response.headers['Content-Length'], str(len(JPEG)))
        missing = catalog.create_edition(work['id'], '표지 없는 판본', 'audio')
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(urllib.request.Request(url.replace(row['id'], missing['id']), headers=headers))
        self.assertEqual(error.exception.code, 404)
        dlsite = catalog.create_edition(work['id'], 'DLsite', 'audio', credits=dlsite_edition()['credits'])
        before = catalog.edition(dlsite['id'])
        server.covers = RplayCovers(self.root / 'dlsite-covers', lambda u, n: dlsite_product() if u == DLSITE_API else JPEG)
        info_url = url.replace(row['id'], dlsite['id']).replace('/cover', '/source-info')
        with urllib.request.urlopen(urllib.request.Request(info_url, headers=headers)) as response:
            self.assertEqual(json.load(response), {'tags': ['ASMR', '睡眠'], 'titles': {}, 'title_sources': {}, 'available': True})
        refresh_url = info_url.replace('/source-info', '/cover/refresh')
        with urllib.request.urlopen(urllib.request.Request(refresh_url, headers={**headers, 'Content-Type': 'application/json'}, data=b'{}')) as response:
            self.assertTrue(json.load(response)['available'])
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(urllib.request.Request(refresh_url, headers={**headers, 'Content-Type': 'application/json', 'Origin': 'https://other.test'}, data=b'{}'))
        self.assertEqual(error.exception.code, 403)
        works_url = info_url.split('/api/editions/')[0] + '/api/works'
        with urllib.request.urlopen(urllib.request.Request(works_url, headers=headers)) as response:
            self.assertEqual(json.load(response)['works'][0]['source_info_titles'], {})
        with urllib.request.urlopen(urllib.request.Request(works_url.replace('/api/works', '/api/export'), headers=headers)) as response:
            self.assertNotIn('source_info_titles', json.load(response)['works'][0], 'Export retains the stored catalog without derived display metadata')
        self.assertEqual(catalog.edition(dlsite['id']), before, 'Public info never rewrites credits or source snapshots')
        with self.assertRaises(KeyError): catalog.edition('0' * 32)

    def test_dlsite_product_cover_and_tags_share_persistent_cache(self):
        calls = []
        def fetch(url, limit):
            calls.append(url)
            return dlsite_product() if url == DLSITE_API else JPEG
        covers = RplayCovers(self.root / 'covers', fetch)
        self.assertEqual(covers.get(dlsite_edition()), (JPEG, 'image/jpeg'))
        self.assertEqual(covers.info(dlsite_edition())['tags'], ['ASMR', '睡眠'])
        self.assertEqual(calls, [DLSITE_API, DLSITE_IMAGE])
        cached = RplayCovers(self.root / 'covers', lambda *_: self.fail('Persistent cache not reused'))
        self.assertEqual(cached.info(dlsite_edition())['tags'], ['ASMR', '睡眠'])
        self.assertEqual(cached.get(dlsite_edition()), (JPEG, 'image/jpeg'))

    def test_dlsite_identifiers_domains_queries_and_api_identity_are_checked(self):
        self.assertTrue(allowed_url(DLSITE_API, RJ, product=True))
        self.assertTrue(allowed_url(DLSITE_IMAGE, RJ, image=True))
        for url in [DLSITE_API + '&url=http://127.0.0.1', DLSITE_API.replace('workno='+RJ, 'workno=RJ999999'), DLSITE_API.replace('www.dlsite.com', 'www.dlsite.com.evil.test')]:
            self.assertFalse(allowed_url(url, RJ, product=True))
        self.assertFalse(allowed_url(DLSITE_IMAGE.replace(RJ+'_img_main', 'RJ999999_img_main'), RJ, image=True))
        calls = []
        covers = RplayCovers(self.root / 'covers', lambda url, limit: calls.append(url) or dlsite_product('RJ999999'))
        for _ in range(2):
            with self.assertRaises(CoverUnavailable): covers.info(dlsite_edition())
        self.assertEqual(calls, [DLSITE_API])

    def test_registered_local_artwork_is_read_only_and_preferred(self):
        folder = self.root / 'media' / 'DLsite' / 'work';folder.mkdir(parents=True)
        artwork = folder / 'folder.jpg';artwork.write_bytes(JPEG)
        covers = RplayCovers(self.root / 'covers', lambda *_: self.fail('Existing local cover should be preferred'), media_root=self.root/'media')
        self.assertEqual(covers.get(dlsite_edition()), (JPEG, 'image/jpeg'))
        self.assertEqual(artwork.read_bytes(), JPEG)
        self.assertFalse((self.root / 'covers').exists())
        unsafe = dlsite_edition();unsafe['credits']['nas_import']['root'] = 'dlsite/../../outside'
        self.assertIsNone(covers.local_cover(unsafe))

    def test_official_translation_cover_and_two_titles_keep_distinct_ids(self):
        translated_id = 'RJ01225213'
        original = json.loads(dlsite_product())[0]
        original.update(work_name='日本語の作品', translation_info={'lang': 'JPN'}, language_editions=[{'workno': translated_id, 'lang': 'KO_KR'}])
        translated = {'workno': translated_id, 'work_name': '공식 한국어 제목', 'translation_info': {'lang': 'KO_KR', 'original_workno': RJ},
                      'language_editions': [{'workno': RJ, 'lang': 'CHI_HANS,JPN'}], 'image_main': {'workno': RJ, 'url': DLSITE_IMAGE}}
        calls = []
        def fetch(url, limit):
            calls.append(url)
            return JPEG if url == DLSITE_IMAGE else json.dumps([translated if translated_id in url else original]).encode()
        covers = RplayCovers(self.root / 'covers', fetch)
        row = dlsite_edition();row['credits']['nas_import']['source_id'] = translated_id
        self.assertEqual(covers.get(row), (JPEG, 'image/jpeg'))
        info = covers.info(row)
        self.assertEqual(info['titles'], {'ja': '日本語の作品', 'ko': '공식 한국어 제목'})
        self.assertEqual(info['title_sources'], {'ja': RJ, 'ko': translated_id})
        self.assertEqual(info['external_id'], translated_id)
        self.assertEqual(info['image_external_id'], RJ)
        self.assertFalse(allowed_url(DLSITE_IMAGE, translated_id, image=True), 'Arbitrary snapshots cannot borrow another RJ cover')
        self.assertEqual(len(calls), 4)
        restarted = RplayCovers(self.root / 'covers', lambda *_: self.fail('Cached titles should survive restart'))
        self.assertEqual(restarted.info(row)['titles'], info['titles'])

    def test_unrelated_official_image_is_not_accepted_and_old_cache_is_upgraded(self):
        directory = self.root / 'covers';directory.mkdir()
        (directory / ('dlsite-' + RJ + '.json')).write_text(json.dumps({'external_id': RJ, 'tags': ['old'], 'image': None}), encoding='utf-8')
        product = json.loads(dlsite_product())[0]
        product['work_name'] = '原文'
        product['image_main'] = {'workno': 'RJ999999', 'url': DLSITE_IMAGE.replace(RJ + '_img', 'RJ999999_img')}
        calls = []
        covers = RplayCovers(directory, lambda url, limit: calls.append(url) or json.dumps([product]).encode())
        self.assertIsNone(covers.info(dlsite_edition())['image'])
        self.assertEqual(covers.info(dlsite_edition())['titles'], {'ja': '原文'})
        self.assertEqual(calls, [DLSITE_API])

    def test_retry_only_rechecks_missing_cover_and_keeps_positive_cache(self):
        calls = [];ready = False
        def fetch(url, limit):
            calls.append(url)
            if url == PAGE:
                return ('<meta property="og:image" content="' + IMAGE + '">').encode() if ready else b'<html></html>'
            return JPEG
        covers = RplayCovers(self.root / 'covers', fetch)
        with self.assertRaises(CoverUnavailable): covers.get(edition())
        ready = True
        self.assertEqual(covers.get(edition(), retry=True), (JPEG, 'image/jpeg'))
        count = len(calls)
        self.assertEqual(covers.get(edition(), retry=True), (JPEG, 'image/jpeg'))
        self.assertEqual(len(calls), count, 'A good cover is not overwritten on retry')

    def test_saved_translation_url_uses_canonical_api_without_following_query(self):
        original_url = 'https://www.dlsite.com/maniax/work/=/product_id/RJ999999.html/?translation=' + RJ
        row = dlsite_edition();row['sources'] = [{'provider': 'dlsite', 'external_id': RJ, 'snapshots': [{'submitted_url': original_url, 'raw_metadata': {}}]}]
        calls = []
        covers = RplayCovers(self.root / 'covers', lambda url, limit: calls.append(url) or (dlsite_product() if url == DLSITE_API else JPEG))
        self.assertEqual(covers.get(row), (JPEG, 'image/jpeg'))
        self.assertEqual(calls, [DLSITE_API, DLSITE_IMAGE])
        self.assertEqual(row['sources'][0]['snapshots'][0]['submitted_url'], original_url)


if __name__ == '__main__':
    unittest.main()
