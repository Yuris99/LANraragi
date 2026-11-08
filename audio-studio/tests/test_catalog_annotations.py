import base64,contextlib,json,sys,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from catalog import Catalog
from catalog_annotations import CatalogAnnotations
from tag_visibility import TagVisibility,TagVisibilityConflict
from server import make_server

class AnnotationTests(unittest.TestCase):
    def test_read_only_missing_and_explicit_cast_and_subtitle_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);file=root/'annotations.json';store=CatalogAnnotations(file)
            self.assertEqual(store.read()['editions'],{});self.assertFalse(file.exists())
            edition='a'*32;subtitle='b'*32;source='https://www.dlsite.com/maniax/work/=/product_id/RJ01003374.html'
            actor={'id':'dlsite:1','name':'Fixture actor','source':source}
            data={'schema':1,'editions':{edition:{'voice_actors':[actor],'voice_actors_checked':True}},'subtitles':{subtitle:{'language':'ko','human_verified':False}}}
            file.write_text(json.dumps(data));works=[{'editions':[{'id':edition,'tracks':[{'subtitles':[{'id':subtitle,'language':'und'}]}]}]}];before=file.read_bytes();store.attach(works)
            self.assertEqual(works[0]['editions'][0]['voice_actors'],[actor]);self.assertEqual(works[0]['editions'][0]['tracks'][0]['subtitles'][0]['language'],'und');self.assertEqual(file.read_bytes(),before)
            actor['source']='https://evil.test';file.write_text(json.dumps(data))
            with self.assertRaises(ValueError):store.read()

    def test_manual_work_tags_preserve_old_settings_and_stale_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            store=TagVisibility(Path(directory)/'tags.json');identifier='a'*32
            result=store.save(0,hidden_rplay_tags=['raw'],tag_names={'keep':{'ko':'name'}},work_tags={identifier:['癒し']})
            self.assertEqual(result['work_tags'][identifier],['癒し'])
            result=store.save(1,favorite_tags=['keep']);self.assertEqual(result['work_tags'][identifier],['癒し']);self.assertEqual(result['hidden_rplay_tags'],['raw'])
            before=store.file.read_bytes()
            with self.assertRaises(TagVisibilityConflict):store.save(1,work_tags={identifier:[]})
            with self.assertRaises(ValueError):store.save(2,work_tags={'bad':['x']})
            self.assertEqual(store.file.read_bytes(),before)

    def test_only_explicit_valid_canonical_choices_save_no_original_catalog_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);media=root/'media';media.mkdir();catalog=Catalog(root/'data'/'db');work=catalog.create_work('Fixture');edition=catalog.create_edition(work['id'],'Original','audio',credits={'nas_import':{'provider':'rplay'},'tags':['raw reference']});original=catalog.works()
            server=make_server(catalog,media,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(path,data=None,status=200):
                req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,json.dumps(data).encode() if data is not None else None,{'Content-Type':'application/json'})
                try:response=urllib.request.urlopen(req)
                except urllib.error.HTTPError as error:response=error
                with contextlib.closing(response):self.assertEqual(response.status,status);return json.loads(response.read())
            try:
                vocabulary=request('/api/tag-vocabulary')['tags'];self.assertFalse(server.tag_visibility.file.exists());tag=vocabulary[0]['tag'];endpoint='/api/works/'+work['id']+'/classification-tags'
                request(endpoint,{'revision':0,'tags':['unverified invented tag']},400);self.assertFalse(server.tag_visibility.file.exists())
                saved=request(endpoint,{'revision':0,'tags':[tag]});self.assertEqual(saved['work_tags'][work['id']],[tag]);request(endpoint,{'revision':0,'tags':[]},409)
                saved=request(endpoint,{'revision':1,'tags':[]});self.assertEqual(saved['work_tags'][work['id']],[]);self.assertEqual(catalog.works(),original)
                self.assertEqual(request('/api/export')['works'],original)
            finally:server.shutdown();server.server_close();thread.join()
