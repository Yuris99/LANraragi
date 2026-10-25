"""Synthetic HTTP responses only; no vault files, accounts or site requests."""
import io
import json
from pathlib import Path
import sys
import socket
import ssl
import unittest
import urllib.error
from unittest.mock import Mock, patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from site_sessions import source_document
from metadata import parse_html
from test_metadata import E,eh_html


class SourceDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.vault=Mock(last_requests={})
        self.vault.read.side_effect=FileNotFoundError

    def fetch(self,body,url=E):
        response=io.BytesIO(body)
        response.status=200
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=response
            result=source_document(self.vault,url)
            opener.return_value.open.assert_called_once()
        return result,self.vault.last_requests['exhentai' if 'exhentai.org' in url else 'ehentai']

    def test_http_200_gallery_is_parsed_without_exposing_document_in_diagnostics(self):
        result,trace=self.fetch(eh_html().encode())
        self.assertEqual(result['status'],'ok')
        self.assertEqual((trace['mode'],trace['http_status']),('anonymous',200))
        self.assertEqual(parse_html(E,result['document'])['external_id'],'987654')
        self.assertEqual(set(trace),{'mode','status','http_status','at'})
        self.assertNotIn(E,json.dumps(trace))
        self.assertNotIn('A Garden',json.dumps(trace))

    def test_http_200_challenge_and_wrong_identity_are_not_parsing_success(self):
        for body in ('<h1>Human verification</h1>',eh_html().replace('987654','1')):
            with self.subTest(kind=body[:20]):
                result,trace=self.fetch(body.encode())
                self.assertEqual(trace['http_status'],200)
                with self.assertRaises(ValueError):parse_html(E,result['document'])

    def test_saved_session_is_still_not_proof_of_valid_gallery(self):
        # A standard account cookie in memory; never read a browser profile.
        import http.cookiejar
        cookie=http.cookiejar.Cookie(0,'ipb_member_id','generated',None,False,'.e-hentai.org',True,True,'/',True,True,None,True,None,None,{})
        self.vault.read.side_effect=None
        self.vault.read.return_value=[cookie]
        result,trace=self.fetch(b'<h1>Login required</h1>')
        self.assertEqual((trace['mode'],trace['http_status']),('saved_session',200))
        with self.assertRaises(ValueError):parse_html(E,result['document'])
        self.assertNotIn('generated',json.dumps(trace))

    def test_search_response_records_http_status_without_claiming_authentication(self):
        _,trace=self.fetch(b'<html>search</html>','https://e-hentai.org/?f_search=generated')
        self.assertEqual(trace['http_status'],200)
        self.assertNotIn('site_verified',trace)

    def test_http_denial_and_connection_failure_remain_distinct_without_retry(self):
        for error,expected,code in ((urllib.error.HTTPError(E,403,'private',{},None),'access_required',403),
                                    (urllib.error.URLError('private'),'unavailable',None)):
            with self.subTest(status=expected),patch('urllib.request.build_opener') as opener:
                opener.return_value.open.side_effect=error
                source_document(self.vault,E)
                opener.return_value.open.assert_called_once()
                trace=self.vault.last_requests['ehentai']
                self.assertEqual((trace['status'],trace['http_status']),(expected,code))
                self.assertNotIn('private',json.dumps(trace))

    def test_exhentai_without_own_session_makes_no_request(self):
        with patch('urllib.request.build_opener') as opener:
            self.assertEqual(source_document(self.vault,'https://exhentai.org/g/1/abc/')['status'],'session_required')
            opener.assert_not_called()
        self.assertEqual(self.vault.last_requests['exhentai']['mode'],'not_sent')

    def test_response_limit_keeps_the_received_http_status(self):
        result,trace=self.fetch(b'x'*(1024*1024+1))
        self.assertEqual(result['status'],'response_limit')
        self.assertEqual(trace['http_status'],200)

    def test_connection_failures_record_only_fixed_categories_without_retry(self):
        cases=[(ssl.SSLCertVerificationError('private'),'certificate_error'),
               (ssl.SSLError('private'),'tls_error'),(socket.gaierror('private'),'dns_error'),
               (TimeoutError('private'),'timeout'),(ConnectionResetError('private'),'connection_reset'),
               (ConnectionRefusedError('private'),'connection_refused'),(OSError('private'),'network_error'),
               ('private url and cookie','network_error')]
        for reason,expected in cases:
            with self.subTest(kind=expected),patch('urllib.request.build_opener') as opener:
                opener.return_value.open.side_effect=urllib.error.URLError(reason)
                result=source_document(self.vault,E)
                trace=self.vault.last_requests['ehentai']
                self.assertEqual((result['status'],trace['error_kind']),('unavailable',expected))
                self.assertIsNone(trace['http_status'])
                self.assertNotIn('private',json.dumps(result)+json.dumps(trace))
                self.assertNotIn(E,json.dumps(trace))
                opener.return_value.open.assert_called_once()

    def test_decode_failure_keeps_http_200_without_claiming_parsing_success(self):
        result,trace=self.fetch(b'\xff')
        self.assertEqual(result,{'status':'unavailable','error_kind':'response_decode_error'})
        self.assertEqual((trace['http_status'],trace['error_kind']),(200,'response_decode_error'))

    def test_http_server_failure_keeps_its_http_code_and_no_transport_guess(self):
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=urllib.error.HTTPError(E,503,'private',{},None)
            source_document(self.vault,E)
        trace=self.vault.last_requests['ehentai']
        self.assertEqual((trace['status'],trace['http_status']),('unavailable',503))
        self.assertNotIn('error_kind',trace)

    def test_later_success_replaces_previous_failure_category(self):
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=ConnectionResetError('private')
            source_document(self.vault,E)
        self.assertEqual(self.vault.last_requests['ehentai']['error_kind'],'connection_reset')
        _,trace=self.fetch(eh_html().encode())
        self.assertNotIn('error_kind',trace)
        self.assertEqual((trace['status'],trace['http_status']),('ok',200))


if __name__=='__main__':unittest.main()
