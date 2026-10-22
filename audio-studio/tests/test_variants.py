import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_audio as fixtures
from subtitles import parse_subtitles


class VariantCatalogTests(unittest.TestCase):
    setUp = fixtures.CatalogTests.setUp
    source = fixtures.CatalogTests.source
    def test_rj_grouping_never_merges_and_duplicate_rolls_back(self):
        self.store.add_code(self.work['id'], 'RJ01234567')
        self.store.add_code(self.work['id'], 'RJ01234567')
        other = self.store.create_work('別作品')
        with self.assertRaises(ValueError):
            self.store.add_code(other['id'], 'RJ01234567')
        count = len(self.store.works())
        with self.assertRaises(ValueError):
            self.store.create_work('Duplicate RJ', 'RJ01234567')
        self.assertEqual(len(self.store.works()), count)
        self.assertEqual(len(self.store.works('RJ01234567')), 1)
        self.assertEqual(len(self.store.edition(self.edition['id'])['sources']), 0)

    def test_video_and_translation_variants_keep_identity_and_metadata(self):
        self.source()
        for media_type, translation in [('audio','none'),('audio','subtitles'),('video','embedded')]:
            updated = self.store.set_profile(self.edition['id'], media_type, translation)
            self.assertEqual(updated['profile'], {'media_type':media_type,'translation':translation})
            self.assertEqual(updated['sources'][0]['snapshots'][0]['raw_metadata'], {'title':'原題'})
        with self.assertRaises(ValueError):
            self.store.set_profile(self.edition['id'],'audio','embedded')

    def test_persistent_order_exact_permutation_and_rollback(self):
        a = self.store.add_track(self.edition['id'],'First','a.wav')
        b = self.store.add_track(self.edition['id'],'Second','b.wav')
        self.store.progress(a['id'], 1.2)
        updated = self.store.reorder_tracks(self.edition['id'], [b['id'],a['id']])
        self.assertEqual([t['id'] for t in updated['tracks']], [b['id'],a['id']])
        for ids in ([a['id']], [a['id'],a['id']], [a['id'],'unknown']):
            with self.assertRaises(ValueError):
                self.store.reorder_tracks(self.edition['id'], ids)
        self.assertEqual([t['id'] for t in self.store.edition(self.edition['id'])['tracks']], [b['id'],a['id']])
        self.assertEqual(self.store.track(a['id'])['resume'],1.2)
        self.assertEqual([t['id'] for t in fixtures.Catalog(self.path).edition(self.edition['id'])['tracks']], [b['id'],a['id']])


class VariantHTTPTests(unittest.TestCase):
    setUp = fixtures.HTTPTests.setUp
    close = fixtures.HTTPTests.close
    request = fixtures.HTTPTests.request
    post = fixtures.HTTPTests.post
    track = fixtures.HTTPTests.track
    def test_subtitle_registration_read_and_escape_rejection(self):
        (self.media/'test.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\n안녕하세요\n', encoding='utf-8')
        track = self.track()
        sub = self.post('/api/tracks/'+track['id']+'/subtitles', {'relative_path':'test.srt','language':'ko','label':'한국어'})
        code, _, raw = self.request('/api/subtitles/'+sub['id'])
        self.assertEqual(code,200)
        self.assertIn('안녕하세요',raw.decode())
        for path in ('../outside.srt','test.wav','missing.srt'):
            self.assertEqual(self.request('/api/tracks/'+track['id']+'/subtitles', {'relative_path':path})[0],400)
        (self.media/'invalid.srt').write_text('wrong format',encoding='utf-8')
        self.assertEqual(self.request('/api/tracks/'+track['id']+'/subtitles', {'relative_path':'invalid.srt'})[0],400)

    def test_profile_and_order_endpoints(self):
        track = self.track()
        edition_id = track['edition_id']
        code,_,_ = self.request('/api/editions/'+edition_id+'/profile',{'media_type':'video','translation':'embedded'})
        self.assertEqual(code,200)
        code,_,_ = self.request('/api/editions/'+edition_id+'/order',{'track_ids':[track['id']]})
        self.assertEqual(code,200)


class SubtitleTests(unittest.TestCase):
    def test_srt_unicode_multiline_and_plain_text(self):
        cues = parse_subtitles('\ufeff1\r\n00:00:01,250 --> 00:00:03,000\r\n<b>첫 줄</b>\r\n&lt;second&gt;\r\n')
        self.assertEqual(cues,[{'start':1.25,'end':3.0,'text':'첫 줄\n<second>'}])

    def test_vtt_identifiers_settings_and_overlaps(self):
        cues = parse_subtitles('WEBVTT\n\nNOTE comment\nignored\n\ncue1\n00:01.000 --> 00:03.000 align:start\none\n\n00:02.000 --> 00:04.000\ntwo')
        self.assertEqual(len(cues),2)
        self.assertEqual(cues[1]['start'],2)

    def test_malformed_and_invalid_times_rejected(self):
        for value in ('','wrong','1\n00:00:03,000 --> 00:00:01,000\nreversed','00:70.000 --> 00:80.000\nbad'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                parse_subtitles(value)
