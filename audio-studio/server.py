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
from urllib.parse import parse_qs, urlsplit, quote

from catalog import Catalog, text
from covers import RplayCovers, CoverUnavailable
from title_metadata import TitleMetadata
from tag_visibility import TagVisibility, TagVisibilityConflict
from media_details import MediaDetails, MediaDetailsConflict
from subtitles import read_subtitles, parse_subtitles
from library_files import LibraryFiles, LibraryConflict, browse, voice_path, decode_text, DOCUMENTS
from catalog_annotations import CatalogAnnotations

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


def local_files(root, limit=2000):
    """Bounded, read-only picker for the explicitly configured media directory."""
    root = Path(root).resolve()
    items, visited, truncated = [], 0, False
    allowed = AUDIO_EXTENSIONS | {'.srt', '.vtt'}
    for directory, dirs, files in os.walk(root, followlinks=False):
        visited += 1
        if visited > 2000:
            truncated = True
            break
        parent = Path(directory)
        safe_dirs = []
        for name in dirs:
            directory_path = parent/name
            try:
                if (not directory_path.is_symlink()
                        and not getattr(directory_path, 'is_junction', lambda: False)()
                        and directory_path.resolve().is_relative_to(root)):
                    safe_dirs.append(name)
            except (OSError, RuntimeError):
                continue
        dirs[:] = sorted(safe_dirs)
        for name in sorted(files):
            path = parent/name
            if path.suffix.lower() not in allowed:
                continue
            try:
                resolved = path.resolve()
                if not resolved.is_relative_to(root) or not resolved.is_file():
                    continue
                kind = 'subtitle' if path.suffix.lower() in {'.srt', '.vtt'} else 'video' if path.suffix.lower() in {'.mp4', '.webm'} else 'audio'
                items.append({'relative_path': path.relative_to(root).as_posix(), 'kind': kind, 'bytes': resolved.stat().st_size})
            except (OSError, RuntimeError):
                continue
            if len(items) >= limit:
                truncated = True
                break
        if truncated:
            break
    return {'items': sorted(items, key=lambda item: item['relative_path'].casefold()), 'truncated': truncated}


class Handler(BaseHTTPRequestHandler):
    server_version = 'AudioStudio/0.1'

    def log_message(self, *args):
        pass  # Titles, paths and source URLs do not belong in request logs.

    def authorized(self):
        # Non-loopback hosts require both a password and an explicit allowlist.
        try:
            host = urlsplit('http://' + self.headers.get('Host', '')).hostname
        except ValueError:
            host = None
        if host not in ('127.0.0.1', 'localhost', '::1') and not (
                self.server.password and host in self.server.allowed_hosts):
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
            parsed = urlsplit(self.path)
            if parsed.path == '/audio' and not mutate:
                self.send_response(308)
                self.send_header('Location', '/audio/' + ('?' + parsed.query if parsed.query else ''))
                self.send_header('Content-Length', '0')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                return
            if parsed.path.startswith('/audio/'):
                self.path = self.path[len('/audio'):]
            if mutate:
                origin = self.headers.get('Origin')
                if origin and origin not in ('http://' + self.headers['Host'], 'https://' + self.headers['Host']):
                    return self.reply({'error': '다른 사이트의 요청은 허용하지 않습니다.'}, 403)
                if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                    return self.reply({'error': '다른 사이트의 요청은 허용하지 않습니다.'}, 403)
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    return self.reply({'error': 'JSON 요청이 필요합니다.'}, 415)
                length = int(self.headers.get('Content-Length', '0'))
                limit = 17 * 1024 * 1024 if urlsplit(self.path).path == '/api/uploads' else 1024 * 1024
                if not 1 <= length <= limit:
                    raise ValueError('요청 크기 제한을 넘었습니다.')
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
            return self.reply({'status': 'ok', 'service': 'audio-studio', 'schema': 1, 'upstream_access': True, 'upstream_scope': 'public_dlsite_rplay_artwork_tags_and_titles_only'})
        if path == '/api/tag-visibility':
            return self.reply(self.server.tag_visibility.read())
        if path == '/api/tag-vocabulary':
            return self.reply(json.loads((HERE / 'tag_vocabulary.json').read_text(encoding='utf-8')))
        if path == '/api/local-files':
            return self.reply(local_files(self.server.media_root))
        query = parse_qs(parsed.query)
        if path == '/api/library-files':
            return self.reply(self.server.library_files.read())
        if path == '/api/files':
            return self.reply(browse(self.server.media_root, query.get('path', [''])[0], int(query.get('offset', ['0'])[0])))
        if path in ('/api/files/text', '/api/files/content'):
            file = voice_path(self.server.media_root, query.get('path', [''])[0], file=True)
            if path.endswith('/text'):
                if file.suffix.lower() not in DOCUMENTS - {'.pdf'}:
                    raise ValueError('텍스트 파일을 선택해 주세요.')
                with file.open('rb') as stream:
                    value, encoding = decode_text(stream.read(4 * 1024 * 1024 + 1), query.get('encoding', ['auto'])[0])
                return self.reply({'text': value, 'encoding': encoding})
            return self.stream(file, document=file.suffix.lower() in DOCUMENTS)
        uploaded = re.fullmatch('/api/uploads/([0-9a-f]{32})/(text|content)', path)
        if uploaded:
            row, file = self.server.library_files.uploaded(uploaded[1])
            if uploaded[2] == 'text':
                if file.suffix.lower() == '.pdf':
                    raise ValueError('PDF는 문서 보기에서 열어 주세요.')
                value, encoding = decode_text(file.read_bytes(), query.get('encoding', [row['encoding']])[0])
                return self.reply({'text': value, 'encoding': encoding})
            return self.stream(file, document=True, filename=row['name'])
        if path in ('/api/works', '/api/export'):
            query = parse_qs(parsed.query).get('q', [''])[0] if path == '/api/works' else ''
            works = store.works(query)
            if path == '/api/works':
                for work in works:
                    for edition in work['editions']:
                        try:
                            info = self.server.covers.info(edition, cached_only=True)
                        except CoverUnavailable:
                            continue
                        if info:
                            work['source_info_titles'] = info['titles']
                            work['source_info_title_sources'] = info['title_sources']
                            work['source_info_tags'] = info['tags']
                            break
                self.server.titles.works(works)
                try:
                    self.server.annotations.attach(works)
                except ValueError as error:
                    annotation_warning = str(error)
                try:
                    self.server.library_files.attach(works)
                except ValueError as error:
                    files_warning = str(error)
                try:
                    details = self.server.media_details.read()
                    for work in works:
                        for edition in work['editions']:
                            edition['media_details'] = details['editions'].get(edition['id'], {})
                            edition['media_details_revision'] = details['revision']
                except ValueError as error:
                    media_warning = str(error)
            result = {'schema': 1, 'works': works}
            if path == '/api/works':
                if 'annotation_warning' in locals():
                    result['catalog_annotations_error'] = annotation_warning
                if 'files_warning' in locals():
                    result['library_files_error'] = files_warning
                if 'media_warning' in locals():
                    result['media_details_error'] = media_warning
                try:
                    result['tag_visibility'] = self.server.tag_visibility.read()
                except ValueError as error:
                    result['tag_visibility_error'] = str(error)
            if path == '/api/works' and self.server.titles.warning:
                result['translation_warning'] = self.server.titles.warning
            return self.reply(result)
        match = re.fullmatch('/api/editions/([0-9a-f]{32})', path)
        if match:
            edition = self.server.titles.edition(store.edition(match[1]))
            self.server.annotations.attach([{'editions': [edition]}])
            self.server.library_files.attach([{'editions': [edition]}])
            details = self.server.media_details.read()
            edition['media_details'] = details['editions'].get(edition['id'], {})
            edition['media_details_revision'] = details['revision']
            return self.reply(edition)
        match = re.fullmatch('/api/editions/([0-9a-f]{32})/media-details', path)
        if match:
            store.edition(match[1])
            value = self.server.media_details.read()
            return self.reply({'revision': value['revision'], 'details': value['editions'].get(match[1], {})})
        match = re.fullmatch('/api/editions/([0-9a-f]{32})/cover', path)
        if match:
            try:
                data, content_type = self.server.covers.get(store.edition(match[1]))
            except CoverUnavailable:
                return self.reply({'error': '표지를 찾을 수 없습니다.'}, 404)
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'private, max-age=86400')
            self.send_header('Vary', 'Authorization')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(data)
            return
        match = re.fullmatch('/api/editions/([0-9a-f]{32})/source-info', path)
        if match:
            edition = store.edition(match[1])
            try:
                info = self.server.covers.info(edition)
                return self.reply({'tags': info['tags'], 'titles': info['titles'], 'title_sources': info['title_sources'], 'available': True})
            except CoverUnavailable:
                return self.reply({'tags': [], 'titles': {}, 'available': False})
        match = re.fullmatch('/api/tracks/([0-9a-f]{32})/media', path)
        if match:
            track = store.track(match[1])
            return self.stream(media_path(self.server.media_root, track['relative_path']))
        match = re.fullmatch('/api/subtitles/([0-9a-f]{32})', path)
        if match:
            if any(row['id'] == match[1] for row in self.server.library_files.read()['uploads']):
                row, file = self.server.library_files.uploaded(match[1])
                if file.suffix.lower() not in ('.srt', '.vtt'):
                    raise ValueError('자막 파일이 아닙니다.')
                value, _ = decode_text(file.read_bytes(), row['encoding'])
                return self.reply({'cues': parse_subtitles(value)})
            subtitle = store.subtitle(match[1])
            file = media_path(self.server.media_root, subtitle['relative_path'], {'.srt', '.vtt'})
            return self.reply({'cues': read_subtitles(file)})
        asset = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/player.css': 'player.css', '/player.js': 'player.js', '/player-core.js': 'player-core.js', '/library-core.js': 'library-core.js', '/tag-labels.js': 'tag-labels.js', '/files-playlists.js': 'files-playlists.js', '/files-playlists.css': 'files-playlists.css', '/catalog-controls.js': 'catalog-controls.js'}.get(path)
        if not asset:
            return self.reply({'error': '찾을 수 없습니다.'}, 404)
        raw = (HERE / 'web' / asset).read_bytes()
        self.send_response(200)
        # Windows registry associations may label .js as text/plain, which nosniff blocks.
        content_types = {'index.html': 'text/html', 'app.js': 'text/javascript', 'style.css': 'text/css', 'player.css': 'text/css', 'player.js': 'text/javascript', 'player-core.js': 'text/javascript', 'library-core.js': 'text/javascript', 'tag-labels.js': 'text/javascript'}
        content_types.update({'files-playlists.js': 'text/javascript', 'files-playlists.css': 'text/css', 'catalog-controls.js': 'text/javascript'})
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
        match = re.fullmatch('/api/works/([0-9a-f]{32})/classification-tags', path)
        if match:
            if not any(work['id'] == match[1] for work in store.works()):
                raise KeyError(match[1])
            tags = self.server.tag_visibility.tags(data.get('tags'))
            allowed = {row['tag'] for row in json.loads((HERE / 'tag_vocabulary.json').read_text(encoding='utf-8'))['tags']}
            if len(tags) > 100 or any(tag not in allowed for tag in tags):
                raise ValueError('DLsite 분류 태그 목록에서 최대 100개를 선택해 주세요.')
            current = self.server.tag_visibility.read()
            try:
                return self.reply(self.server.tag_visibility.save(data.get('revision'), work_tags={**current['work_tags'], match[1]: tags}))
            except TagVisibilityConflict as error:
                return self.reply({'error': str(error)}, 409)
        if path == '/api/playlists':
            remove = data.get('remove', False)
            if type(remove) is not bool:
                raise ValueError('재생목록 동작이 올바르지 않습니다.')
            if not remove:
                self.server.library_files.validate_playlist(data.get('name'), data.get('track_ids'))
                for identifier in data['track_ids']:
                    store.track(identifier)
            try:
                return self.reply(self.server.library_files.playlist(data.get('revision'), data.get('id', ''),
                                  data.get('name'), data.get('track_ids'), remove))
            except LibraryConflict as error:
                return self.reply({'error': str(error)}, 409)
        if path == '/api/uploads':
            edition = store.edition(data['edition_id'])
            track_id = data.get('track_id', '')
            if track_id and not any(track['id'] == track_id for track in edition['tracks']):
                raise ValueError('선택한 버전의 트랙이 아닙니다.')
            original = data.get('original_path', '')
            if original:
                voice_path(self.server.media_root, original, file=True)
            try:
                return self.reply(self.server.library_files.upload(data.get('revision'), edition['id'], track_id,
                                  data['name'], data['content'], data.get('encoding', 'auto'), original), 201)
            except LibraryConflict as error:
                return self.reply({'error': str(error)}, 409)
        match = re.fullmatch('/api/editions/([0-9a-f]{32})/media-details', path)
        if match:
            edition = store.edition(match[1])
            details = self.server.media_details.validate(data.get('details'))
            if edition['profile']['media_type'] != 'video' and details['video_subtitles'] not in ('unknown', 'none'):
                raise ValueError('영상 자막은 영상 판본에서만 확인할 수 있습니다.')
            if any(t['subtitles'] for t in edition['tracks']) and details['subtitle_files'] == 'none':
                raise ValueError('연결된 자막 파일이 있습니다. 자막 파일 없음으로 저장할 수 없습니다.')
            try:
                value = self.server.media_details.save(match[1], data.get('revision'), details)
                return self.reply({'revision': value['revision'], 'details': value['editions'][match[1]]})
            except MediaDetailsConflict as error:
                return self.reply({'error': str(error)}, 409)
        if path == '/api/tag-visibility':
            try:
                fields = {'hidden_rplay_tags', 'hidden_dlsite_tags', 'hidden_tags', 'favorite_tags', 'tag_aliases', 'tag_names'}
                updates = {key: data[key] for key in fields if key in data}
                return self.reply(self.server.tag_visibility.save(data.get('revision'), **updates))
            except TagVisibilityConflict as error:
                return self.reply({'error': str(error)}, 409)
        match = re.fullmatch('/api/(works|tracks)/([0-9a-f]{32})/title-translation', path)
        if match:
            kind, identifier = ('work' if match[1] == 'works' else 'track'), match[2]
            if kind == 'track':
                original = store.track(identifier)['title']
            else:
                work = next((work for work in store.works() if work['id'] == identifier), None)
                if work is None:
                    raise KeyError(identifier)
                original = work['title']
                for edition in work['editions']:
                    try:
                        info = self.server.covers.info(edition, cached_only=True)
                    except CoverUnavailable:
                        continue
                    if info:
                        original = info['titles'].get('ja') or original
                        break
            if data.get('original') != original:
                raise ValueError('원문 정보가 바뀌었습니다. 새로고침 후 다시 편집하세요.')
            return self.reply(self.server.titles.save(kind, identifier, original, data.get('text'),
                              data.get('revision'), data.get('reviewed', False), data.get('flagged', False)))
        match = re.fullmatch('/api/editions/([0-9a-f]{32})/cover/refresh', path)
        if match:
            edition = store.edition(match[1])
            try:
                self.server.covers.get(edition, retry=True)
                return self.reply({'available': True})
            except CoverUnavailable:
                return self.reply({'available': False})
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

    def stream(self, path, document=False, filename=None):
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
            content_type = ('application/pdf' if path.suffix.lower() == '.pdf' else 'text/plain; charset=utf-8') if document else mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            self.send_header('Content-Type', content_type)
            if document:
                self.send_header('Content-Disposition', "inline; filename*=UTF-8''" + quote(filename or path.name, safe=''))
                self.send_header('Content-Security-Policy', "sandbox; default-src 'none'; frame-ancestors 'self'")
                self.send_header('Referrer-Policy', 'no-referrer')
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


def make_server(catalog, media_root, port=43130, password='', bind='127.0.0.1', allowed_hosts=()):
    if bind not in ('127.0.0.1', '0.0.0.0'):
        raise ValueError('지원하지 않는 바인딩 주소입니다.')
    server = LocalServer((bind, port), Handler)
    server.catalog = catalog
    server.media_root = Path(media_root).resolve()
    server.password = password
    server.allowed_hosts = frozenset(host.strip().lower() for host in allowed_hosts if host.strip())
    server.covers = RplayCovers(catalog.path.parent / 'covers', media_root=server.media_root)
    server.titles = TitleMetadata(catalog.path.parent / 'title-translations.json')
    server.tag_visibility = TagVisibility(catalog.path.parent / 'tag-visibility.json')
    server.media_details = MediaDetails(catalog.path.parent / 'media-details.json')
    server.library_files = LibraryFiles(catalog.path.parent)
    server.annotations = CatalogAnnotations(catalog.path.parent / 'catalog-annotations.json')
    server.daemon_threads = True
    return server


if __name__ == '__main__':
    # No .env, comic DB, LANraragi API, downloader, NAS or Redis configuration is loaded.
    server = make_server(Catalog(HERE / 'data' / 'audio.sqlite3'), HERE / 'media',
                         password=os.environ.get('AUDIO_STUDIO_PASSWORD', ''),
                         bind=os.environ.get('AUDIO_STUDIO_BIND', '127.0.0.1'),
                         allowed_hosts=os.environ.get('AUDIO_STUDIO_ALLOWED_HOSTS', '').split(','))
    print('Audio Studio: http://127.0.0.1:43130 (Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
