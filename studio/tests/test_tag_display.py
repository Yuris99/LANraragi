"""Bilingual searches keep exact namespaces and never rewrite the catalog."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import Store
from tag_display import LABELS, tag_words, dictionary


class TagDisplayTests(unittest.TestCase):
    def test_internal_user_tags_hidden_from_management_but_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'studio.db');work=store.create_work('Generated')
            tags=['date_added:123','timestamp','SOURCE:generated','소장']
            store.edit_user_tags([work['id']],tags)
            self.assertEqual(store.tag_catalog(),[{'tag':'소장','count':1}])
            self.assertEqual(store.tag_catalog('date_added'),[])
            self.assertEqual(set(store.get_work(work['id'])['user_tags']),set(tags))

    def test_dictionary_is_local_namespace_safe_and_has_explanations(self):
        self.assertGreater(len(LABELS),7500)
        self.assertIn('안경',tag_words('female:glasses'))
        self.assertIn('안경',tag_words('male:glasses'))
        self.assertNotIn('안경',tag_words('artist:glasses'))
        self.assertIn('나루토',tag_words('parody:naruto'))
        self.assertNotIn('나루토',tag_words('character:naruto'))
        self.assertIn('안경',dictionary()['descriptions']['glasses'])
        self.assertEqual(tag_words('constructor'),'constructor ')

    def test_search_matches_both_languages_before_limit_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'studio.db')
            tags=['female:glasses','male:glasses','language:korean','series:naruto','artist:glasses','100% literal']
            work=store.create_work('Generated',tags=tags)
            store.upsert_source(work['id'],{'url':'https://e-hentai.org/g/123/abc/','tags':['female:glasses']})
            store.edit_user_tags([work['id']],['나만의 태그'])
            before=json.dumps(store.get_work(work['id']),sort_keys=True)
            self.assertEqual([t['tag'] for t in store.library_tags('안경')],['female:glasses','male:glasses'])
            self.assertEqual(store.library_tags('안경','male'),[{'tag':'male:glasses','count':1}])
            self.assertEqual(store.library_tags('male:안경'),[{'tag':'male:glasses','count':1}])
            self.assertEqual(store.library_tags('female:안경','male'),[])
            self.assertEqual(store.library_tags('한국어'),[{'tag':'language:korean','count':1}])
            self.assertEqual(store.library_tags('나루토'),[{'tag':'parody:naruto','count':1}])
            self.assertEqual(store.library_tags('%'),[{'tag':'100% literal','count':1}])
            self.assertEqual(store.library_tags('나만','user'),[{'tag':'나만의 태그','count':1}])
            self.assertEqual(json.dumps(store.get_work(work['id']),sort_keys=True),before)
            # A rare matching namespace must survive 100 more popular unrelated tags.
            store.create_work('Generated many',tags=['female:example'+str(n) for n in range(130)])
            self.assertEqual(store.library_tags('','male'),[{'tag':'male:glasses','count':1}])
            with self.assertRaises(ValueError):store.library_tags('', 'invalid')


if __name__=='__main__':unittest.main()
