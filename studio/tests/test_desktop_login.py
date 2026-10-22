"""Desktop boundaries; generated tokens/cookies only."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from login_service import DesktopBrowser,BrowserActor
from site_sessions import CookieVault


class DesktopLoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.vault=CookieVault(Path(self.tmp.name)/'sessions')
        self.browser=DesktopBrowser(self.vault,bridge_token='generated-token-'+'a'*48)

    def test_challenge_clearance_never_reaches_worker_cookie_file(self):
        cookies=[dict(domain='.e-hentai.org',path='/',name=n,value='generated',secure=True,expires=-1)
                 for n in ('ipb_member_id','ipb_pass_hash','cf_clearance','__cf_bm','cf_chl_test')]
        self.vault.save('ehentai',cookies)
        self.assertEqual({c.name for c in self.vault.read('ehentai')},{'ipb_member_id','ipb_pass_hash'})
        self.assertNotIn('cf_clearance',self.vault.path('ehentai').read_text())
        with self.vault.path('ehentai').open('a') as stream:
            stream.write('.e-hentai.org\tTRUE\t/\tTRUE\t\tcf_clearance\tgenerated-legacy\n')
        self.assertEqual({c.name for c in self.vault.read('ehentai')},{'ipb_member_id','ipb_pass_hash'})

    def test_production_factory_never_silently_falls_back_to_automation(self):
        actor=BrowserActor(self.vault)
        try:self.assertIsInstance(actor.browser,DesktopBrowser)
        finally:actor.close()

    def test_desktop_export_requires_explicit_recent_save_and_current_window(self):
        b=self.browser;b.provider='ehentai';b.session='generated-window';b.deadline=time.monotonic()+30
        data={'op':'desktop-session','session':b.session,'cookies':[dict(domain='.e-hentai.org',path='/',name='ipb_member_id',value='generated',secure=True)]}
        with self.assertRaises(ValueError):b.call(data)
        self.assertFalse(self.vault.path('ehentai').exists())
        b.saving_until=time.monotonic()+15
        with self.assertRaises(ValueError):b.call({**data,'session':'another-window'})
        self.assertEqual(b.call(data)['state'],'saved_unverified')
        self.assertTrue(b.saved)
        with self.assertRaises(ValueError):b.call(data)

    def test_expired_save_and_unrelated_cookies_never_replace_saved_session(self):
        self.vault.save('ehentai',[dict(domain='.e-hentai.org',name='ipb_member_id',value='keep')])
        before=self.vault.path('ehentai').read_bytes();b=self.browser
        b.provider='ehentai';b.session='generated-window';b.deadline=time.monotonic()+30;b.saving_until=time.monotonic()-1
        data={'op':'desktop-session','session':b.session,'cookies':[dict(domain='.evil.example',name='x',value='bad')]}
        with self.assertRaises(ValueError):b.call(data)
        b.saving_until=time.monotonic()+15
        with self.assertRaises(ValueError):b.call(data)
        self.assertEqual(before,self.vault.path('ehentai').read_bytes())

    def test_extension_private_and_no_stealth_or_challenge_export(self):
        b=self.browser;b.provider='ehentai';b.session='generated-window'
        folder=Path(self.tmp.name)/'extension';folder.mkdir(mode=0o700);b.extension(folder)
        manifest=json.loads((folder/'manifest.json').read_text())
        self.assertEqual(manifest['permissions'],['cookies'])
        self.assertNotIn('web_accessible_resources',manifest)
        for file in folder.iterdir():self.assertEqual(file.stat().st_mode&0o777,0o600)
        script=(folder/'save.js').read_text()
        self.assertNotIn('navigator.webdriver',script)
        self.assertNotIn('chrome.debugger',script)

    def test_text_is_stdin_and_actions_reject_invalid_input(self):
        b=self.browser;b.provider='ehentai';b.session='generated-window';b.deadline=time.monotonic()+30
        with patch.object(b,'run',return_value=b'') as run:
            b.call({'op':'text','session':b.session,'text':'generated-password'})
            self.assertNotIn('generated-password',str(run.call_args.args))
            self.assertEqual(run.call_args.kwargs['input'],b'generated-password')
            for bad in ({'op':'click','x':float('nan'),'y':1},{'op':'key','key':'ctrl+alt+Delete'},
                        {'op':'scroll','delta':10000},{'op':'text','text':'\0'}):
                with self.assertRaises(ValueError):b.call({**bad,'session':b.session})


if __name__=='__main__':unittest.main()
