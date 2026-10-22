"""Generated documents only. No personal HTML or live external requests."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from metadata import parse_html,parse_hitomi_json,compare_metadata,counterpart_candidates
from store import Store
from backup import copy_database
from server import Studio,make_server

H='https://hitomi.la/galleries/123456.html'
E='https://e-hentai.org/g/987654/abcdef/'


def hitomi_html():
    return '''<h1 id="gallery-brand"><a href="/reader/123456.html">A Garden</a></h1>
    <h2 id="artists"><a href="/artist/fixture-all.html">Fixture</a></h2>
    <td id="language"><a href="/index-korean.html">Korean</a></td>
    <td id="series"><a href="/series/original-all.html">original</a></td>
    <ul id="tags"><li><a href="/tag/color-all.html">color</a></li></ul>
    <section class="related-content"><a href="/tag/unrelated-all.html">unrelated</a></section>
    <script>throw new Error('must never run');</script><img src="https://invalid.example/no-request">'''


def eh_html(title='A Garden',comments=True):
    return '''<script>var gid = 987654; var token = "abcdef";</script>
    <h1 id="gn">[Fixture] A Garden [Korean] [Digital]</h1><h1 id="gj">'''+title+'''</h1>
    <div id="gdd"><table><tr><td>Length:</td><td>6 pages</td></tr></table></div>
    <div id="taglist"><a id="ta_artist:Fixture">Fixture</a><a id="ta_language:korean">korean</a>
    <a id="ta_parody:original">original</a><a id="ta_other:color">color</a></div>'''+('''
    <div id="cdiv"><div class="c1"><a name="c12"></a><div class="c3">Posted on a date by: <a>Example</a></div>
    <div class="c6">A &amp; B<script>private()</script></div></div></div>''' if comments else '')


def hitomi_js():
    return 'var galleryinfo = '+json.dumps({'id':123456,'title':'A Garden','artists':[{'artist':'Fixture'}],
        'language':'korean','parodys':[{'parody':'original'}],'tags':[{'tag':'color'}],
        'files':[{'name':str(n)+'.jpg'} for n in range(6)]})+';'


class MetadataTests(unittest.TestCase):
    def test_html_scoping_languages_and_identity_not_related_cards_or_scripts(self):
        h=parse_html(H,hitomi_html());e=parse_html(E,eh_html())
        self.assertEqual(h['title'],'A Garden')
        self.assertEqual(h['languages'],['korean'])
        self.assertEqual(set(h['tags']),set(e['tags']))
        self.assertIn('series:original',h['raw_tags'])
        self.assertIn('tag:color',h['raw_tags'])
        self.assertNotIn('other:unrelated',h['tags'])
        self.assertEqual(e['pages'],6)
        self.assertEqual(e['comments'][0]['text'],'A & B')
        self.assertNotIn('private()',json.dumps(e))
        with self.assertRaises(ValueError):parse_html(H.replace('123456','111111'),hitomi_html())
        with self.assertRaises(ValueError):parse_html(E.replace('abcdef','other'),eh_html())
        with self.assertRaises(ValueError):parse_html(E,eh_html().replace('987654','1'))

    def test_document_limits_and_challenge_are_not_imported(self):
        for html in ['x'*(2*1024*1024+1),'<div>'*130,'<h1>Human verification</h1>']:
            with self.subTest(size=len(html)),self.assertRaises(ValueError):parse_html(H,html)
        with self.assertRaises(ValueError):parse_hitomi_json(H,'var galleryinfo = {"id":123456}; alert(1)')
        with self.assertRaises(ValueError):parse_hitomi_json(H,hitomi_js().replace('123456','9'))

    def test_cross_provider_ids_differ_and_strict_edition_evidence(self):
        h=parse_hitomi_json(H,hitomi_js());e=parse_html(E,eh_html())
        self.assertNotEqual(h['external_id'],e['external_id'])
        self.assertTrue(compare_metadata(h,e)['automatic_eligible'])
        self.assertTrue(compare_metadata(h,{**e,'title':'[Fixture] A Garden [Korean] [Digital]'})['automatic_eligible'])
        for change in [{'pages':None},{'pages':7},{'languages':['japanese']},{'artists':['Other']},{'title':'Another Garden'},{'tags':['other:different']},{'provider':'hitomi'}]:
            self.assertFalse(compare_metadata(h,{**e,**change})['automatic_eligible'],change)

    def test_counterpart_search_queries_other_site_not_same_number(self):
        calls=[]
        def fetch(url):
            calls.append(url)
            if 'f_search=' in url:return '<a href="'+E+'">result</a><a href="'+E+'">duplicate</a>'
            if url==E:return eh_html()
            raise AssertionError(url)
        value=counterpart_candidates(parse_hitomi_json(H,hitomi_js()),fetch)
        self.assertEqual(len(value['items']),1)
        self.assertEqual(value['items'][0]['metadata']['external_id'],'987654')
        self.assertTrue(value['items'][0]['comparison']['automatic_eligible'])
        self.assertNotIn('123456',calls[0])
        calls.clear()
        def hfetch(url):
            calls.append(url);return hitomi_js().replace('123456',url.rsplit('/',1)[-1].split('.')[0])
        value=counterpart_candidates(parse_html(E,eh_html()),hfetch,lambda artist:[str(n) for n in range(123456,123476)])
        self.assertEqual(len(calls),8)
        self.assertTrue(value['bounded'])

    def test_access_failure_and_incomplete_response_never_look_like_absence(self):
        def denied(url):raise urllib.error.HTTPError(url,403,'denied',{},None)
        self.assertEqual(counterpart_candidates(parse_hitomi_json(H,hitomi_js()),denied)['status'],'access_required')
        value=counterpart_candidates(parse_html(E,eh_html()),denied,lambda artist:['123456'])
        self.assertEqual(value['status'],'access_required')
        self.assertEqual(value['failures'],1)

    def test_rate_limit_stops_further_requests_and_format_failure_is_partial(self):
        calls=[]
        def limited(url):
            calls.append(url);raise urllib.error.HTTPError(url,429,'limited',{},None)
        value=counterpart_candidates(parse_html(E,eh_html()),limited,lambda artist:['123456','123457'])
        self.assertEqual(value['status'],'access_required')
        self.assertEqual(len(calls),1)
        value=counterpart_candidates(parse_html(E,eh_html()),lambda url:'not metadata',lambda artist:['123456'])
        self.assertEqual(value['status'],'partial')

    def test_store_originals_alias_filter_hidden_internal_tags_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'catalog.db');work=store.create_work('My title','My artist',tags=['date_added:123','timestamp:2','source:private','series:original'])
            store.edit_user_tags([work['id']],['keep'])
            store.import_metadata(work['id'],parse_html(E,eh_html()))
            store.import_metadata(work['id'],parse_html(E,eh_html(comments=False)))
            value=store.get_work(work['id'])
            self.assertEqual((value['title'],value['artist']),('My title','My artist'))
            self.assertEqual(value['sources'][0]['comments'][0]['text'],'A & B')
            self.assertEqual(value['sources'][0]['metadata']['title'],'A Garden')
            self.assertIn('date_added:123',value['tags'])
            self.assertNotIn('date_added:123',value['all_tags'])
            self.assertEqual(store.library_tags('parody:original'),[{'tag':'parody:original','count':1}])
            self.assertFalse(store.library_tags('date_added'))
            self.assertEqual(store.list_works(all_tag='series:original')['total'],1)
            self.assertEqual(store.list_works(all_tag='parody:original')['total'],1)
            self.assertEqual(store.library_tags('series:original'),[{'tag':'parody:original','count':1}])
            self.assertEqual(store.list_works(query='series:original')['total'],1)
            other=store.create_work('Other')
            with self.assertRaises(ValueError):store.import_metadata(other['id'],parse_html(E,eh_html()))
            copy_database(store.path,Path(directory)/'backup.db')
            self.assertEqual(Store(Path(directory)/'backup.db').get_work(work['id'])['sources'][0]['metadata']['title'],'A Garden')


class MetadataHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.env=patch.dict('os.environ',{'STUDIO_PASSWORD':'generated-metadata-test'});self.env.start();self.addCleanup(self.env.stop)
        self.store=Store(Path(self.temp.name)/'catalog.db');self.work=self.store.create_work('Local title')
        self.server=make_server('127.0.0.1',0,Studio(self.store,None))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def post(self,path,data,auth=True):
        import base64
        headers={'Content-Type':'application/json'}
        if auth:headers['Authorization']='Basic '+base64.b64encode(b'admin:generated-metadata-test').decode()
        req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+path,data=json.dumps(data).encode(),headers=headers)
        with urllib.request.urlopen(req) as response:return json.load(response)

    def test_authenticated_preview_then_import_no_network_and_title_retained(self):
        value=self.post('/api/metadata/preview',{'url':H,'html':hitomi_html()})
        self.assertEqual(value['provider'],'hitomi')
        value=self.post('/api/works/'+self.work['id']+'/metadata',{'url':H,'html':hitomi_html()})
        self.assertEqual(value['title'],'Local title')
        self.assertEqual(len(value['sources']),1)
        with self.assertRaises(urllib.error.HTTPError) as error:self.post('/api/metadata/preview',{'url':H,'html':hitomi_html()},False)
        self.assertEqual(error.exception.code,401)

    def test_automatic_counterpart_connects_only_unique_complete_candidate(self):
        self.store.import_metadata(self.work['id'],parse_hitomi_json(H,hitomi_js()))
        source=self.store.get_work(self.work['id'])['sources'][0]
        candidate=parse_html(E,eh_html())
        item={'metadata':candidate,'comparison':compare_metadata(source['metadata'],candidate)}
        with patch('server.counterpart_candidates',return_value={'status':'checked','items':[item],'message':'generated'}):
            value=self.post('/api/works/'+self.work['id']+'/counterparts',{'source_id':source['id'],'automatic':True})
        self.assertTrue(value['connected'])
        self.assertEqual(len(self.store.get_work(self.work['id'])['sources']),2)
        self.assertEqual(self.store.get_work(self.work['id'])['title'],'Local title')

    def test_ambiguous_incomplete_and_already_owned_candidates_do_not_auto_connect(self):
        for mode in ('ambiguous','partial','owned'):
            with self.subTest(mode=mode):
                work=self.store.create_work('Another generated work')
                source=self.store.import_metadata(work['id'],parse_hitomi_json(H.replace('123456','123457'),hitomi_js().replace('123456','123457')))['sources'][0]
                e=parse_html(E,eh_html());item={'metadata':e,'comparison':compare_metadata(source['metadata'],e)}
                if mode=='owned':self.store.import_metadata(self.work['id'],e)
                response={'status':'partial' if mode=='partial' else 'checked','items':[item,item] if mode=='ambiguous' else [item],'message':'generated'}
                with patch('server.counterpart_candidates',return_value=response):
                    value=self.post('/api/works/'+work['id']+'/counterparts',{'source_id':source['id'],'automatic':True})
                self.assertFalse(value['connected'])
                self.assertEqual(len(self.store.get_work(work['id'])['sources']),1)
                # Remove only generated source between independent cases.
                with self.store.db() as db:db.execute('DELETE FROM sources WHERE work_id=?',(work['id'],))
