"""One normal saved-session request in a separate login-container Python process.

Reads the existing URL with hidden terminal input, or one JSON line on a pipe.
Never print input, cookies, documents, exception text, paths or frame locals.
Uses installed site_sessions unchanged; no service/configuration/file writes.
"""
import getpass
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

from site_sessions import CookieVault, source_document


def failure_phase(error):
    if isinstance(error,urllib.error.HTTPError):return 'http_status_received'
    reason=error.reason if isinstance(error,urllib.error.URLError) else error
    frames=set()
    traceback=getattr(reason,'__traceback__',None)
    while traceback:
        frames.add((traceback.tb_frame.f_globals.get('__name__'),traceback.tb_frame.f_code.co_name))
        traceback=traceback.tb_next
    for frame,phase in ((('ssl','do_handshake'),'tls_handshake'),
                        (('socket','getaddrinfo'),'dns_lookup'),
                        (('socket','create_connection'),'tcp_connect'),
                        (('http.client','_tunnel'),'proxy_connect'),
                        (('http.client','_read_status'),'http_headers')):
        if frame in frames:return phase
    return 'transport_unknown'


def probe(vault,url):
    if not isinstance(url,str) or len(url)>2048 or not re.fullmatch(
            r'https://e-hentai\.org/g/[0-9]+/[A-Za-z0-9]+/',url):
        raise ValueError('existing_gallery_required')
    if os.environ.get('SSLKEYLOGFILE'):
        raise ValueError('key_logging_configured')
    class SavedOnly:
        def __init__(self):self.last_requests={}
        def read(self,provider):
            try:cookies=vault.read(provider)
            except FileNotFoundError:raise ValueError('saved_session_required') from None
            if not cookies:raise ValueError('saved_session_required')
            return cookies
    saved=SavedOnly()
    original=urllib.request.OpenerDirector.open
    calls=0
    phase='not_sent'
    def observed_open(opener,*args,**kwargs):
        nonlocal calls,phase
        calls+=1
        try:response=original(opener,*args,**kwargs)
        except (OSError,UnicodeError) as error:
            phase=failure_phase(error)
            raise
        phase='http_status_received'
        return response
    urllib.request.OpenerDirector.open=observed_open
    try:result=source_document(saved,url)
    finally:urllib.request.OpenerDirector.open=original
    record=saved.last_requests.get('ehentai',{})
    return {**{key:record.get(key) for key in ('mode','status','http_status','error_kind','at')},
            'failure_phase':phase,'open_calls':calls,'document_received':result.get('status')=='ok',
            'document_parsed':False,'python':sys.version.split()[0],'openssl':ssl.OPENSSL_VERSION,
            'https_proxy_present':bool(urllib.request.getproxies().get('https')),
            'ca_override_present':bool(os.environ.get('SSL_CERT_FILE') or os.environ.get('SSL_CERT_DIR'))}


def main():
    try:
        if sys.stdin.isatty():data={'url':getpass.getpass('Existing gallery URL (input hidden): ')}
        else:
            raw=sys.stdin.buffer.readline(4097)
            if len(raw)>4096:raise ValueError('input_limit')
            data=json.loads(raw)
        if not isinstance(data,dict) or set(data)!={'url'}:raise ValueError('input_fields')
        vault=CookieVault(os.environ.get('STUDIO_SESSION_DIR','/sessions'),readonly=True)
        result=probe(vault,data['url'])
    except Exception:
        result={'status':'probe_unavailable','open_calls':None}
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
