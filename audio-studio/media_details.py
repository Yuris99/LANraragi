"""Manually verified edition facts, separate from catalog originals and media."""
import json
import os
import re
import tempfile
import threading
from pathlib import Path

FIELDS = {'subtitle_files': ('unknown', 'none', 'present'),
          'video_subtitles': ('unknown', 'none', 'soft', 'burned', 'both'),
          'script': ('unknown', 'none', 'present'),
          'dubbing': ('unknown', 'none', 'present'),
          'audio_language': ('', 'ja', 'ko', 'en', 'other')}


class MediaDetailsConflict(ValueError):
    pass


class MediaDetails:
    def __init__(self, file):
        self.file = Path(file)
        self.lock = threading.Lock()

    @staticmethod
    def validate(value):
        if not isinstance(value, dict) or set(value) != set(FIELDS) | {'note'}:
            raise ValueError('자막·대본·더빙 확인 항목이 올바르지 않습니다.')
        if any(not isinstance(value[k], str) or value[k] not in allowed for k, allowed in FIELDS.items()):
            raise ValueError('지원하지 않는 자막·대본·더빙 확인 값입니다.')
        note = value['note']
        if not isinstance(note, str) or len(note) > 1000 or any(ord(c) < 32 and c not in '\n\t' for c in note):
            raise ValueError('확인 근거는 1000자 이하의 텍스트여야 합니다.')
        return {k: value[k] for k in FIELDS} | {'note': note.strip()}

    def _read(self):
        try:
            if self.file.is_symlink() or self.file.parent.is_symlink():
                raise ValueError()
            if not self.file.exists():
                return {'schema': 1, 'revision': 0, 'editions': {}}
            if self.file.stat().st_size > 2 * 1024 * 1024:
                raise ValueError()
            value = json.loads(self.file.read_text(encoding='utf-8'))
            if (not isinstance(value, dict) or value.get('schema') != 1
                    or type(value.get('revision')) is not int or value['revision'] < 0
                    or not isinstance(value.get('editions'), dict) or len(value['editions']) > 10000):
                raise ValueError()
            editions = {}
            for key, row in value['editions'].items():
                if not re.fullmatch('[0-9a-f]{32}', key):
                    raise ValueError()
                editions[key] = self.validate(row)
            return {'schema': 1, 'revision': value['revision'], 'editions': editions}
        except (ValueError, TypeError, OSError):
            raise ValueError('자막·대본·더빙 확인 기록을 읽지 못했습니다. 기존 파일을 보존하고 저장을 중지합니다.') from None

    def read(self):
        with self.lock:
            return self._read()

    def save(self, edition_id, revision, details):
        if not re.fullmatch('[0-9a-f]{32}', edition_id) or type(revision) is not int or revision < 0:
            raise ValueError('판본 ID와 최신 revision이 필요합니다.')
        details = self.validate(details)
        with self.lock:
            old = self._read()
            if revision != old['revision']:
                raise MediaDetailsConflict('다른 기기에서 확인 기록이 바뀌었습니다. 초안을 보관한 뒤 다시 열어 주세요.')
            if old['editions'].get(edition_id) == details:
                return old
            value = {'schema': 1, 'revision': revision + 1, 'editions': {**old['editions'], edition_id: details}}
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if len(raw) > 2 * 1024 * 1024 or len(value['editions']) > 10000:
                raise ValueError('확인 기록의 저장 한도를 초과했습니다.')
            self.file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.file.parent, prefix='media-details-', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            try:
                temporary.chmod(0o600); temporary.replace(self.file)
            finally:
                temporary.unlink(missing_ok=True)
            return value
