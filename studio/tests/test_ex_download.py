"""Generated sessions and pinned extractor only; requests never reach a network."""
import base64
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studio'))
from gallery_engine import engine_argv,require_ex_session,strict_ex_download,package_images
from worker import engine_failure
import gallery_engine

wheel=os.environ.get('STUDIO_GALLERY_DL_WHEEL')
if not wheel:
    wheel=next((ROOT/'work/ex-download/vendor').glob('gallery_dl-1.32.16-*.whl'),None)
if wheel:sys.path.insert(0,str(wheel))
try:
    import gallery_dl
    import requests
except ImportError:
    gallery_dl=None

URL='https://exhentai.org/g/123/0123456789/'
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jXioAAAAASUVORK5CYII=')


def jar(path,domain='exhentai.org',expires='',names=('ipb_member_id','ipb_pass_hash'),scope='/'):
    path.write_text('# Netscape HTTP Cookie File\n'+''.join(f'{domain}\t{"TRUE" if domain.startswith(".") else "FALSE"}\t{scope}\tTRUE\t{expires}\t{name}\tgenerated-{name}\n' for name in names),encoding='utf-8')
    path.chmod(0o600);return path


class SessionTests(unittest.TestCase):
    def test_actual_target_domain_path_expiry_and_both_cookies_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cookies.txt'
            for domain in ('exhentai.org','.exhentai.org'):
                jar(path,domain);require_ex_session(path,URL)
                argv=engine_argv(URL,directory,path)
                self.assertIn('--strict-exhentai',argv);self.assertIn(URL,argv)
                self.assertNotIn('gallery_dl',argv)
            for args in [dict(domain='.e-hentai.org'),dict(expires=1),dict(names=('ipb_member_id',)),dict(scope='/forums')]:
                jar(path,**args)
                with self.assertRaises(ValueError):require_ex_session(path,URL)
            with self.assertRaises(ValueError):engine_argv(URL,directory)

    def test_worker_reports_only_validated_categories_never_raw_log(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'studio-engine-result.json'
            path.write_text(json.dumps({'engine':'gallery-dl','adapter':'same-source-1','category':'access_required','exit_code':16,'http_status':403,'cookie':'generated-do-not-display'}))
            message,safe=engine_failure(directory,16)
            self.assertIn('HTTP 403',message);self.assertNotIn('cookie',safe)
            self.assertNotIn('generated-do-not-display',message+json.dumps(safe))
            path.write_text('{not json')
            self.assertEqual(engine_failure(directory,16),('엔진 종료 코드 16',None))

    def test_verification_does_not_publish_a_cbz(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cookies=jar(root/'cookies.txt')
            @contextmanager
            def saved(url):yield cookies
            def child(argv,**kwargs):
                self.assertIn('--verify',argv);(root/'0001.png').write_bytes(PNG);return SimpleNamespace(returncode=0)
            with patch('gallery_engine.cookie_snapshot',saved),patch('gallery_engine.subprocess.run',child),patch('gallery_engine.package_images') as package,patch('sys.argv',['gallery_engine.py','--url',URL,'--output',str(root),'--verify']):
                gallery_engine.main();package.assert_not_called()
            self.assertFalse(list(root.glob('*.cbz')))


@unittest.skipUnless(gallery_dl,'Install pinned requirements-worker.txt or provide STUDIO_GALLERY_DL_WHEEL')
class PinnedExtractorTests(unittest.TestCase):
    def test_real_extractor_host_only_cookies_download_and_cbz(self):
        calls=[]
        gallery='''<h1 id="gn">Generated gallery</h1><h1 id="gj">Generated gallery</h1>
        <div id="gdc"><div class="cs ct2">Manga</div></div><div id="gdn">Generated</div>
        <table><tr><td>Posted:</td><td class="gdt2">2020-01-01 00:00:00</td></tr>
        <tr><td>Language:</td><td class="gdt2">English </td></tr>
        <tr><td>File Size:</td><td class="gdt2">1 KB</td></tr>
        <tr><td>Length:</td><td class="gdt2">1 pages</td></tr></table>
        <span id="favcount">0 times</span><span>Average: 4.00<</span>
        <a href="https://exhentai.org/s/aaaaaaaaaa/123-1">Page</a>'''
        def request(session,method,url,**kwargs):
            calls.append(url)
            if url==URL:body=gallery.encode()
            elif url=='https://exhentai.org/s/aaaaaaaaaa/123-1':body=b'<img id="img" src="https://ehgt.org/generated.png">'
            elif url=='https://ehgt.org/generated.png':body=PNG
            else:raise AssertionError('Unexpected generated request: '+url)
            response=requests.Response();response.url=url;response.status_code=200;response._content=body;response.raw=io.BytesIO(body)
            response.raw.chunked=False
            response.headers={'Cache-Control':'private','Content-Length':str(len(body)),'Content-Type':'image/png' if body==PNG else 'text/html; charset=utf-8'}
            response.encoding='utf-8';return response
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cookies=jar(root/'cookies.txt')
            with patch('requests.Session.request',request),patch('gallery_dl.extractor.common.Extractor.sleep'):
                self.assertEqual(strict_ex_download(URL,root,cookies),0)
            self.assertTrue((root/'0001.png').is_file())
            self.assertEqual(package_images(root,{'provider':'exhentai','external_id':'123','url':URL}),1)
            self.assertTrue((root/'exhentai-123.cbz').is_file())
            self.assertFalse(any('e-hentai.org' in call for call in calls))

    def test_missing_cookies_no_requests_and_redirect_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cookies=jar(root/'cookies.txt',domain='.e-hentai.org')
            with patch('requests.Session.request') as request:
                with self.assertRaises(ValueError):strict_ex_download(URL,root,cookies)
                request.assert_not_called()
            cookies=jar(cookies)
            def redirect(session,method,url,**kwargs):
                self.assertEqual(url,URL);self.assertFalse(kwargs['allow_redirects'])
                response=requests.Response();response.url=url;response.status_code=302;response._content=b'login'
                response.headers={'Location':'https://e-hentai.org/g/123/0123456789/','Cache-Control':'private'}
                return response
            with patch('requests.Session.request',redirect),patch('gallery_dl.extractor.common.Extractor.sleep'):
                self.assertEqual(strict_ex_download(URL,root,cookies),16)
            self.assertEqual(json.loads((root/'studio-engine-result.json').read_text())['category'],'login_redirect')
            self.assertFalse(list(root.glob('*.cbz')))


if __name__=='__main__':unittest.main()
