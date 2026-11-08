"""Display-only Korean title cache. Original catalog titles and file paths stay intact."""
import hashlib
import json
import re
import tempfile
import threading
import time
import unicodedata
from pathlib import Path
from translation_quality import ISSUE_LABELS


def title_key(original):
    return hashlib.sha256(unicodedata.normalize('NFC', original).strip().encode('utf-8')).hexdigest()


class TitleMetadata:
    def __init__(self, file):
        self.file = Path(file)
        self.lock = threading.Lock()
        self.signature = None
        self.entries = {}
        self.override_file = self.file.with_name('title-overrides.json')
        self.override_lock = threading.Lock()
        self.warning = ''

    def read(self):
        with self.lock:
            try:
                stat = self.file.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if signature == self.signature:
                    return self.entries
                if self.file.is_symlink() or stat.st_size > 8 * 1024 * 1024:
                    return {}
                value = json.loads(self.file.read_text(encoding='utf-8'))
                if value.get('schema') != 1 or value.get('language') != 'ko' or not isinstance(value.get('entries'), dict) or len(value['entries']) > 20000:
                    return {}
                entries = {}
                for key, row in value['entries'].items():
                    if (isinstance(row, dict) and isinstance(row.get('original'), str) and isinstance(row.get('ko'), str)
                            and 0 < len(row['original']) <= 4096 and len(row['ko'].strip()) <= 4096
                            and isinstance(row.get('issues', []), list) and all(isinstance(issue, str) for issue in row.get('issues', []))
                            and row.get('kind') == 'machine' and key == title_key(row['original'])):
                        entries[key] = row
                self.signature, self.entries = signature, entries
                return entries
            except (OSError, ValueError, AttributeError):
                return {}

    def translation(self, original, entries):
        if not isinstance(original, str):
            return None
        return entries.get(title_key(original))

    def overrides(self, strict=False):
        try:
            if not self.override_file.exists():
                self.warning = ''
                return {}
            if self.override_file.is_symlink() or self.override_file.stat().st_size > 8 * 1024 * 1024:
                raise ValueError()
            value = json.loads(self.override_file.read_text(encoding='utf-8'))
            if value.get('schema') != 1 or not isinstance(value.get('entries'), dict):
                raise ValueError()
            for key, row in value['entries'].items():
                if (not re.fullmatch(r'(work|track):[0-9a-f]{32}', key) or not isinstance(row, dict)
                        or not isinstance(row.get('original'), str) or not 0 < len(row['original']) <= 4096 or not isinstance(row.get('ko'), str)
                        or not 0 < len(row['ko'].strip()) <= 4096 or type(row.get('revision')) is not int
                        or row['revision'] < 1 or type(row.get('reviewed')) is not bool or type(row.get('flagged')) is not bool):
                    raise ValueError()
            self.warning = ''
            return value['entries']
        except (OSError, ValueError, AttributeError, TypeError):
            self.warning = '직접 입력한 번역을 읽지 못했습니다. 기존 저장 내용을 확인해 주세요.'
            if strict:
                raise ValueError(self.warning) from None
            return {}

    def info(self, kind, identifier, original, official='', entries=None, overrides=None):
        entries = self.read() if entries is None else entries
        overrides = self.overrides() if overrides is None else overrides
        manual = overrides.get(kind + ':' + identifier)
        machine = self.translation(original, entries)
        issues = []
        if manual:
            text, source = manual['ko'], 'manual'
            if not manual['reviewed'] and machine:
                issues.extend(issue for issue in machine.get('issues', []) if issue in ISSUE_LABELS)
            if manual['flagged']:
                issues.append('user_flagged')
            if title_key(manual['original']) != title_key(original):
                issues.append('source_changed')
            reviewed, revision = manual['reviewed'], manual['revision']
        elif official:
            text, source, reviewed, revision = official, 'official', True, 0
        elif machine:
            text, source, reviewed, revision = machine['ko'], 'machine', False, 0
            issues = [issue for issue in machine.get('issues', []) if issue in ISSUE_LABELS]
        else:
            text, source, reviewed, revision = ('', 'missing', False, 0) if re.search(r'[\u3040-\u30ff\u3400-\u9fff]', original) else (original, 'original', False, 0)
        return {'original': original, 'text': text, 'kind': source, 'revision': revision,
                'reviewed': reviewed, 'flagged': bool(manual and manual['flagged']),
                'status': 'needs_review' if issues else 'reviewed' if reviewed else 'unreviewed',
                'issues': [{'code': issue, 'message': ISSUE_LABELS[issue]} for issue in issues],
                'candidate': str(machine.get('candidate') or machine.get('raw_response', '')) if machine else '',
                'response_scope': 'batch' if machine and not machine.get('candidate') and machine.get('raw_response') else 'item',
                'engine': str(machine.get('engine', '')) if machine else ''}

    def save(self, kind, identifier, original, ko, revision, reviewed=False, flagged=False):
        if (not re.fullmatch(r'(work|track):[0-9a-f]{32}', kind + ':' + identifier)
                or not isinstance(original, str) or not 0 < len(original) <= 4096
                or not isinstance(ko, str) or not 0 < len(ko.strip()) <= 4096
                or type(revision) is not int or revision < 0 or type(reviewed) is not bool or type(flagged) is not bool):
            raise ValueError('번역문은 1~4096자로 입력하고 올바른 검수 상태를 선택하세요.')
        with self.override_lock:
            rows = self.overrides(strict=True)
            key = kind + ':' + identifier
            previous = rows.get(key)
            if revision != (previous['revision'] if previous else 0):
                raise ValueError('다른 화면에서 번역이 변경됐습니다. 새로고침 후 다시 편집하세요.')
            history = ((previous.get('history', []) + [{k: v for k, v in previous.items() if k != 'history'}])[-10:] if previous else [])
            rows[key] = {'original': original, 'ko': ko.strip(), 'revision': revision + 1,
                         'reviewed': reviewed, 'flagged': flagged, 'updated': time.time(), 'history': history}
            raw = json.dumps({'schema': 1, 'entries': rows}, ensure_ascii=False).encode('utf-8')
            if len(raw) > 8 * 1024 * 1024 or self.override_file.parent.is_symlink():
                raise ValueError('번역 저장 공간을 확인해 주세요.')
            self.override_file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.override_file.parent, suffix='.tmp', delete=False) as output:
                output.write(raw)
                temporary = Path(output.name)
            try:
                temporary.replace(self.override_file)
            finally:
                temporary.unlink(missing_ok=True)
            return self.info(kind, identifier, original, overrides=rows)

    def edition(self, edition, entries=None, overrides=None):
        entries = self.read() if entries is None else entries
        overrides = self.overrides() if overrides is None else overrides
        for track in edition['tracks']:
            track.pop('title_ko', None)
            track.pop('title_translation_kind', None)
            info = self.info('track', track.get('id', ''), track['title'], entries=entries, overrides=overrides)
            track['title_translation'] = info
            if info['text'] and info['kind'] != 'original':
                track['title_ko'] = info['text']
                track['title_translation_kind'] = info['kind']
        return edition

    def works(self, works):
        entries = self.read()
        overrides = self.overrides()
        for work in works:
            work.pop('title_ko_auto', None)
            work.pop('title_ko_manual', None)
            titles = work.get('source_info_titles') or {}
            info = self.info('work', work.get('id', ''), titles.get('ja') or work['title'], titles.get('ko', ''), entries, overrides)
            work['title_translation'] = info
            if info['kind'] == 'manual':
                work['title_ko_manual'] = info['text']
            elif info['kind'] == 'machine' and info['text']:
                work['title_ko_auto'] = info['text']
            for edition in work['editions']:
                self.edition(edition, entries, overrides)
        return works
