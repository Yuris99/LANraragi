"""Server-wide display preferences; catalog/source originals are never changed."""
import json
import os
import tempfile
import threading
import unicodedata
import re
from pathlib import Path


class TagVisibilityConflict(ValueError):
    pass


UNSET = object()


class TagVisibility:
    def __init__(self, file):
        self.file = Path(file)
        self.lock = threading.Lock()

    @staticmethod
    def tags(values):
        if not isinstance(values, list) or len(values) > 2000 or any(
                not isinstance(v, str) or not 1 <= len(v.strip()) <= 300
                or any(ord(c) < 32 for c in v) for v in values):
            raise ValueError('숨길 태그는 최대 2000개, 각 1–300자 문자열이어야 합니다.')
        return list(dict.fromkeys(unicodedata.normalize('NFC', v.strip()) for v in values))

    @classmethod
    def aliases(cls, value):
        if not isinstance(value, dict) or len(value) > 2000:
            raise ValueError('태그 병합 정보 형식이 올바르지 않습니다.')
        result = {}
        for key, target in value.items():
            key = cls.tags([key])[0]
            target = cls.tags([target])[0]
            if key in result and result[key] != target:
                raise ValueError('중복된 태그 병합 키입니다.')
            result[key] = target
        flattened = {}
        for key in result:
            seen = {key}; target = result[key]
            while target in result:
                if target in seen:
                    raise ValueError('서로를 가리키는 태그 병합은 저장할 수 없습니다.')
                seen.add(target); target = result[target]
            if target == key:
                raise ValueError('태그를 자기 자신으로 병합할 수 없습니다.')
            flattened[key] = target
        return flattened

    @classmethod
    def names(cls, value):
        if not isinstance(value, dict) or len(value) > 2000:
            raise ValueError('태그 이름 정보 형식이 올바르지 않습니다.')
        result = {}
        for key, labels in value.items():
            key = cls.tags([key])[0]
            if not isinstance(labels, dict) or set(labels) - {'ko', 'original'}:
                raise ValueError('태그 이름은 한국어·원문 표시 이름만 저장할 수 있습니다.')
            row = {}
            for language, text in labels.items():
                if not isinstance(text, str) or len(text) > 300 or any(ord(c) < 32 for c in text):
                    raise ValueError('태그 이름은 300자 이하의 한 줄 문자열이어야 합니다.')
                if text.strip():
                    row[language] = unicodedata.normalize('NFC', text.strip())
            if row:
                if key in result and result[key] != row:
                    raise ValueError('중복된 태그 이름 키입니다.')
                result[key] = row
        return result

    @classmethod
    def work_tags(cls, value):
        if not isinstance(value, dict) or len(value) > 10000:
            raise ValueError('작품 분류 태그 형식이 올바르지 않습니다.')
        result = {}
        for key, tags in value.items():
            if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{32}', key) or not isinstance(tags, list) or len(tags) > 100:
                raise ValueError('작품별 분류 태그는 최대 100개입니다.')
            result[key] = cls.tags(tags)
        return result

    @classmethod
    def validate(cls, value):
        return {'hidden_rplay_tags': cls.tags(value.get('hidden_rplay_tags', [])),
                'hidden_dlsite_tags': cls.tags(value.get('hidden_dlsite_tags', [])),
                'hidden_tags': cls.tags(value.get('hidden_tags', [])),
                'favorite_tags': cls.tags(value.get('favorite_tags', [])),
                'tag_aliases': cls.aliases(value.get('tag_aliases', {})),
                'tag_names': cls.names(value.get('tag_names', {})),
                'work_tags': cls.work_tags(value.get('work_tags', {}))}

    def _read(self):
        try:
            if self.file.is_symlink() or self.file.parent.is_symlink():
                raise ValueError()
            if not self.file.exists():
                return {'schema': 1, 'revision': 0, **self.validate({})}
            if self.file.stat().st_size > 1024 * 1024:
                raise ValueError()
            value = json.loads(self.file.read_text(encoding='utf-8'))
            if (not isinstance(value, dict) or value.get('schema') != 1
                    or type(value.get('revision')) is not int or value['revision'] < 0
                    or 'hidden_rplay_tags' not in value):
                raise ValueError()
            return {'schema': 1, 'revision': value['revision'], **self.validate(value)}
        except (OSError, ValueError, TypeError):
            raise ValueError('태그 숨김 설정을 읽지 못했습니다. 기존 파일을 보존하고 관리자에게 확인해 주세요.') from None

    def read(self):
        with self.lock:
            return self._read()

    def save(self, revision, hidden_rplay_tags=UNSET, hidden_dlsite_tags=UNSET, **updates):
        if type(revision) is not int or revision < 0:
            raise ValueError('현재 태그 설정의 revision이 필요합니다.')
        if set(updates) - {'hidden_tags', 'favorite_tags', 'tag_aliases', 'tag_names', 'work_tags'}:
            raise ValueError('허용되지 않은 태그 설정입니다.')
        if hidden_rplay_tags is not UNSET:
            updates['hidden_rplay_tags'] = hidden_rplay_tags
        if hidden_dlsite_tags is not UNSET:
            updates['hidden_dlsite_tags'] = hidden_dlsite_tags
        with self.lock:
            old = self._read()
            if revision != old['revision']:
                raise TagVisibilityConflict('다른 기기에서 태그 설정이 바뀌었습니다. 닫았다 다시 열어 최신 설정에서 선택해 주세요.')
            fields = self.validate({**old, **updates})
            if all(old[key] == value for key, value in fields.items()):
                return old
            value = {'schema': 1, 'revision': revision + 1, **fields}
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if len(raw) > 1024 * 1024:
                raise ValueError('태그 숨김 설정은 1 MiB 이하여야 합니다.')
            self.file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.file.parent, prefix='tag-visibility-', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            try:
                temporary.chmod(0o600)
                temporary.replace(self.file)
            finally:
                temporary.unlink(missing_ok=True)
            return value
