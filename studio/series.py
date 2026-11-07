"""User-curated reading series; independent from source tags and edition groups."""
import re
import uuid

SCHEMA='''
CREATE TABLE IF NOT EXISTS reading_series(id TEXT PRIMARY KEY,name TEXT NOT NULL,name_key TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS series_members(series_id TEXT NOT NULL REFERENCES reading_series(id),
 work_id TEXT NOT NULL REFERENCES works(id),position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 100000),
 PRIMARY KEY(series_id,work_id));
CREATE INDEX IF NOT EXISTS series_members_work ON series_members(work_id);
'''


class SeriesCatalog:
    def list_series(self):
        with self.db() as db:
            return [dict(row) for row in db.execute('''SELECT s.id,s.name,count(w.id) AS count
                FROM reading_series s LEFT JOIN series_members m ON m.series_id=s.id
                LEFT JOIN works w ON w.id=m.work_id AND w.merged_into IS NULL
                GROUP BY s.id ORDER BY s.name,s.id''')]

    def work_series(self,work_id):
        with self.db() as db:
            return self.series_for_works(db,[work_id])[work_id]

    @staticmethod
    def series_for_works(db,work_ids):
        result={work_id:[] for work_id in work_ids}
        if not work_ids:return result
        placeholders=','.join('?' for _ in work_ids)
        for row in db.execute('''SELECT m.work_id,s.id,s.name,m.position,
                (SELECT count(*) FROM series_members other JOIN works w ON w.id=other.work_id
                 WHERE other.series_id=s.id AND w.merged_into IS NULL) AS count
                FROM series_members m JOIN reading_series s ON s.id=m.series_id
                WHERE m.work_id IN ('''+placeholders+''') ORDER BY s.name,s.id''',work_ids):
            value=dict(row);result[value.pop('work_id')].append(value)
        return result

    def set_work_series(self,work_id,data):
        if not isinstance(data,dict) or set(data)-{'series_id','name','position'}:
            raise ValueError('시리즈 이름·묶음·권 순서만 지정하세요.')
        work_id=self.get_work(work_id)['id']
        series_id=data.get('series_id');name=data.get('name','');position=data.get('position')
        if series_id is not None and (not isinstance(series_id,str) or not re.fullmatch('[0-9a-f]{32}',series_id)):
            raise ValueError('시리즈 묶음을 선택하세요.')
        if not isinstance(name,str) or any(ord(c)<32 for c in name) or len(name)>120:
            raise ValueError('시리즈 이름은 1~120자로 입력하세요.')
        name=name.strip()
        if bool(series_id)==bool(name):raise ValueError('기존 시리즈를 선택하거나 새 이름을 입력하세요.')
        if position is not None and (type(position) is not int or not 1<=position<=100000):
            raise ValueError('권 순서는 1~100000의 정수로 입력하세요.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM works WHERE id=? AND merged_into IS NULL',(work_id,)).fetchone():raise KeyError('작품을 찾을 수 없습니다.')
            if series_id:
                if not db.execute('SELECT 1 FROM reading_series WHERE id=?',(series_id,)).fetchone():raise KeyError('시리즈를 찾을 수 없습니다.')
            else:
                if db.execute('SELECT 1 FROM reading_series WHERE name_key=?',(name.casefold(),)).fetchone():
                    raise ValueError('같은 이름의 시리즈가 있습니다. 기존 시리즈에서 선택하세요.')
                series_id=uuid.uuid4().hex
                db.execute('INSERT INTO reading_series VALUES(?,?,?)',(series_id,name,name.casefold()))
            current=db.execute('SELECT position FROM series_members WHERE series_id=? AND work_id=?',(series_id,work_id)).fetchone()
            if position is None:position=current[0] if current else db.execute('SELECT COALESCE(max(position),0)+1 FROM series_members WHERE series_id=?',(series_id,)).fetchone()[0]
            if position>100000:raise ValueError('권 순서 범위를 초과했습니다.')
            db.execute('INSERT INTO series_members VALUES(?,?,?) ON CONFLICT(series_id,work_id) DO UPDATE SET position=excluded.position',(series_id,work_id,position))
        return self.get_work(work_id)

    def remove_work_series(self,work_id,series_id):
        work_id=self.get_work(work_id)['id']
        if not isinstance(series_id,str) or not re.fullmatch('[0-9a-f]{32}',series_id):raise ValueError('시리즈 묶음을 확인하세요.')
        with self.db() as db:db.execute('DELETE FROM series_members WHERE series_id=? AND work_id=?',(series_id,work_id))
        return self.get_work(work_id)
