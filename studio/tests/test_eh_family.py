"""One EH/EX account and display family; original host identity remains intact."""
import io
import json
import os
import shutil
import subprocess
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from site_sessions import CookieVault,source_document
from login_service import LoginBrowser,DesktopBrowser
from store import Store
from auto_sources import AutoLinker
from test_metadata import E,H,eh_html,hitomi_js
from test_auto_sources import generated_fetch,generated_index
from metadata import parse_html,compare_metadata,counterpart_candidates


def account(domain,identity='generated-account'):
    return [dict(domain=domain,path='/',name=name,value=identity if name=='ipb_member_id' else 'generated-'+domain,
                 secure=False,httpOnly=True,expires=-1) for name in ('ipb_member_id','ipb_pass_hash')]


class EHAccountTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.vault=CookieVault(Path(self.temp.name)/'sessions')

    def legacy(self,provider,cookies):
        path=self.vault.root/(provider+'.cookies')
        path.write_text('# Netscape HTTP Cookie File\n'+''.join(c['domain']+'\tTRUE\t/\tFALSE\t\t'+c['name']+'\t'+c['value']+'\n' for c in cookies))
        path.chmod(0o600);return path

    def test_frozen_login_recipe_needs_only_its_three_existing_modules(self):
        root=Path(self.temp.name)/'frozen-login';root.mkdir()
        for name in ('login_service.py','site_sessions.py','init_login.py'):
            shutil.copy(Path(__file__).resolve().parents[1]/name,root/name)
        result=subprocess.run([sys.executable,'-I','-B','-c','import sys;sys.path.insert(0,sys.argv[1]);import login_service,site_sessions',str(root)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_one_save_is_shared_without_rewriting_cookie_domains(self):
        cookies=account('.e-hentai.org')+account('.exhentai.org')
        self.vault.save('ehentai',cookies)
        self.assertEqual(self.vault.path('ehentai'),self.vault.path('exhentai'))
        self.assertEqual(len(self.vault.read('exhentai')),4)
        self.assertEqual({c.domain for c in self.vault.read('ehentai')},{'.e-hentai.org','.exhentai.org'})
        self.assertEqual(self.vault.path('ehentai').stat().st_mode&0o777,0o600)
        for provider in ('ehentai','exhentai'):
            status=self.vault.status(provider)
            self.assertEqual(status['session_family'],'ehentai')
            self.assertTrue(status['target_session_available'])
        self.assertNotIn('generated-',json.dumps(self.vault.status('ehentai')))

    def test_legacy_files_are_read_and_preserved_until_explicit_shared_save(self):
        e=self.legacy('ehentai',account('.e-hentai.org'));x=self.legacy('exhentai',account('.exhentai.org'))
        original={p:p.read_bytes() for p in (e,x)}
        self.assertEqual(len(self.vault.read('ehentai')),4)
        self.assertEqual(original,{p:p.read_bytes() for p in (e,x)})
        self.vault.save('ehentai',account('.e-hentai.org'))
        self.assertEqual(x.read_bytes(),original[x])
        self.assertEqual(len(self.vault.read('exhentai')),2,'An old EX backup must not revive after an authoritative save')
        self.assertFalse(self.vault.status('exhentai')['target_session_available'])

    def test_legacy_different_accounts_require_explicit_choice(self):
        self.legacy('ehentai',account('.e-hentai.org','generated-one'))
        x=self.legacy('exhentai',account('.exhentai.org','generated-two'));before=x.read_bytes()
        with self.assertRaises(ValueError):self.vault.read('ehentai')
        self.vault.save('ehentai',account('.e-hentai.org','generated-one'))
        self.assertEqual(x.read_bytes(),before)
        self.assertEqual(len(self.vault.read('ehentai')),2)

    def test_different_accounts_in_one_export_do_not_replace_current_session(self):
        self.vault.save('ehentai',account('.e-hentai.org'));before=self.vault.path('ehentai').read_bytes()
        with self.assertRaises(ValueError):self.vault.save('exhentai',account('.e-hentai.org','one')+account('.exhentai.org','two'))
        self.assertEqual(before,self.vault.path('ehentai').read_bytes())

    def test_overlapping_legacy_domains_do_not_hide_different_accounts(self):
        self.legacy('ehentai',account('.e-hentai.org','generated-one'))
        self.legacy('exhentai',account('.e-hentai.org','generated-two')+account('.exhentai.org','generated-two'))
        with self.assertRaises(ValueError):self.vault.read('ehentai')

    def test_e_only_session_never_becomes_an_anonymous_ex_request(self):
        self.vault.save('ehentai',account('.e-hentai.org'))
        self.assertEqual(self.vault.status('exhentai')['state'],'saved_unverified')
        self.assertFalse(self.vault.status('exhentai')['target_session_available'])
        with patch('urllib.request.build_opener') as opener:
            result=source_document(self.vault,'https://exhentai.org/g/1/abc/')
        self.assertEqual(result['status'],'session_required');opener.assert_not_called()
        self.assertEqual(self.vault.last_requests['exhentai']['mode'],'no_matching_cookies')

    def test_shared_import_accepts_a_real_ex_domain_export(self):
        self.vault.import_file('ehentai',json.dumps(account('.exhentai.org')))
        self.assertTrue(self.vault.status('exhentai')['target_session_available'])
        self.assertFalse(self.vault.status('ehentai')['target_session_available'])
        with patch('urllib.request.build_opener') as opener:
            self.assertEqual(source_document(self.vault,E)['status'],'session_required')
        opener.assert_not_called()

    def test_forget_removes_both_legacy_names_without_resurrection(self):
        self.legacy('ehentai',account('.e-hentai.org'));self.legacy('exhentai',account('.exhentai.org'))
        self.vault.forget('exhentai')
        self.assertEqual(self.vault.status('ehentai')['state'],'not_saved')
        self.assertEqual(self.vault.status('exhentai')['state'],'not_saved')

    def test_browser_restoration_uses_account_cookies_and_original_domains_only(self):
        self.vault.save('ehentai',account('.e-hentai.org')+account('.exhentai.org')+
            [dict(domain='.e-hentai.org',name='cf_clearance',value='generated-excluded')])
        b=DesktopBrowser(self.vault,bridge_token='generated-token-'+'a'*48);b.provider='ehentai';b.session='generated-window'
        folder=Path(self.temp.name)/'extension';folder.mkdir(mode=0o700);b.extension(folder)
        config=json.loads((folder/'save.js').read_text().splitlines()[0].removeprefix('const config=').removesuffix(';'))
        self.assertEqual(set(config['domains']),{'e-hentai.org','exhentai.org'})
        self.assertEqual({c['domain'] for c in config['restored']},{'.e-hentai.org','.exhentai.org'})
        self.assertEqual(len(config['restored']),4)

    def test_fixed_visit_can_switch_within_family_but_never_to_an_unrelated_host(self):
        for kind in (LoginBrowser,DesktopBrowser):
            b=kind(self.vault);b.provider='ehentai';b.session='generated-window';b.deadline=time.monotonic()+30
            b.page=SimpleNamespace(goto=Mock(return_value=None));b.frame=Mock(return_value={});b.run=Mock(return_value=b'')
            b.call({'op':'visit','session':b.session,'target':'exhentai'})
            with self.assertRaises(ValueError):b.call({'op':'visit','session':b.session,'target':'nhentai'})
            with self.assertRaises(ValueError):b.call({'op':'visit','session':b.session,'target':'https://other.invalid'})

    def test_download_snapshot_contains_only_original_host_cookies(self):
        from gallery_engine import cookie_snapshot
        self.vault.save('ehentai',account('.e-hentai.org')+account('.exhentai.org'))
        with patch.dict(os.environ,{'STUDIO_SESSION_DIR':str(self.vault.root)}):
            with cookie_snapshot(E) as path:
                text=Path(path).read_text()
                self.assertIn('.e-hentai.org',text)
                self.assertNotIn('.exhentai.org',text)


class EHSourceFamilyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'catalog.db')

    def test_family_filter_includes_both_origins_without_merging_work_records(self):
        e=self.store.create_work('Generated E');x=self.store.create_work('Generated X')
        self.store.upsert_source(e['id'],{'url':E})
        self.store.upsert_source(x['id'],{'url':'https://exhentai.org/g/2/xyz/'})
        for provider in ('ehentai','exhentai'):
            self.assertEqual(self.store.list_works(provider=provider)['total'],2)
        self.assertEqual(self.store.resolve_short_id('E987654')['id'],e['id'])
        self.assertEqual(self.store.resolve_short_id('X2')['id'],x['id'])

    def test_original_e_and_x_routes_remain_bound_to_their_work(self):
        e=self.store.create_work('Generated');other=self.store.create_work('Other')
        self.store.upsert_source(e['id'],{'url':E});alias=E.replace('e-hentai.org','exhentai.org')
        self.store.upsert_source(e['id'],{'url':alias})
        self.assertEqual({s['provider'] for s in self.store.get_work(e['id'])['sources']},{'ehentai','exhentai'})
        self.assertEqual(self.store.resolve_short_id('E987654')['id'],e['id'])
        self.assertEqual(self.store.resolve_short_id('X987654')['id'],e['id'])
        with self.assertRaises(ValueError):self.store.upsert_source(other['id'],{'url':alias})
        self.assertEqual(self.store.list_works(provider='ehentai')['total'],1)
        self.assertEqual(self.store.list_works()['total'],2,'The empty other work remains preserved')

    def test_automatic_linking_does_not_search_a_second_eh_host(self):
        work=self.store.create_work('Generated')
        self.store.upsert_source(work['id'],{'url':H})
        calls=[]
        def fetch(url):calls.append(url);return generated_fetch(url)
        linker=AutoLinker(self.store,lambda:(fetch,generated_index,{'exhentai':'session_required'}))
        self.assertTrue(linker.run_one())
        result=self.store.automatic_status(work['id'])
        self.assertEqual(result['state'],'complete')
        self.assertEqual({s['provider'] for s in result['result']['sites']},{'ehentai','hitomi'})
        self.assertFalse(any('exhentai.org' in url for url in calls))

    def test_eh_and_ex_are_not_treated_as_different_counterpart_families(self):
        e=parse_html(E,eh_html());x=parse_html(E.replace('e-hentai.org','exhentai.org'),eh_html())
        self.assertFalse(compare_metadata(e,x)['automatic_eligible'])
        fetch=Mock()
        with self.assertRaises(ValueError):counterpart_candidates(e,fetch,target='exhentai')
        fetch.assert_not_called()

    def test_same_family_alias_requires_verified_metadata_and_preserves_original_url(self):
        work=self.store.create_work('Generated')
        self.store.import_metadata(work['id'],parse_html(E,eh_html()))
        linker=AutoLinker(self.store,lambda:(generated_fetch,generated_index,{}))
        self.assertTrue(linker.run_one())
        sources=self.store.get_work(work['id'])['sources']
        self.assertIn(E,{s['url'] for s in sources})
        self.assertIn(E.replace('e-hentai.org','exhentai.org'),{s['url'] for s in sources})
        self.assertEqual(self.store.list_works()['total'],1)


if __name__=='__main__':unittest.main()
