"""Loopback-only, independent service; local media is opened read-only."""
import base64
import hmac
import json
import mimetypes
import os
import re
import socket
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PureWindowsPath
from urllib.parse import parse_qs, urlsplit

from catalog import Catalog, text
from subtitles import read_subtitles

HERE = Path(__file__).resolve().parent
AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.aac', '.ogg', '.opus', '.wav', '.flac', '.mp4', '.webm'}


def media_path(root, relative, extensions=None):
    text(relative, '상대 파일 경로', 2000)
    windows = PureWindowsPath(relative)
    if windows.drive or windows.root or '\\' in relative or ':' in relative:
        raise ValueError('미디어 폴더 내부의 / 구분 상대 경로가 필요합니다.')
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()) or candidate.suffix.lower() not in (extensions or AUDIO_EXTENSIONS):
        raise ValueError('허용된 미디어 폴더·음성 파일 형식이 아닙니다.')
    if not candidate.is_file():
        raise ValueError('등록할 로컬 파일을 찾을 수 없습니다.')
    return candidate


class Handler(BaseHTTPRequestHandler):
    server_version = 'AudioStudio/0.1'

    def log_message(self, *args):
        pass  # Titles, paths and source URLs do not belong in request logs.

    def authorized(self):
        # Require a loopback Host, preventing browser DNS rebinding in passwordless mode.
        try:
            host = urlsplit('http://' + self.headers.get('Host', '')).hostname
        except ValueError:
            host = None
        if host not in ('127.0.0.1', 'localhost', '::1'):
            self.reply({'error': '로컬 호스트 요청만 허용합니다.'}, 403)
            return False
        password = self.server.password
        expected = 'Basic ' + base64.b64encode(('admin:' + password).encode()).decode()
        if password and not hmac.compare_digest(self.headers.get('Authorization', '').encode(), expected.encode()):
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="Audio Studio", charset="UTF-8"')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return False
        return True

    def reply(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(raw)

    def dispatch(self, mutate=False):
        if not self.authorized():
            return
        try:
            if mutate:
                origin = self.headers.get('Origin')
                if origin and origin not in ('http://' + self.headers['Host'], 'https://' + self.headers['Host']):
                    return self.reply({'error': '다른 사이트의 요청은 허용하지 않습니다.'}, 403)
                if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                    return self.reply({'error': '다른 사이트의 요청은 허용하지 않습니다.'}, 403)
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    return self.reply({'error': 'JSON 요청이 필요합니다.'}, 415)
                length = int(self.headers.get('Content-Length', '0'))
                if not 1 <= length <= 1024 * 1024:
                    raise ValueError('요청 크기는 1 MiB 이하여야 합니다.')
                data = json.loads(self.rfile.read(length), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('유한한 JSON 값이 필요합니다.')))
                if not isinstance(data, dict):
                    raise ValueError('JSON 객체가 필요합니다.')
                self.post(data)
            else:
                self.get()
        except KeyError:
            self.reply({'error': '대상을 찾을 수 없거나 필수 입력이 빠졌습니다.'}, 404)
        except sqlite3.IntegrityError:
            self.reply({'error': '이미 등록된 트랙 또는 출처입니다.'}, 409)
        except (ValueError, TypeError) as error:
            self.reply({'error': str(error)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.reply({'error': '요청을 처리할 수 없습니다.'}, 500)

    def do_GET(self):
        self.dispatch()

    def do_HEAD(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch(True)

    def get(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        store = self.server.catalog
        if path == '/api/health':
            return self.reply({'status': 'ok', 'service': 'audio-studio', 'schema': 1, 'upstream_access': False})
        if path in ('/api/works', '/api/export'):
            query = parse_qs(parsed.query).get('q', [''])[0] if path == '/api/works' else ''
            return self.reply({'schema': 1, 'works': store.works(query)})
        match = re.fullmatch('/api/editions/([0-9a-f]{32})', path)
        if match:
            return self.reply(store.edition(match[1]))
        match = re.fullmatch('/api/tracks/([0-9a-f]{32})/media', path)
        if match:
            track = store.track(match[1])
            return self.stream(media_path(self.server.media_root, track['relative_path']))
        match = re.fullmatch('/api/subtitles/([0-9a-f]{32})', path)
        if match:
            subtitle = store.subtitle(match[1])
            file = media_path(self.server.media_root, subtitle['relative_path'], {'.srt', '.vtt'})
            return self.reply({'cues': read_subtitles(file)})
        asset = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/player.css': 'player.css', '/player.js': 'player.js', '/player-core.js': 'player-core.js'}.get(path)
        if not asset:
            return self.reply({'error': '찾을 수 없습니다.'}, 404)
        raw = (HERE / 'web' / asset).read_bytes()
        self.send_response(200)
        # Windows registry associations may label .js as text/plain, which nosniff blocks.
        content_types = {'index.html': 'text/html', 'app.js': 'text/javascript', 'style.css': 'text/css', 'player.css': 'text/css', 'player.js': 'text/javascript', 'player-core.js': 'text/javascript'}
        self.send_header('Content-Type', content_types[asset] + '; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; media-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(raw)

    def post(self, data):
        path = urlsplit(self.path).path
        store = self.server.catalog
        if path == '/api/works':
            return self.reply(store.create_work(data['title'], data.get('rj_code', '')), 201)
        match = re.fullmatch('/api/works/([0-9a-f]{32})/codes', path)
        if match:
            return self.reply(store.add_code(match[1], data['code']), 201)
        if path == '/api/editions':
            return self.reply(store.create_edition(data['work_id'], data['title'], data['kind'],
                              data.get('language', ''), data.get('credits')), 201)
        match = re.fullmatch('/api/editions/([0-9a-f]{32})/(profile|order)', path)
        if match:
            if match[2] == 'profile':
                return self.reply(store.set_profile(match[1], data['media_type'], data['translation']))
            return self.reply(store.reorder_tracks(match[1], data['track_ids']))
        match = re.fullmatch('/api/editions/([0-9a-f]{32})/(sources|tracks)', path)
        if match:
            if match[2] == 'sources':
                return self.reply(store.add_source(match[1], data['provider'], data['external_id'],
                                  data['url'], data['raw_metadata']), 201)
            media_path(self.server.media_root, data['relative_path'])
            return self.reply(store.add_track(match[1], data['title'], data['relative_path'],
                              data.get('duration', 0)), 201)
        match = re.fullmatch('/api/tracks/([0-9a-f]{32})/progress', path)
        if match:
            return self.reply(store.progress(match[1], data['seconds']))
        match = re.fullmatch('/api/tracks/([0-9a-f]{32})/subtitles', path)
        if match:
            file = media_path(self.server.media_root, data['relative_path'], {'.srt', '.vtt'})
            read_subtitles(file)
            return self.reply(store.add_subtitle(match[1], data['relative_path'], data.get('language', 'ko'), data.get('label', '한국어')), 201)
        return self.reply({'error': '찾을 수 없습니다.'}, 404)

    def stream(self, path):
        with path.open('rb') as media:
            size = os.fstat(media.fileno()).st_size
            start, end, status = 0, size - 1, 200
            value = self.headers.get('Range')
            if value:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
                valid = bool(match and (match[1] or match[2]) and size)
                if valid:
                    if match[1]:
                        start = int(match[1]); end = min(int(match[2]), size - 1) if match[2] else size - 1
                    else:
                        suffix = int(match[2]); valid = suffix > 0
                        start = max(0, size - suffix)
                    valid = valid and start <= end and start < size
                if not valid:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                status = 206
            self.send_response(status)
            self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Length', str(max(0, end - start + 1)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if status == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if self.command == 'HEAD':
                return
            media.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                block = media.read(min(256 * 1024, remaining))
                if not block:
                    break
                self.wfile.write(block)
                remaining -= len(block)


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        # Windows SO_REUSEADDR can permit two servers on one port; refuse that.
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(catalog, media_root, port=43130, password='', bind='127.0.0.1'):
    if bind not in ('127.0.0.1', '0.0.0.0'):
        raise ValueError('지원하지 않는 바인딩 주소입니다.')
    server = LocalServer((bind, port), Handler)
    server.catalog = catalog
    server.media_root = Path(media_root).resolve()
    server.password = password
    server.daemon_threads = True
    return server


if __name__ == '__main__':
    # No .env, comic DB, LANraragi API, downloader, NAS or Redis configuration is loaded.
    server = make_server(Catalog(HERE / 'data' / 'audio.sqlite3'), HERE / 'media',
                         password=os.environ.get('AUDIO_STUDIO_PASSWORD', ''),
                         bind=os.environ.get('AUDIO_STUDIO_BIND', '127.0.0.1'))
    print('Audio Studio: http://127.0.0.1:43130 (Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
