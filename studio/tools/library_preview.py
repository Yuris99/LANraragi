"""Local preview of one Library section with the shared kit, as the gateway would serve it.

Serves /_library/* and /library-guide from library_kit.py (read-only) and proxies the
section prefix to the section's own dev server. Development only; never deployed.

  python studio/tools/library_preview.py --prefix /audio/ --upstream http://127.0.0.1:8080
  python studio/tools/library_preview.py --prefix /real/ --upstream http://127.0.0.1:9999 --strip

--strip removes the prefix before proxying (the gateway does this for /real/ only).
--override /real/css=deploy/stash-ui/nmlo-stash-ui.css answers that path from a local file
instead of the upstream, so a change can be checked without installing it anywhere.
Then open http://127.0.0.1:43200/<prefix> and http://127.0.0.1:43200/library-guide.
"""
import argparse
import http.client
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import library_kit  # noqa: E402

HOP = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te',
       'trailers', 'transfer-encoding', 'upgrade', 'host'}


LOCAL_TYPES = {'.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
               '.html': 'text/html; charset=utf-8'}


def make_handler(prefix, upstream, strip, overrides=None):
    target = urllib.parse.urlsplit(upstream)
    overrides = overrides or {}

    class Preview(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def kit(self, name):
            body = library_kit.ASSETS[name].encode()
            self.send_response(200)
            self.send_header('Content-Type', library_kit.TYPES[name.rsplit('.', 1)[1]])
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def route(self):
            path = urllib.parse.urlsplit(self.path).path
            match = re.fullmatch(r'/_library/([a-z0-9-]+\.(?:css|js))', path)
            if match and match.group(1) in library_kit.ASSETS:
                return self.kit(match.group(1))
            if path == '/library-guide':
                return self.kit('guide.html')
            if path in overrides:
                body = Path(overrides[path]).read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', LOCAL_TYPES.get(Path(overrides[path]).suffix, 'application/octet-stream'))
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                if self.command != 'HEAD':
                    self.wfile.write(body)
                return
            if path == prefix.rstrip('/'):
                self.send_response(308); self.send_header('Location', prefix)
                self.send_header('Content-Length', '0'); self.end_headers(); return
            if not path.startswith(prefix):
                self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers(); return
            self.proxy()

        def proxy(self):
            path = self.path[len(prefix) - 1:] if strip else self.path
            length = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
            headers['X-Forwarded-Prefix'] = prefix.rstrip('/')
            conn_type = http.client.HTTPSConnection if target.scheme == 'https' else http.client.HTTPConnection
            conn = conn_type(target.hostname, target.port, timeout=60)
            try:
                conn.request(self.command, path, body=body, headers=headers)
                response = conn.getresponse()
                self.send_response(response.status, response.reason)
                data = response.read()
                for key, value in response.getheaders():
                    if key.lower() in HOP or key.lower() == 'content-length':
                        continue
                    if key.lower() == 'location' and strip and value.startswith('/'):
                        value = prefix.rstrip('/') + value
                    self.send_header(key, value)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                if self.command != 'HEAD':
                    self.wfile.write(data)
            except OSError as error:
                message = ('upstream unavailable: %s' % error).encode()
                self.send_response(502); self.send_header('Content-Length', str(len(message)))
                self.end_headers(); self.wfile.write(message)
            finally:
                conn.close()

        do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = route

        def log_message(self, *args):
            pass

    return Preview


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--prefix', required=True, help='section path, e.g. /audio/')
    parser.add_argument('--upstream', required=True, help='section dev server, e.g. http://127.0.0.1:8080')
    parser.add_argument('--strip', action='store_true', help='remove the prefix before proxying')
    parser.add_argument('--port', type=int, default=43200)
    parser.add_argument('--override', action='append', default=[], metavar='PATH=FILE',
                        help='answer PATH from a local FILE; repeatable')
    args = parser.parse_args()
    prefix = '/' + args.prefix.strip('/') + '/'
    overrides = {}
    for item in args.override:
        path, _, file = item.partition('=')
        if not path.startswith('/') or not Path(file).is_file():
            parser.error('--override needs /path=existing-file: ' + item)
        overrides[path] = str(Path(file).resolve())
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(prefix, args.upstream, args.strip, overrides))
    print('preview http://127.0.0.1:%d%s  guide http://127.0.0.1:%d/library-guide' % (args.port, prefix, args.port))
    server.serve_forever()


if __name__ == '__main__':
    main()
