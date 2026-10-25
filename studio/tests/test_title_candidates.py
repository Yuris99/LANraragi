"""Synthetic titles and source candidates; original records remain unchanged."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from sources import clean_title
from metadata import compare_metadata,counterpart_candidates,parse_html,parse_hitomi_json
from store import Store
from auto_sources import AutoLinker
from test_metadata import E,H,eh_html,hitomi_js


class TitleCandidateTests(unittest.TestCase):
    def test_title_cleanup_preserves_volumes_years_and_unknown_brackets(self):
        cases=[('[Author] A Garden 2 (123456)',['Author'],['123456'],'A Garden 2'),
               ('[Author, Other] A Garden 2 [Korean] (123456)',['Author','Other'],['123456'],'A Garden 2'),
               ('(COMITIA124) [Circle (Author)] A Garden 2 [韓国翻訳]',[],[],'A Garden 2'),
               ('A Garden Vol. 2',[],['123456'],'A Garden Vol. 2'),
               ('1984',[],['1984'],'1984'),('A Garden (2024)',[],[],'A Garden (2024)'),
               ('[Special title] A Garden',[],[],'[Special title] A Garden'),
               ('A Garden (999999)',[],['123456'],'A Garden (999999)')]
        for title,artists,ids,expected in cases:
            with self.subTest(title=title):self.assertEqual(clean_title(title,artists,ids),expected)

    def test_store_returns_clean_display_without_rewriting_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'catalog.db')
            title='[Author] A Garden 2 (123456)'
            work=store.create_work(title,'Author')
            listed=store.list_works()['items'][0]
            self.assertEqual((work['title'],listed['title']),(title,title))
            self.assertEqual((work['display_title'],listed['display_title']),('A Garden 2','A Garden 2'))
            self.assertEqual(store.get_work(work['id'])['artist'],'Author')

    def test_counterpart_search_uses_clean_title_and_keeps_strict_language(self):
        base=parse_hitomi_json(H,hitomi_js())
        base['title']='[Fixture] A Garden 2 (123456)'
        calls=[]
        def fetch(url):
            calls.append(url)
            if 'f_search=' in url:return '<a href="'+E+'">candidate</a>'
            return eh_html(title='A Garden 2').replace('ta_language:korean','ta_language:japanese')
        result=counterpart_candidates(base,fetch)
        self.assertEqual(calls[0],'https://e-hentai.org/?f_search=A%20Garden%202')
        comparison=result['items'][0]['comparison']
        self.assertEqual(comparison['title_similarity'],1)
        self.assertFalse(comparison['language_match'])
        self.assertFalse(comparison['automatic_eligible'])

    def test_same_language_candidate_survives_top_ten_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'catalog.db');work=store.create_work('Original title')
            baseline=parse_hitomi_json(H,hitomi_js())
            store.import_metadata(work['id'],baseline)
            foreign=parse_html(E,eh_html());foreign['languages']=['japanese']
            same={**parse_html(E,eh_html()),'title':'Different title'}
            candidates=[]
            for index in range(11):
                meta={**(same if index==10 else foreign),'external_id':str(987654+index),'url':E.replace('987654',str(987654+index))}
                candidates.append({'metadata':meta,'comparison':compare_metadata(baseline,meta)})
            result={'provider':'ehentai','items':candidates,'status':'checked','failures':0}
            linker=AutoLinker(store,lambda:(None,None,{'exhentai':'session_required'}))
            with patch('auto_sources.counterpart_candidates',return_value=result):linker.run_one()
            items=next(s for s in store.automatic_status(work['id'])['result']['sites'] if s['provider']=='ehentai')['items']
            self.assertEqual(len(items),10)
            self.assertTrue(items[0]['comparison']['language_match'])
            self.assertIn('display_title',items[0])
            self.assertNotIn('display_title',items[0]['metadata'])
            store.import_metadata(work['id'],items[0]['metadata'])
            source=next(s for s in store.get_work(work['id'])['sources'] if s['provider']=='ehentai')
            self.assertIn('display_title',source)
            self.assertNotIn('display_title',source['metadata'])
            self.assertEqual(store.get_work(work['id'])['title'],'Original title')
            self.assertEqual(len(store.get_work(work['id'])['sources']),2)


if __name__=='__main__':unittest.main()
