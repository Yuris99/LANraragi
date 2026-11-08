"""Hub login: one cookie session for every Library section (synthetic password only)."""
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from library_session import Sessions, COOKIE
from server import Studio, make_server
from store import Store
from test_studio import temporary_directory


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


class SessionTokenTests(unittest.TestCase):
    def test_signed_token_round_trip_and_rejections(self):
        s = Sessions(password='pw')
        token = s.issue()
        self.assertTrue(s.valid(token))
        self.assertFalse(s.valid(token[:-2] + 'xx'))
        self.assertFalse(s.valid(''))
        self.assertFalse(s.valid('1.2'))
        self.assertFalse(s.valid(s.issue(now=0)))  # expired
        # Changing the password signs every browser out.
        self.assertFalse(Sessions(password='other').valid(token))

    def test_secret_file_persists_across_restarts(self):
        with temporary_directory() as temp:
            path = Path(temp) / 'session.key'
            token = Sessions(path, password='pw').issue()
            self.assertTrue(Sessions(path, password='pw').valid(token))

    def test_backoff_after_repeated_failures(self):
        s = Sessions(password='pw')
        for _ in range(4):
            self.assertFalse(s.check_password('no', 'client'))
        self.assertIsNone(s.check_password('pw', 'client'))
        self.assertTrue(s.check_password('pw', 'someone-else'))


class HubLoginHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(); self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'STUDIO_PASSWORD': 'test-password'})
        env.start(); self.addCleanup(env.stop)

        class FakeLRR:
            def json(self, path, *args):
                if path == '/api/info': return {'version': 'test'}
                raise ValueError('Unknown fake endpoint')
        self.app = Studio(Store(Path(self.temp.name) / 'http.db'), FakeLRR())
        self.server = make_server('127.0.0.1', 0, self.app)
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        self.origin = self.url

    def call(self, path, body=None, headers=None, method=None):
        headers = dict(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode(); headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)
        try:
            return OPENER.open(req, timeout=5)
        except urllib.error.HTTPError as error:
            return error

    def login(self):
        response = self.call('/api/session/login', {'password': 'test-password'}, {'Origin': self.origin})
        self.assertEqual(response.status, 200)
        cookie = response.headers['Set-Cookie']
        self.assertIn('HttpOnly', cookie); self.assertIn('SameSite=Lax', cookie)
        return cookie.split(';')[0]

    def test_public_login_page_and_kit(self):
        for path in ['/login', '/_library/tokens.css', '/_library/shell.js', '/_library/login.js', '/api/session']:
            with self.subTest(path=path):
                self.assertEqual(self.call(path).status, 200)
        self.assertEqual(self.call('/_library/../server.py').status, 401)
        self.assertEqual(json.load(self.call('/api/session')), {'authenticated': False})

    def test_browser_navigation_redirects_to_login_without_popup(self):
        response = self.call('/works/' + 'a' * 32, headers={'Accept': 'text/html'})
        self.assertEqual(response.status, 303)
        self.assertEqual(response.headers['Location'], '/login?next=/works/' + 'a' * 32)
        api = self.call('/api/works')
        self.assertEqual(api.status, 401)
        self.assertIsNone(api.headers.get('WWW-Authenticate'))

    def test_login_cookie_grants_every_section(self):
        self.assertEqual(self.call('/api/auth/check').status, 401)
        self.assertEqual(self.call('/api/session/login', {'password': 'wrong'}, {'Origin': self.origin}).status, 401)
        cookie = self.login()
        self.assertEqual(self.call('/api/auth/check', headers={'Cookie': cookie}).status, 204)
        self.assertEqual(self.call('/', headers={'Cookie': cookie}).status, 200)
        self.assertEqual(json.load(self.call('/api/session', headers={'Cookie': cookie})), {'authenticated': True})
        self.assertEqual(self.call('/api/auth/check', headers={'Cookie': COOKIE + '=forged.token.value'}).status, 401)

    def test_cookie_writes_require_same_origin(self):
        cookie = self.login()
        self.assertEqual(self.call('/api/session/login', {'password': 'test-password'}).status, 403)  # no Origin
        self.assertEqual(self.call('/api/tag-presets', {}, {'Cookie': cookie}).status, 403)
        self.assertEqual(self.call('/api/tag-presets', {}, {'Cookie': cookie, 'Origin': 'https://evil.invalid'}).status, 403)

    def test_logout_clears_cookie(self):
        response = self.call('/api/session/logout', {}, {'Origin': self.origin})
        self.assertEqual(response.status, 200)
        self.assertIn('Max-Age=0', response.headers['Set-Cookie'])

    def test_basic_clients_still_work_and_get_challenge(self):
        import base64
        good = 'Basic ' + base64.b64encode(b'admin:test-password').decode()
        self.assertEqual(self.call('/api/auth/check', headers={'Authorization': good}).status, 204)
        bad = self.call('/api/works', headers={'Authorization': 'Basic ' + base64.b64encode(b'admin:x').decode()})
        self.assertEqual(bad.status, 401)
        self.assertIn('Basic', bad.headers['WWW-Authenticate'])

    def test_secure_cookie_behind_https_gateway(self):
        response = self.call('/api/session/login', {'password': 'test-password'},
                             {'Origin': self.origin, 'X-Forwarded-Proto': 'https'})
        self.assertIn('; Secure', response.headers['Set-Cookie'])


if __name__ == '__main__':
    unittest.main()
