"""Only explicit valid user input keeps the generated login window alive."""
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from login_service import DesktopBrowser, LoginBrowser


class LoginIdleTimeoutTests(unittest.TestCase):
    def browser(self, kind):
        vault = SimpleNamespace(status=lambda provider: {'provider': provider, 'state': 'not_saved'},
                                save=Mock(return_value={'state': 'saved_unverified'}))
        browser = kind(vault)
        browser.provider = 'ehentai'
        browser.session = 'generated-window'
        browser.deadline = 1900
        browser.frame = Mock(return_value={'image': 'generated-preview'})
        browser.run = Mock(return_value=b'')
        browser.page = SimpleNamespace(mouse=Mock(), keyboard=Mock(), goto=Mock(return_value=SimpleNamespace(status=200)))
        return browser

    def test_valid_input_renews_thirty_minutes_for_both_browser_modes(self):
        actions = ({'op': 'click', 'x': 50, 'y': 50}, {'op': 'text', 'text': 'generated'},
                   {'op': 'key', 'key': 'Tab'}, {'op': 'scroll', 'delta': 100}, {'op': 'visit'})
        for kind in (LoginBrowser, DesktopBrowser):
            for action in actions:
                with self.subTest(mode=kind.__name__, op=action['op']):
                    browser = self.browser(kind)
                    with patch('login_service.time.monotonic', return_value=1000):
                        browser.call({**action, 'session': browser.session})
                    self.assertEqual(browser.deadline, 2800)

    def test_polling_does_not_extend_idle_expiry(self):
        for kind in (LoginBrowser, DesktopBrowser):
            browser = self.browser(kind)
            with patch('login_service.time.monotonic', return_value=1000):
                browser.call({'op': 'frame', 'session': browser.session})
                status = browser.call({'op': 'status'})
            self.assertEqual(browser.deadline, 1900)
            self.assertEqual(status['idle_timeout_seconds'], 1800)
            self.assertEqual(status['idle_remaining_seconds'], 900)

    def test_continued_input_survives_original_deadline_then_idle_closes(self):
        for kind in (LoginBrowser, DesktopBrowser):
            browser = self.browser(kind)
            for now in (1000, 2000, 3000):
                with patch('login_service.time.monotonic', return_value=now):
                    browser.call({'op': 'key', 'key': 'Tab', 'session': browser.session})
                self.assertEqual(browser.deadline, now + 1800)
            with patch('login_service.time.monotonic', return_value=4800):
                browser.expire()
            self.assertIsNone(browser.session)
            self.assertEqual(browser.deadline, 0)

    def test_invalid_input_or_wrong_session_does_not_renew(self):
        for kind in (LoginBrowser, DesktopBrowser):
            for action in ({'op': 'click', 'x': -1, 'y': 0}, {'op': 'key', 'key': 'unsupported'},
                           {'op': 'scroll', 'delta': 10000}, {'op': 'text', 'text': '\0'}):
                browser = self.browser(kind)
                with patch('login_service.time.monotonic', return_value=1000):
                    with self.assertRaises(ValueError):
                        browser.call({**action, 'session': browser.session})
                self.assertEqual(browser.deadline, 1900)
            browser = self.browser(kind)
            with patch('login_service.time.monotonic', return_value=1000):
                with self.assertRaises(ValueError):
                    browser.call({'op': 'key', 'key': 'Tab', 'session': 'wrong-window'})
            self.assertEqual(browser.deadline, 1900)

    def test_save_renews_idle_without_changing_fifteen_second_save_window(self):
        browser = self.browser(DesktopBrowser)
        with patch('login_service.time.monotonic', return_value=1000):
            self.assertTrue(browser.call({'op': 'save', 'session': browser.session})['saving'])
        self.assertEqual(browser.deadline, 2800)
        self.assertEqual(browser.saving_until, 1015)
        with patch('login_service.time.monotonic', return_value=1005):
            browser.call({'op': 'desktop-session', 'session': browser.session, 'cookies': []})
        self.assertEqual(browser.deadline, 2800, 'Automatic export callback is not user activity')


if __name__ == '__main__':
    unittest.main()
