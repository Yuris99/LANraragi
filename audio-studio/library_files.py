"""Read-only Voice browsing and separate, revisioned user uploads/playlists."""
import base64
import binascii
import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from pathlib import Path, PureWindowsPath

from catalog import text
from subtitles import parse_subtitles

DOCUMENTS = {'.txt', '.md', '.srt', '.vtt', '.pdf'}
MEDIA = {'.mp3', '.m4a', '.aac', '.ogg', '.opus', '.wav', '.flac', '.mp4', '.webm'}
MAX_UPLOAD = 12 * 1024 * 1024
ID = re.compile(r'[0-9a-f]{32}')


def voice_path(root, relative, file=False):
    if not isinstance(relative, str) or len(relative) > 2000:
        raise ValueError('폴더 상대 경로가 필요합니다.')
    parts = relative.split('/') if relative else []
    if (PureWindowsPath(relative).drive or relative.startswith('/') or '\\' in relative or ':' in relative
            or any(not p or p in ('.', '..') or p.startswith(('.', '@')) or any(ord(c) < 32 for c in p) for p in parts)):
        raise ValueError('미디어 폴더 안의 일반 경로만 열 수 있습니다.')
    root = Path(root).resolve()
    candidate = root
    for part in parts:
        candidate = candidate / part
        if candidate.is_symlink() or getattr(candidate, 'is_junction', lambda: False)():
            raise ValueError('연결 경로는 탐색하지 않습니다.')
    if not candidate.resolve().is_relative_to(root):
        raise ValueError('미디어 폴더 밖의 파일은 열 수 없습니다.')
    if file:
        if not candidate.is_file() or candidate.suffix.lower() not in DOCUMENTS | MEDIA:
            raise ValueError('지원하는 문서·미디어 파일이 아닙니다.')
    elif not candidate.is_dir():
        raise ValueError('폴더를 찾을 수 없습니다.')
    return candidate


def browse(root, relative='', offset=0):
    if type(offset) is not int or not 0 <= offset <= 100000:
        raise ValueError('목록 위치가 올바르지 않습니다.')
    folder = voice_path(root, relative)
    rows = []
    with os.scandir(folder) as entries:
        for entry in entries:
            if entry.name.startswith(('.', '@')) or entry.is_symlink():
                continue
            path = Path(entry.path)
            if getattr(path, 'is_junction', lambda: False)():
                continue
            is_dir = entry.is_dir(follow_symlinks=False)
            if not is_dir and (path.suffix.lower() not in DOCUMENTS | MEDIA or not entry.is_file(follow_symlinks=False)):
                continue
            try:
                stat = entry.stat(follow_symlinks=False)
                rows.append({'name': entry.name, 'path': (relative + '/' if relative else '') + entry.name,
                             'kind': 'folder' if is_dir else 'document' if path.suffix.lower() in DOCUMENTS else 'media',
                             'bytes': 0 if is_dir else stat.st_size})
            except OSError:
                continue
            if len(rows) > 100000:
                raise ValueError('폴더 항목이 너무 많습니다. 더 작은 폴더를 선택해 주세요.')
    rows.sort(key=lambda row: (row['kind'] != 'folder', row['name'].casefold()))
    return {'path': relative, 'items': rows[offset:offset + 300], 'next': offset + 300 if len(rows) > offset + 300 else None}


def decode_text(raw, encoding='auto'):
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('텍스트 열람은 4 MiB까지 지원합니다. 파일로 내려받아 주세요.')
    if encoding not in ('auto', 'utf-8-sig', 'utf-16', 'cp932', 'cp949'):
        raise ValueError('지원하지 않는 문자 인코딩입니다.')
    choices = (['utf-16'] if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ['utf-8-sig', 'cp932', 'cp949']) if encoding == 'auto' else [encoding]
    for codec in choices:
        try:
            value = raw.decode(codec)
            if '\x00' not in value:
                return value, codec
        except UnicodeError:
            continue
    raise ValueError('글자를 읽지 못했습니다. 문자 인코딩을 바꿔 주세요.')


class LibraryConflict(ValueError):
    pass


class LibraryFiles:
    def __init__(self, root):
        self.root = Path(root)
        self.file = self.root / 'library-files.json'
        self.uploads = self.root / 'uploads'
        self.lock = threading.Lock()

    def _read(self):
        try:
            if self.file.is_symlink() or self.root.is_symlink() or self.uploads.is_symlink():
                raise ValueError()
            if not self.file.exists():
                return {'schema': 1, 'revision': 0, 'playlists': [], 'uploads': []}
            if self.file.stat().st_size > 4 * 1024 * 1024:
                raise ValueError()
            value = json.loads(self.file.read_text(encoding='utf-8'))
            if (value.get('schema') != 1 or type(value.get('revision')) is not int or value['revision'] < 0
                    or not isinstance(value.get('playlists'), list) or not isinstance(value.get('uploads'), list)):
                raise ValueError()
            if len(value['playlists']) > 1000 or len(value['uploads']) > 10000:
                raise ValueError()
            identifiers = set()
            for row in value['playlists'] + value['uploads']:
                if not isinstance(row, dict) or not ID.fullmatch(row.get('id', '')) or row['id'] in identifiers:
                    raise ValueError()
                identifiers.add(row['id'])
                if row in value['playlists']:
                    self.validate_playlist(row['name'], row['track_ids'])
                else:
                    self.filename(row['name'])
                    if not ID.fullmatch(row['edition_id']) or row['track_id'] and not ID.fullmatch(row['track_id']):
                        raise ValueError()
                    if (row['encoding'] not in ('binary', 'utf-8-sig', 'utf-16', 'cp932', 'cp949')
                            or type(row['bytes']) is not int or not 1 <= row['bytes'] <= MAX_UPLOAD
                            or not re.fullmatch('[0-9a-f]{64}', row['sha256'])):
                        raise ValueError()
            return value
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise ValueError('파일·재생목록 기록을 읽지 못했습니다. 기존 기록을 보존하고 저장을 중지합니다.') from None

    def read(self):
        with self.lock:
            return self._read()

    def _current(self, revision):
        value = self._read()
        if type(revision) is not int or revision != value['revision']:
            raise LibraryConflict('다른 창에서 파일·재생목록이 바뀌었습니다. 초안을 보관한 채 다시 불러와 주세요.')
        return value

    def _write(self, value):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError('파일·재생목록 기록의 저장 한도를 넘었습니다.')
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=self.root, prefix='library-files-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        try:
            temporary.chmod(0o600); temporary.replace(self.file)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def validate_playlist(name, track_ids):
        name = text(name, '재생목록 이름', 200)
        if (not isinstance(track_ids, list) or len(track_ids) > 5000 or len(set(track_ids)) != len(track_ids)
                or any(not isinstance(i, str) or not ID.fullmatch(i) for i in track_ids)):
            raise ValueError('재생목록은 서로 다른 트랙 ID 최대 5000개까지 저장할 수 있습니다.')
        return name

    def playlist(self, revision, identifier, name, track_ids, remove=False):
        if not isinstance(identifier, str) or identifier and not ID.fullmatch(identifier):
            raise ValueError('재생목록 ID가 올바르지 않습니다.')
        if not remove:
            name = self.validate_playlist(name, track_ids)
        with self.lock:
            value = self._current(revision)
            if identifier and not any(row['id'] == identifier for row in value['playlists']):
                raise KeyError(identifier)
            if not identifier and len(value['playlists']) >= 1000:
                raise ValueError('재생목록 저장 한도는 1000개입니다.')
            if remove and not identifier:
                raise ValueError('지울 재생목록을 선택해 주세요.')
            rows = [row for row in value['playlists'] if row['id'] != identifier]
            if not remove:
                rows.append({'id': identifier or uuid.uuid4().hex, 'name': name, 'track_ids': track_ids})
            value['playlists'] = rows; value['revision'] += 1
            self._write(value)
            return value

    @staticmethod
    def filename(name):
        name = text(name, '업로드 파일 이름', 240)
        if (Path(name).suffix.lower() not in DOCUMENTS or any(c in name for c in '/\\:')
                or name.startswith('.') or any(ord(c) < 32 for c in name)):
            raise ValueError('TXT·MD·PDF·SRT·VTT 파일만 업로드할 수 있습니다.')
        return name

    def upload(self, revision, edition_id, track_id, name, encoded, encoding='auto', original_path=''):
        name = self.filename(name)
        if not ID.fullmatch(edition_id) or track_id and not ID.fullmatch(track_id):
            raise ValueError('연결할 버전·트랙을 선택해 주세요.')
        if not isinstance(encoded, str) or len(encoded) > (MAX_UPLOAD * 4 // 3 + 4):
            raise ValueError('파일 하나당 12 MiB까지 업로드할 수 있습니다.')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError('파일 전송 형식이 올바르지 않습니다.') from None
        if not 1 <= len(raw) <= MAX_UPLOAD:
            raise ValueError('비어 있지 않은 12 MiB 이하 파일이 필요합니다.')
        suffix = Path(name).suffix.lower()
        if suffix == '.pdf':
            if not raw.startswith(b'%PDF-'):
                raise ValueError('PDF 파일 형식이 올바르지 않습니다.')
            encoding = 'binary'
        else:
            decoded, encoding = decode_text(raw, encoding)
            if suffix in ('.srt', '.vtt'):
                parse_subtitles(decoded)
                if not track_id:
                    raise ValueError('자막을 사용할 트랙을 직접 선택해 주세요.')
        if not isinstance(original_path, str) or len(original_path) > 2000:
            raise ValueError('원본 연결 경로가 올바르지 않습니다.')
        with self.lock:
            value = self._current(revision)
            if len(value['uploads']) >= 10000:
                raise ValueError('업로드 저장 한도는 10000개입니다.')
            row = {'id': uuid.uuid4().hex, 'edition_id': edition_id, 'track_id': track_id,
                   'name': name, 'encoding': encoding, 'original_path': original_path,
                   'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            self.uploads.mkdir(parents=True, exist_ok=True)
            target = self.uploads / (row['id'] + suffix)
            try:
                with target.open('xb') as stream:
                    stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                target.chmod(0o600)
                value['uploads'].append(row); value['revision'] += 1
                self._write(value)
            except Exception:
                target.unlink(missing_ok=True)
                raise
            return value

    def uploaded(self, identifier):
        row = next((r for r in self.read()['uploads'] if r['id'] == identifier), None)
        if row is None:
            raise KeyError(identifier)
        path = self.uploads / (identifier + Path(row['name']).suffix.lower())
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(self.uploads.resolve()):
            raise ValueError('업로드 파일을 찾을 수 없습니다.')
        return row, path

    def attach(self, works):
        uploads = self.read()['uploads']
        by_track = {}
        for row in uploads:
            if Path(row['name']).suffix.lower() in ('.srt', '.vtt'):
                by_track.setdefault(row['track_id'], []).append(row)
        for work in works:
            for edition in work['editions']:
                for track in edition['tracks']:
                    for row in by_track.get(track['id'], []):
                        track['subtitles'].append({'id': row['id'], 'track_id': track['id'], 'label': row['name'],
                                                   'language': 'und', 'origin': 'upload', 'sync_verified': False})
