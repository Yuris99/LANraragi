"""Synthetic failures only; no sockets, vault files or site requests."""
import http.cookiejar
import email.message
import getpass
import io
import json
from pathlib import Path
import ssl
import sys
import unittest
import urllib.error
import urllib.request
import warnings
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from diagnostics.source_transport_probe import probe,main

URL='https://e-hentai.org/g/987654/generated/'


class ProbeTests(unittest.TestCase):
    def setUp(self):
        cookie=http.cookiejar.Cookie(0,'ipb_member_id','generated-secret',None,False,
            '.e-hentai.org',True,True,'/',True,True,None,True,None,None,{})
        self.vault=Mock()
        self.vault.read.return_value=[cookie]

    def test_real_ssl_frame_identifies_handshake_without_changing_tls(self):
        def reset(*args,**kwargs):
            socket=Mock()
            socket.gettimeout.return_value=20
            socket._sslobj.do_handshake.side_effect=ConnectionResetError('private error and URL')
            try:ssl.SSLSocket.do_handshake(socket)
            except OSError as error:raise urllib.error.URLError(error)
        original=urllib.request.OpenerDirector.open
        original_tls=ssl._create_default_https_context
        with patch.object(urllib.request.HTTPSHandler,'https_open',side_effect=reset) as request:
            result=probe(self.vault,URL)
        self.assertIs(urllib.request.OpenerDirector.open,original)
        self.assertIs(ssl._create_default_https_context,original_tls)
        self.assertEqual(request.call_args.args[0].get_header('User-agent'),'LibraryStudio/0.1')
        self.assertEqual((result['error_kind'],result['failure_phase']),('connection_reset','tls_handshake'))
        self.assertEqual((result['open_calls'],result['mode']),(1,'saved_session'))
        for private in ('private','generated-secret',URL):self.assertNotIn(private,json.dumps(result))

    def test_reset_with_no_matching_frame_stays_unknown(self):
        with patch.object(urllib.request.HTTPSHandler,'https_open',side_effect=ConnectionResetError('private')):
            result=probe(self.vault,URL)
        self.assertEqual((result['error_kind'],result['failure_phase']),('connection_reset','transport_unknown'))

    def test_http_error_is_not_guessed_to_be_a_handshake_failure(self):
        error=urllib.error.HTTPError(URL,503,'private',{},None)
        with patch.object(urllib.request.HTTPSHandler,'https_open',side_effect=error):
            result=probe(self.vault,URL)
        self.assertEqual((result['http_status'],result['failure_phase']),(503,'http_status_received'))
        self.assertEqual(result['open_calls'],1)

    def test_missing_session_never_falls_back_to_anonymous(self):
        for missing in (FileNotFoundError(),None):
            self.vault.read.side_effect=missing
            self.vault.read.return_value=[]
            with patch('urllib.request.build_opener') as opener:
                result=probe(self.vault,URL)
            opener.assert_not_called()
            self.assertEqual((result['status'],result['mode'],result['open_calls']),('session_required','not_sent',0))

    def test_received_document_is_not_parsing_or_authentication_success(self):
        response=io.BytesIO(b'private login document')
        response.status=200
        with patch.object(urllib.request.HTTPSHandler,'https_open',return_value=response):
            # A normal opener expects response attributes used by HTTPErrorProcessor.
            response.code=200;response.msg='OK';response.info=email.message.Message
            result=probe(self.vault,URL)
        self.assertTrue(result['document_received'])
        self.assertFalse(result['document_parsed'])
        self.assertNotIn('private',json.dumps(result))

    def test_other_routes_and_key_logging_make_no_request(self):
        with patch('urllib.request.build_opener') as opener:
            for url in ('https://exhentai.org/g/1/generated/','https://e-hentai.org/?f_search=generated',
                        'http://e-hentai.org/g/1/generated/'):
                with self.assertRaises(ValueError):probe(self.vault,url)
            with patch.dict('os.environ',{'SSLKEYLOGFILE':'generated-only'}):
                with self.assertRaises(ValueError):probe(self.vault,URL)
        opener.assert_not_called()

    def test_cli_uses_readonly_vault_and_never_echoes_input(self):
        output=io.StringIO()
        with patch('sys.stdin') as input_stream,patch('sys.stdout',output),patch(
                'diagnostics.source_transport_probe.getpass.getpass',return_value=URL),patch(
                'diagnostics.source_transport_probe.CookieVault') as vault,patch(
                'diagnostics.source_transport_probe.probe',return_value={'status':'session_required'}):
            input_stream.isatty.return_value=True
            main()
        self.assertTrue(vault.call_args.kwargs['readonly'])
        self.assertEqual(json.loads(output.getvalue()),{'status':'session_required'})
        self.assertNotIn(URL,output.getvalue())

    def test_cli_unexpected_local_error_does_not_expose_message_or_claim_no_request(self):
        output=io.StringIO()
        with patch('sys.stdin') as input_stream,patch('sys.stdout',output),patch(
                'diagnostics.source_transport_probe.getpass.getpass',return_value=URL),patch(
                'diagnostics.source_transport_probe.CookieVault',side_effect=RuntimeError('private exception')):
            input_stream.isatty.return_value=True
            main()
        result=json.loads(output.getvalue())
        self.assertEqual(result['status'],'probe_unavailable')
        self.assertIsNone(result['open_calls'])
        self.assertNotIn('private',output.getvalue())

    def test_cli_no_echo_failure_stops_before_plaintext_input_or_any_vault_request(self):
        output,error_output=io.StringIO(),io.StringIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',getpass.GetPassWarning)
            filters=list(warnings.filters)
            with patch('sys.stdin') as input_stream,patch('sys.stdout',output),patch(
                    'sys.stderr',error_output),patch(
                    'diagnostics.source_transport_probe.getpass.getpass',side_effect=getpass.fallback_getpass),patch(
                    'getpass._raw_input',return_value=URL) as plaintext,patch(
                    'diagnostics.source_transport_probe.CookieVault') as vault,patch(
                    'diagnostics.source_transport_probe.probe') as request:
                input_stream.isatty.return_value=True
                main()
            self.assertEqual(warnings.filters,filters)
        plaintext.assert_not_called()
        vault.assert_not_called()
        request.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['status'],'probe_unavailable')
        self.assertNotIn(URL,output.getvalue())
        self.assertEqual(error_output.getvalue(),'')

    def test_cli_private_pipe_input_still_works_without_terminal_prompt(self):
        input_stream=Mock()
        input_stream.isatty.return_value=False
        input_stream.buffer=io.BytesIO(json.dumps({'url':URL}).encode()+b'\n')
        output=io.StringIO()
        with patch('sys.stdin',input_stream),patch('sys.stdout',output),patch(
                'diagnostics.source_transport_probe.getpass.getpass') as prompt,patch(
                'diagnostics.source_transport_probe.CookieVault') as vault,patch(
                'diagnostics.source_transport_probe.probe',return_value={'status':'session_required'}) as request:
            main()
        prompt.assert_not_called()
        self.assertTrue(vault.call_args.kwargs['readonly'])
        request.assert_called_once_with(vault.return_value,URL)
        self.assertEqual(json.loads(output.getvalue()),{'status':'session_required'})
        self.assertNotIn(URL,output.getvalue())


if __name__=='__main__':unittest.main()
