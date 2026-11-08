"""Read-only public cast and local language observations, separate from originals."""
import json
import re
from pathlib import Path


class CatalogAnnotations:
    def __init__(self, file):
        self.file = Path(file)

    def read(self):
        if not self.file.exists():
            return {'schema': 1, 'editions': {}, 'subtitles': {}}
        try:
            if self.file.is_symlink() or self.file.stat().st_size > 8 * 1024 * 1024:
                raise ValueError()
            value = json.loads(self.file.read_text(encoding='utf-8'))
            if value.get('schema') != 1 or not isinstance(value.get('editions'), dict) or not isinstance(value.get('subtitles'), dict):
                raise ValueError()
            for key, row in value['editions'].items():
                if not re.fullmatch('[0-9a-f]{32}', key) or not isinstance(row, dict) or not isinstance(row.get('voice_actors', []), list):
                    raise ValueError()
                for actor in row.get('voice_actors', []):
                    if (not isinstance(actor, dict) or not isinstance(actor.get('id'), str) or len(actor['id']) > 128
                            or not isinstance(actor.get('name'), str) or not 1 <= len(actor['name']) <= 300
                            or any(ord(c) < 32 for c in actor['name'])
                            or not re.fullmatch(r'https://www\.dlsite\.com/maniax/work/=/product_id/RJ[0-9]{6,12}\.html', actor.get('source', ''))):
                        raise ValueError()
            for key, row in value['subtitles'].items():
                if not re.fullmatch('[0-9a-f]{32}', key) or not isinstance(row, dict) or row.get('language') not in ('', 'ko', 'ja', 'mixed'):
                    raise ValueError()
            return value
        except (ValueError, TypeError, OSError, AttributeError):
            raise ValueError('성우·언어 확인 기록을 읽지 못했습니다. 원본과 기존 기록은 보존됩니다.') from None

    def attach(self, works):
        value = self.read()
        for work in works:
            for edition in work['editions']:
                row = value['editions'].get(edition['id'], {})
                edition['voice_actors'] = row.get('voice_actors', [])
                edition['voice_actors_checked'] = row.get('voice_actors_checked', False)
                edition['voice_actors_source'] = row.get('voice_actors_source', '')
                edition['audio_language_observation'] = row.get('audio_language_observation', {})
                for track in edition['tracks']:
                    for subtitle in track['subtitles']:
                        if subtitle['id'] in value['subtitles']:
                            subtitle['language_observation'] = value['subtitles'][subtitle['id']]
