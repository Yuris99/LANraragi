"""Generated filenames and mocked same-number metadata; never query real media."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from connectors import source_candidates
from sources import filename_hints, canonical_archive_name
from store import Store


class FilenameTests(unittest.TestCase):
    def test_number_is_not_provider_identity_and_multiple_numbers_need_review(self):
        hint=filename_hints('/private/[Artist A] Title [123456].cbz')
        self.assertEqual(hint['artist'],'Artist A')
        self.assertEqual(hint['numbers'],[{'number':'123456','provider':None}])
        self.assertFalse(hint['ambiguous'])
        self.assertNotIn('/private',hint['filename'])
        self.assertTrue(filename_hints('[Artist] Title 123456 654321.cbz')['ambiguous'])
        self.assertEqual(filename_hints('2026 Title.cbz')['numbers'],[])
        self.assertEqual(filename_hints('[C100] Title.cbz')['artist'],'')

    def test_explicit_provider_prefix_and_safe_portable_basename(self):
        self.assertEqual(filename_hints('E123456 [Artist] Title.cbz')['numbers'][0]['provider'],'ehentai')
        name=canonical_archive_name('../Title:*'+('題'*200),'../Artist/'+('가'*200),'hitomi','123456')
        self.assertNotIn('/',name)
        self.assertNotIn(':',name)
        self.assertLess(len(name.encode()),255)
        self.assertTrue(name.endswith('[H123456].cbz'))
        self.assertIn('[U123456]',canonical_archive_name('Title','Artist',None,'123456'))


class OrganizationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'studio.db')

    def test_sync_keeps_original_basename_but_never_auto_assigns_site_or_artist(self):
        self.store.sync_lrr([dict(arcid='a'*40,filename='/private/[Artist] Title [123456].cbz',title='Title',tags='')])
        work=self.store.organization_preview()['items'][0]
        self.assertEqual(work['artist'],'')
        self.assertEqual(work['organization']['artist'],'Artist')
        self.assertEqual(work['sources'],[])
        self.assertEqual(work['archive_filename'],'[Artist] Title [123456].cbz')
        self.assertIn('[U123456]',work['proposed_filename'])

    def test_artist_confirmation_survives_sync_without_locking_title(self):
        record=dict(arcid='a'*40,filename='Title.cbz',title='Old',tags='artist:Remote')
        self.store.sync_lrr([record]);work=self.store.list_works()['items'][0]
        self.store.update_work(work['id'],{'artist':'Confirmed'})
        self.store.sync_lrr([{**record,'title':'New'}])
        actual=self.store.get_work(work['id'])
        self.assertEqual((actual['artist'],actual['title']),('Confirmed','New'))
        self.assertIn('artist:Remote',actual['tags'])

    def test_batch_artist_fill_skips_manual_values_and_keeps_confirmations(self):
        self.store.sync_lrr([dict(arcid='a'*40,filename='[123456] [Artist A] Title.cbz',title='Title',tags=''),
                             dict(arcid='b'*40,filename='[Artist B] Title.cbz',title='Other',tags='artist:Existing')])
        works=self.store.list_works()['items']
        result=self.store.apply_filename_artists([w['id'] for w in works])
        self.assertEqual(result['updated'],1)
        self.assertEqual({w['artist'] for w in self.store.list_works()['items']},{'Artist A','Existing'})
        self.assertEqual(self.store.apply_filename_artists([w['id'] for w in works])['updated'],0)

    def test_matching_cooldown_persists_and_does_not_create_sources(self):
        work=self.store.create_work('Generated')
        self.store.begin_matching(work['id'])
        with self.assertRaises(ValueError):Store(self.store.path).begin_matching(work['id'])
        self.assertEqual(self.store.get_work(work['id'])['sources'],[])


class CandidateTests(unittest.TestCase):
    @staticmethod
    def fetch(url,payload=None):
        if 'f_search=' in url:return '<a href="https://e-hentai.org/g/123456/abc123/">Result</a>'
        if 'api.e-hentai.org' in url:
            assert payload['gidlist']==[[123456,'abc123']]
            return json.dumps({'gmetadata':[{'gid':123456,'title':'Different E title','tags':['artist:E artist']}]})
        if 'gold-usergeneratedcontent' in url:
            return 'var galleryinfo = '+json.dumps({'id':123456,'title':'Different H title','artists':[{'artist':'H artist'}]})+';'
        return json.dumps({'id':123456,'title':{'english':'Different N title'},'tags':[{'type':'artist','name':'N artist'}]})

    def test_all_three_independent_candidates_return_distinct_metadata(self):
        result=source_candidates('123456',self.fetch)
        self.assertEqual([r['provider'] for r in result],['ehentai','hitomi','nhentai'])
        self.assertTrue(all(r['status']=='found' for r in result))
        self.assertEqual(len({r['title'] for r in result}),3)
        self.assertTrue(all(r['artists'] for r in result))

    def test_blocked_site_is_not_substituted_by_another_site(self):
        def fetch(url,payload=None):
            if 'e-hentai.org' in url:raise urllib.error.HTTPError(url,403,'Denied',{},io.BytesIO())
            return self.fetch(url,payload)
        result=source_candidates('123456',fetch)
        self.assertEqual(result[0]['status'],'access_required')
        self.assertIsNone(result[0]['url'])
        self.assertEqual(result[1]['status'],'found')
        self.assertEqual(result[2]['status'],'found')

    def test_ehentai_missing_token_and_wrong_identity_do_not_offer_selection(self):
        def fetch(url,payload=None):
            if 'f_search=' in url:return 'No exact publicly accessible URL'
            if 'gold-usergeneratedcontent' in url:return 'var galleryinfo = {"id":123457,"title":"Wrong"};'
            return '[]'
        result=source_candidates('123456',fetch)
        self.assertEqual([r['status'] for r in result],['needs_url','invalid_response','invalid_response'])
        self.assertTrue(all(r['url'] is None for r in result))

    def test_number_validation_prevents_arbitrary_network_destinations(self):
        for value in ['https://private/', '../123', 123, '1'*13]:
            with self.assertRaises(ValueError):source_candidates(value,self.fetch)


if __name__=='__main__':unittest.main()
