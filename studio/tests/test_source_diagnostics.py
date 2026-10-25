"""Synthetic HTTP responses only; no vault files, accounts or site requests."""
import io
import http.client
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
        self.vault.last_requests['exhentai']={'status':'unavailable','error_kind':'connection_reset','error_phase':'tls_handshake'}
        with patch('urllib.request.build_opener') as opener:
            self.assertEqual(source_document(self.vault,'https://exhentai.org/g/1/abc/')['status'],'session_required')
            opener.assert_not_called()
        self.assertEqual(self.vault.last_requests['exhentai']['mode'],'not_sent')
        self.assertNotIn('error_kind',self.vault.last_requests['exhentai'])
        self.assertNotIn('error_phase',self.vault.last_requests['exhentai'])

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
                self.assertEqual(trace['error_phase'],'transport_unknown')
                self.assertNotIn('error_phase',result)
                self.assertIsNone(trace['http_status'])
                self.assertNotIn('private',json.dumps(result)+json.dumps(trace))
                self.assertNotIn(E,json.dumps(trace))
                opener.return_value.open.assert_called_once()

    def test_decode_failure_keeps_http_200_without_claiming_parsing_success(self):
        result,trace=self.fetch(b'\xff')
        self.assertEqual(result,{'status':'unavailable','error_kind':'response_decode_error'})
        self.assertEqual((trace['http_status'],trace['error_kind']),(200,'response_decode_error'))
        self.assertEqual(trace['error_phase'],'transport_unknown')

    def test_http_server_failure_keeps_its_http_code_and_no_transport_guess(self):
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=urllib.error.HTTPError(E,503,'private',{},None)
            source_document(self.vault,E)
        trace=self.vault.last_requests['ehentai']
        self.assertEqual((trace['status'],trace['http_status']),('unavailable',503))
        self.assertNotIn('error_kind',trace)
        self.assertNotIn('error_phase',trace)

    def test_later_success_replaces_previous_failure_category(self):
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=ConnectionResetError('private')
            source_document(self.vault,E)
        self.assertEqual(self.vault.last_requests['ehentai']['error_kind'],'connection_reset')
        self.assertEqual(self.vault.last_requests['ehentai']['error_phase'],'transport_unknown')
        _,trace=self.fetch(eh_html().encode())
        self.assertNotIn('error_kind',trace)
        self.assertNotIn('error_phase',trace)
        self.assertEqual((trace['status'],trace['http_status']),('ok',200))

    def observe_failure(self,callback,phase):
        def opening(request,timeout):
            try:callback()
            except OSError as error:raise urllib.error.URLError(error)
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=opening
            result=source_document(self.vault,E)
            opener.return_value.open.assert_called_once()
        trace=self.vault.last_requests['ehentai']
        self.assertEqual((trace['error_kind'],trace['error_phase']),('connection_reset',phase))
        self.assertEqual(set(trace),{'mode','status','http_status','at','error_kind','error_phase'})
        self.assertIsNone(trace['http_status'])
        self.assertEqual(result,{'status':'unavailable','error_kind':'connection_reset'})
        for private in ('private',E,'generated-secret','callback','traceback'):
            self.assertNotIn(private,json.dumps(trace))
        return trace

    def test_actual_ssl_frame_records_handshake_without_changing_tls(self):
        original=ssl._create_default_https_context
        self.observe_failure(self.reset_in_handshake,'tls_handshake')
        self.assertIs(ssl._create_default_https_context,original)

    def reset_in_handshake(self):
        connection=Mock()
        connection.gettimeout.return_value=20
        connection._sslobj.do_handshake.side_effect=ConnectionResetError('private generated-secret '+E)
        ssl.SSLSocket.do_handshake(connection)

    def test_actual_dns_frame_takes_priority_over_outer_tcp_frame(self):
        with patch('socket._socket.getaddrinfo',side_effect=ConnectionResetError('private')):
            self.observe_failure(lambda:socket.create_connection(('generated.invalid',443),20),'dns_lookup')

    def test_actual_tcp_frame_records_connect_without_opening_a_socket(self):
        connection=Mock()
        connection.connect.side_effect=ConnectionResetError('private')
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
        with patch('socket.getaddrinfo',return_value=addresses),patch('socket.socket',return_value=connection):
            self.observe_failure(lambda:socket.create_connection(('generated.invalid',443),20),'tcp_connect')
        connection.close.assert_called_once()

    def test_actual_http_status_frame_records_headers(self):
        connection=Mock()
        connection.makefile.return_value.readline.side_effect=ConnectionResetError('private')
        response=http.client.HTTPResponse(connection)
        self.observe_failure(response.begin,'http_headers')

    def test_actual_proxy_tunnel_frame_takes_priority_over_http_headers(self):
        connection=http.client.HTTPConnection('generated.invalid')
        connection.set_tunnel('generated.example')
        connection.sock=Mock()
        connection.sock.makefile.return_value.readline.side_effect=ConnectionResetError('private')
        connection.send=Mock()
        self.observe_failure(connection._tunnel,'proxy_connect')

    def test_nonstandard_function_name_is_not_tls_evidence(self):
        def do_handshake():raise ConnectionResetError('private')
        self.observe_failure(do_handshake,'transport_unknown')

    def test_later_http_denial_or_server_error_replaces_previous_phase(self):
        for code in (301,403,429,503):
            with self.subTest(code=code):
                self.observe_failure(self.reset_in_handshake,'tls_handshake')
                with patch('urllib.request.build_opener') as opener:
                    opener.return_value.open.side_effect=urllib.error.HTTPError(E,code,'private',{},None)
                    result=source_document(self.vault,E)
                    opener.return_value.open.assert_called_once()
                trace=self.vault.last_requests['ehentai']
                self.assertEqual(trace['http_status'],code)
                self.assertEqual(result['http_status'],code)
                self.assertNotIn('error_kind',trace)
                self.assertNotIn('error_phase',trace)

    def test_existing_authenticated_rpc_exposes_phase_only_in_status(self):
        import http.cookiejar
        import threading
        from login_service import BrowserActor,LoginBrowser,make_login_server
        from site_sessions import CookieVault,LoginClient

        self.vault.read.side_effect=None
        self.vault.read.return_value=[http.cookiejar.Cookie(0,'ipb_member_id','generated-secret',None,False,
            '.e-hentai.org',True,True,'/',True,True,None,True,None,None,{})]
        self.vault.path.return_value.stat.side_effect=FileNotFoundError
        self.vault.status.side_effect=lambda provider:CookieVault.status(self.vault,provider)
        actor=BrowserActor(self.vault,browser=LoginBrowser(self.vault))
        self.addCleanup(actor.close)
        token='generated-only-service-token-'+'a'*40
        gateway=make_login_server('127.0.0.1',0,actor,token)
        thread=threading.Thread(target=gateway.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(lambda:(gateway.shutdown(),gateway.server_close(),thread.join(timeout=3)))
        client=LoginClient('http://127.0.0.1:'+str(gateway.server_port),'unused-generated-path')
        def opening(request):
            try:self.reset_in_handshake()
            except OSError as error:raise urllib.error.URLError(error)
        with patch('site_sessions.read_service_token',return_value=token),patch(
                'urllib.request.HTTPSHandler.https_open',side_effect=opening) as source_request:
            result=client.call({'op':'source-document','url':E})
            status=client.call({'op':'status'})
        source_request.assert_called_once()
        self.assertEqual(result,{'status':'unavailable','error_kind':'connection_reset'})
        current=next(site for site in status['sites'] if site['provider']=='ehentai')
        self.assertEqual(current['last_request']['error_phase'],'tls_handshake')
        self.assertEqual(current['last_request']['mode'],'saved_session')
        self.assertEqual(current['state'],'saved_unverified')
        self.assertFalse(current['site_verified'])
        self.assertIsNone(status['active'])
        self.assertIsNone(actor.browser.browser)
        self.vault.save.assert_not_called()
        self.vault.forget.assert_not_called()
        self.vault.import_file.assert_not_called()
        for private in ('private','generated-secret',token,E):self.assertNotIn(private,json.dumps(status))


if __name__=='__main__':unittest.main()
