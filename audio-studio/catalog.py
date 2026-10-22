"""Audio Studio catalog. Never opens the comic catalog or upstream Redis."""
import contextlib
import json
import math
import re
import sqlite3
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

APP_ID = 0x41535431
KINDS = ('comic', 'translation', 'voice_comic', 'audio')


def text(value, name, maximum=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f'{name}: 1–{maximum}자 문자열이 필요합니다.')
    return value.strip()


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('시간은 0 이상의 유한한 숫자여야 합니다.')
    return value


class Catalog:
    def __init__(self, path):
        self.path = Path(path).resolve()
        # Inspect existing files read-only BEFORE any schema/journal modification.
        if self.path.exists():
            with contextlib.closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
                if db.execute('PRAGMA application_id').fetchone()[0] != APP_ID:
                    raise ValueError('Audio Studio 전용 DB가 아닙니다. 기존 DB를 열지 않습니다.')
                if db.execute('PRAGMA user_version').fetchone()[0] != 1:
                    raise ValueError('지원하지 않는 DB 버전입니다.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                PRAGMA application_id=1095980081;
                PRAGMA user_version=1;
                CREATE TABLE IF NOT EXISTS works (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS editions (
                    id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES works(id),
                    title TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN
                    ('comic','translation','voice_comic','audio')),
                    language TEXT NOT NULL, credits TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, edition_id TEXT NOT NULL REFERENCES editions(id),
                    provider TEXT NOT NULL, external_id TEXT NOT NULL,
                    UNIQUE(provider, external_id));
                CREATE TABLE IF NOT EXISTS source_snapshots (
                    id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
                    submitted_url TEXT NOT NULL, raw_metadata TEXT NOT NULL,
                    recorded REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS tracks (
                    id TEXT PRIMARY KEY, edition_id TEXT NOT NULL REFERENCES editions(id),
                    title TEXT NOT NULL, relative_path TEXT NOT NULL, duration REAL NOT NULL,
                    position INTEGER NOT NULL CHECK(position >= 1), resume REAL NOT NULL DEFAULT 0,
                    UNIQUE(edition_id, position), UNIQUE(edition_id, relative_path));
                CREATE INDEX IF NOT EXISTS editions_work ON editions(work_id);
                CREATE INDEX IF NOT EXISTS sources_edition ON sources(edition_id);
                CREATE INDEX IF NOT EXISTS snapshots_source ON source_snapshots(source_id);
                CREATE INDEX IF NOT EXISTS tracks_edition ON tracks(edition_id);
                CREATE TABLE IF NOT EXISTS work_codes (
                    work_id TEXT NOT NULL REFERENCES works(id), provider TEXT NOT NULL,
                    code TEXT NOT NULL, PRIMARY KEY(provider,code));
                CREATE TABLE IF NOT EXISTS edition_profiles (
                    edition_id TEXT PRIMARY KEY REFERENCES editions(id),
                    media_type TEXT NOT NULL, translation TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS subtitles (
                    id TEXT PRIMARY KEY, track_id TEXT NOT NULL REFERENCES tracks(id),
                    relative_path TEXT NOT NULL, language TEXT NOT NULL,
                    label TEXT NOT NULL, UNIQUE(track_id,relative_path));
            ''')

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def require(db, table, item_id):
        # Table names are code constants, never request data.
        row = db.execute(f'SELECT * FROM {table} WHERE id=?', (item_id,)).fetchone()
        if row is None:
            raise KeyError('원작·판본·트랙을 찾을 수 없습니다.')
        return dict(row)

    def create_work(self, title, rj_code=''):
        item = dict(id=uuid.uuid4().hex, title=text(title, '원작 제목'), created=time.time())
        with self.db() as db:
            db.execute('INSERT INTO works VALUES(:id,:title,:created)', item)
            if rj_code:
                self._add_code(db, item['id'], rj_code)
        return item

    @staticmethod
    def _add_code(db, work_id, code):
        # A manually confirmed product grouping, never an inferred source merge.
        if not isinstance(code, str) or not re.fullmatch(r'RJ[0-9]{6,12}', code):
            raise ValueError('RJ와 6~12자리 숫자로 된 코드를 입력하세요.')
        old = db.execute('SELECT work_id FROM work_codes WHERE provider=? AND code=?', ('dlsite', code)).fetchone()
        if old and old['work_id'] != work_id:
            raise ValueError('이미 다른 원작에 등록된 RJ 코드입니다. 자동 병합하지 않습니다.')
        db.execute('INSERT OR IGNORE INTO work_codes VALUES(?,?,?)', (work_id, 'dlsite', code))

    def add_code(self, work_id, code):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.require(db, 'works', work_id)
            self._add_code(db, work_id, code)
        return {'work_id': work_id, 'provider': 'dlsite', 'code': code}

    def set_profile(self, edition_id, media_type, translation):
        if media_type not in ('audio', 'video') or translation not in ('none', 'subtitles', 'embedded'):
            raise ValueError('지원하지 않는 미디어·번역 상태입니다.')
        if translation == 'embedded' and media_type != 'video':
            raise ValueError('자막이 합성된 영상은 영상 판본으로 지정하세요.')
        with self.db() as db:
            self.require(db, 'editions', edition_id)
            db.execute('INSERT INTO edition_profiles VALUES(?,?,?) ON CONFLICT(edition_id) DO UPDATE SET media_type=excluded.media_type,translation=excluded.translation',
                       (edition_id, media_type, translation))
        return self.edition(edition_id)

    def create_edition(self, work_id, title, kind, language='', credits=None):
        if kind not in KINDS:
            raise ValueError('지원하지 않는 판본 유형입니다.')
        if not isinstance(language, str) or len(language) > 100:
            raise ValueError('언어 형식이 잘못되었습니다.')
        if credits is None:
            credits = {}
        if not isinstance(credits, dict):
            raise ValueError('제작진 정보는 JSON 객체여야 합니다.')
        encoded = json.dumps(credits, ensure_ascii=False, allow_nan=False)
        item = dict(id=uuid.uuid4().hex, work_id=work_id, title=text(title, '판본 제목'),
                    kind=kind, language=language, credits=encoded, created=time.time())
        with self.db() as db:
            self.require(db, 'works', work_id)
            db.execute('INSERT INTO editions VALUES(:id,:work_id,:title,:kind,:language,:credits,:created)', item)
        return self.edition(item['id'])

    def add_source(self, edition_id, provider, external_id, url, raw_metadata):
        provider = text(provider, '출처', 80)
        if not re.fullmatch('[a-z0-9][a-z0-9._-]*', provider):
            raise ValueError('출처는 소문자 영문·숫자·점·밑줄·하이픈으로 입력하세요.')
        external_id = text(external_id, '출처 ID', 300)
        text(url, '원본 URL', 2048)
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port:
            raise ValueError('인증정보 없는 HTTPS 원본 URL이 필요합니다.')
        if not isinstance(raw_metadata, dict):
            raise ValueError('원본 메타데이터는 JSON 객체여야 합니다.')
        raw = json.dumps(raw_metadata, ensure_ascii=False, allow_nan=False)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.require(db, 'editions', edition_id)
            old = db.execute('SELECT * FROM sources WHERE provider=? AND external_id=?',
                             (provider, external_id)).fetchone()
            if old and old['edition_id'] != edition_id:
                raise ValueError('다른 판본에 연결된 출처 ID입니다. 자동 병합하거나 이동하지 않습니다.')
            source_id = old['id'] if old else uuid.uuid4().hex
            if not old:
                db.execute('INSERT INTO sources VALUES(?,?,?,?)', (source_id, edition_id, provider, external_id))
            db.execute('INSERT INTO source_snapshots(source_id,submitted_url,raw_metadata,recorded) VALUES(?,?,?,?)',
                       (source_id, url, raw, time.time()))
        return self.edition(edition_id)

    def edition(self, edition_id):
        with self.db() as db:
            item = self.require(db, 'editions', edition_id)
            item['credits'] = json.loads(item['credits'])
            profile = db.execute('SELECT media_type,translation FROM edition_profiles WHERE edition_id=?', (edition_id,)).fetchone()
            item['profile'] = dict(profile) if profile else {'media_type': 'audio', 'translation': 'none'}
            item['sources'] = []
            for row in db.execute('SELECT * FROM sources WHERE edition_id=? ORDER BY provider,external_id', (edition_id,)):
                source = dict(row)
                source['snapshots'] = []
                for snapshot in db.execute('SELECT * FROM source_snapshots WHERE source_id=? ORDER BY id', (source['id'],)):
                    snapshot = dict(snapshot)
                    snapshot['raw_metadata'] = json.loads(snapshot['raw_metadata'])
                    source['snapshots'].append(snapshot)
                item['sources'].append(source)
            item['tracks'] = [dict(t) for t in db.execute('SELECT * FROM tracks WHERE edition_id=? ORDER BY position', (edition_id,))]
            for track in item['tracks']:
                track['subtitles'] = [dict(s) for s in db.execute('SELECT * FROM subtitles WHERE track_id=? ORDER BY rowid', (track['id'],))]
        return item

    def works(self, query=''):
        with self.db() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM works ORDER BY created DESC,id')]
            editions = [(e['id'], e['work_id']) for e in db.execute('SELECT id,work_id FROM editions ORDER BY created,id')]
        by_work = {r['id']: r for r in rows}
        for work in rows:
            work['editions'] = []
            with self.db() as db:
                work['codes'] = [dict(c) for c in db.execute('SELECT provider,code FROM work_codes WHERE work_id=? ORDER BY code', (work['id'],))]
        for edition_id, work_id in editions:
            by_work[work_id]['editions'].append(self.edition(edition_id))
        if query:
            term = query.casefold()
            rows = [r for r in rows if term in json.dumps(r, ensure_ascii=False).casefold()]
        return rows

    def add_track(self, edition_id, title, relative_path, duration=0):
        duration = number(duration)
        title = text(title, '트랙 제목')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            edition = self.require(db, 'editions', edition_id)
            if edition['kind'] not in ('audio', 'voice_comic'):
                raise ValueError('음성판·보이스코믹에만 트랙을 등록할 수 있습니다.')
            position = db.execute('SELECT COALESCE(MAX(position),0)+1 FROM tracks WHERE edition_id=?', (edition_id,)).fetchone()[0]
            track_id = uuid.uuid4().hex
            db.execute('INSERT INTO tracks(id,edition_id,title,relative_path,duration,position) VALUES(?,?,?,?,?,?)',
                       (track_id, edition_id, title, relative_path, duration, position))
        return self.track(track_id)

    def track(self, track_id):
        with self.db() as db:
            return self.require(db, 'tracks', track_id)

    def reorder_tracks(self, edition_id, ids):
        if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
            raise ValueError('트랙 ID 목록이 필요합니다.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.require(db, 'editions', edition_id)
            rows = db.execute('SELECT id,position FROM tracks WHERE edition_id=?', (edition_id,)).fetchall()
            if len(ids) != len(rows) or set(ids) != {r['id'] for r in rows}:
                raise ValueError('이 판본의 모든 트랙을 중복 없이 지정하세요.')
            offset = max((r['position'] for r in rows), default=0) + 1
            db.execute('UPDATE tracks SET position=position+? WHERE edition_id=?', (offset, edition_id))
            for position, track_id in enumerate(ids, 1):
                db.execute('UPDATE tracks SET position=? WHERE id=? AND edition_id=?', (position, track_id, edition_id))
        return self.edition(edition_id)

    def add_subtitle(self, track_id, relative_path, language='ko', label='한국어'):
        language = text(language, '자막 언어', 100)
        label = text(label, '자막 이름', 200)
        with self.db() as db:
            self.require(db, 'tracks', track_id)
            subtitle_id = uuid.uuid4().hex
            db.execute('INSERT INTO subtitles VALUES(?,?,?,?,?)', (subtitle_id, track_id, relative_path, language, label))
        return {'id': subtitle_id, 'track_id': track_id, 'relative_path': relative_path, 'language': language, 'label': label}

    def subtitle(self, subtitle_id):
        with self.db() as db:
            return self.require(db, 'subtitles', subtitle_id)

    def progress(self, track_id, seconds):
        seconds = number(seconds)
        with self.db() as db:
            track = self.require(db, 'tracks', track_id)
            if track['duration'] and seconds > track['duration']:
                raise ValueError('재생 위치가 트랙 길이를 초과합니다.')
            db.execute('UPDATE tracks SET resume=? WHERE id=?', (seconds, track_id))
        return self.track(track_id)
