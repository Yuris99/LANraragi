import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest.mock import Mock,patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from source_finder import baseline,first_page_hash,candidates,preview_url,preview_image
from site_sessions import source_document
from test_metadata import E,eh_html


class PageLRR:
    def __init__(self):self.raw=b'\x89PNG\r\n\x1a\n'+b'generated-first-page';self.calls=[]
    def json(self,path):return {'pages':['/api/archives/'+'a'*40+'/page?p=1']}
    def open(self,path):
        self.calls.append(path);response=io.BytesIO(self.raw);response.status=200;return response


class SourceFinderTests(unittest.TestCase):
    def setUp(self):
        self.work={'id':'b'*32,'lrr_id':'a'*40,'title':'Local title','artist':'','pages':6,'sources':[],
                   'organization':{'title':'Local title','artist':''}}
        self.record={'evidence':[{'metadata':{'title':'A Garden','artists':['Fixture'],'languages':['korean'],'tags':['other:color'],'pages':6}}]}

    def test_original_metadata_is_search_baseline_without_overwriting_title(self):
        base=baseline(self.work,self.record)
        self.assertEqual((base['title'],base['artists']),('A Garden',['Fixture']))
        self.assertEqual(self.work['title'],'Local title')

    def test_image_candidate_can_seed_hitomi_without_linking_or_losing_local_edition(self):
        from test_metadata import hitomi_js
        work={**self.work,'title':'Opaque local filename'}
        record={'evidence':[{'metadata':{'title':'Opaque local filename','languages':['english']}}]}
        calls=[]
        def fetch(url):
            calls.append(url)
            return eh_html() if url==E else hitomi_js()
        result=candidates(work,record,'hitomi',fetch,lambda artist,offset=None:{'ids':['123456'],'complete':True},from_url=E)
        self.assertEqual(result['seed_url'],E)
        self.assertEqual(result['baseline']['title'],'A Garden')
        self.assertEqual(result['baseline']['languages'],['english'])
        self.assertFalse(result['items'][0]['comparison']['language_match'])
        self.assertEqual(work['sources'],[])
        self.assertEqual(calls[0],E)
        for method,url in [('image',E),('hitomi','https://private.invalid/test'),('hitomi','https://hitomi.la/galleries/123.html')]:
            with self.assertRaises(ValueError):candidates(work,record,method,fetch,from_url=url)

    def test_seed_auth_failure_stops_before_hitomi_search(self):
        fetch=Mock(side_effect=urllib.error.HTTPError(E,403,'denied',{},None));index=Mock()
        result=candidates(self.work,self.record,'hitomi',fetch,index,from_url=E)
        self.assertEqual(result['status'],'access_required');self.assertEqual(result['items'],[])
        fetch.assert_called_once_with(E);index.assert_not_called()

    def test_original_page_hash_and_path_validation(self):
        lrr=PageLRR();digest,image=first_page_hash(lrr,self.work)
        self.assertEqual(digest,hashlib.sha1(lrr.raw).hexdigest())
        self.assertTrue(image.startswith('/api/media/'))
        with self.assertRaises(ValueError):first_page_hash(lrr,self.work,True)
        lrr.json=lambda path:{'pages':['https://private.invalid/no']}
        with self.assertRaises(ValueError):first_page_hash(lrr,self.work)

    def test_image_results_are_real_gallery_candidates_with_more_and_no_attachment(self):
        seen=[]
        def fetch(url):
            seen.append(url)
            if 'f_shash=' in url:return ''.join('<a href="https://e-hentai.org/g/'+str(i)+'/abcdef/">candidate</a>' for i in range(987654,987660))
            gid=url.split('/')[4]
            return eh_html().replace('987654',gid)
        result=candidates(self.work,self.record,'image',fetch,lrr=PageLRR())
        self.assertEqual(len(result['items']),5);self.assertEqual(result['next_cursor'],{'page':0,'offset':5})
        self.assertEqual(result['baseline']['pages'],6)
        self.assertEqual(self.work['sources'],[])
        self.assertIn('fs_similar=1&fs_covers=1',seen[0])
        more=candidates(self.work,self.record,'image',fetch,lrr=PageLRR(),cursor=result['next_cursor'])
        self.assertEqual(len(more['items']),1);self.assertNotIn('next_cursor',more)

    def test_access_denial_and_challenge_never_become_no_results_or_another_site(self):
        for body in (None,'<title>Just a moment...</title>'):
            fetch=Mock(side_effect=urllib.error.HTTPError(E,403,'denied',{},None)) if body is None else Mock(return_value=body)
            result=candidates(self.work,self.record,'image',fetch,lrr=PageLRR())
            self.assertEqual(result['status'],'access_required');self.assertEqual(result['items'],[])
            fetch.assert_called_once()

    def test_search_uses_explicit_original_host_when_available(self):
        record={'evidence':[{'provider':'exhentai','external_id':'987654','url':E.replace('e-hentai.org','exhentai.org'),
                            'origin':{'url_basis':'original-url'}}]}
        fetch=Mock(return_value='')
        candidates(self.work,record,'image',fetch,lrr=PageLRR())
        self.assertTrue(fetch.call_args.args[0].startswith('https://exhentai.org/?f_shash='))

    def test_unknown_source_uses_available_account_and_linked_host_is_preserved(self):
        fetch=Mock(return_value='')
        candidates(self.work,{'evidence':[]},'image',fetch,lrr=PageLRR(),default_provider='exhentai')
        self.assertTrue(fetch.call_args.args[0].startswith('https://exhentai.org/?f_shash='))
        linked={**self.work,'sources':[{'provider':'ehentai','metadata':{}}]}
        candidates(linked,{'evidence':[]},'image',fetch,lrr=PageLRR(),default_provider='exhentai')
        self.assertTrue(fetch.call_args.args[0].startswith('https://e-hentai.org/?f_shash='))

    def test_thumbnail_proxy_accepts_only_fixed_public_image_host(self):
        good='https://ehgt.org/aa/bb/generated.jpg'
        self.assertEqual(preview_url(good),good)
        for url in ('http://ehgt.org/x.jpg','https://ehgt.org.evil/x.jpg','https://ehgt.org/x.svg','https://ehgt.org/x.jpg?secret=1','https://user@ehgt.org/x.jpg','https://ehgt.org/../x.jpg'):
            with self.subTest(url=url),self.assertRaises(ValueError):preview_url(url)
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=io.BytesIO(b'x'*(768*1024+1))
            with self.assertRaises(ValueError):preview_image(good)

    def test_login_transport_allows_only_fixed_hash_search_parameters(self):
        url='https://e-hentai.org/?f_shash='+'a'*40+'&fs_similar=1&fs_covers=1'
        vault=Mock(last_requests={});vault.read.side_effect=FileNotFoundError
        response=io.BytesIO(b'<html>generated search results</html>');response.status=200
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=response
            self.assertEqual(source_document(vault,url)['status'],'ok')
        for bad in (url.replace('a'*40,'short'),url+'&redirect=https://private.invalid',url+'&f_shash='+'b'*40,url.replace('fs_covers=1','fs_covers=0'),url+'&page=1001'):
            with self.subTest(url=bad),self.assertRaises(ValueError):source_document(vault,bad)


if __name__=='__main__':unittest.main()
