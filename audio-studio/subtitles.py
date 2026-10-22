"""Read UTF-8 SRT/WebVTT as plain timed text; never interpret HTML."""
import html
import re

STAMP = r'(?:\d{1,4}:)?\d{2}:\d{2}[.,]\d{3}'
TIMING = re.compile(r'^(' + STAMP + r')\s+-->\s+(' + STAMP + r')(?:\s+.*)?$')


def seconds(value):
    parts = value.replace(',', '.').split(':')
    if len(parts) == 3:
        hours, minutes, sec = int(parts[0]), int(parts[1]), float(parts[2])
    else:
        hours, minutes, sec = 0, int(parts[0]), float(parts[1])
    if minutes >= 60 or sec >= 60:
        raise ValueError('자막 시간 형식이 잘못되었습니다.')
    return hours * 3600 + minutes * 60 + sec


def parse_subtitles(raw):
    if len(raw.encode('utf-8')) > 4 * 1024 * 1024:
        raise ValueError('자막은 4 MiB 이하여야 합니다.')
    blocks = re.split(r'\n[ \t]*\n', raw.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n').strip())
    cues = []
    for block in blocks:
        lines = block.split('\n')
        if lines[0].startswith(('WEBVTT', 'NOTE', 'STYLE', 'REGION')):
            continue
        index = 0 if '-->' in lines[0] else 1
        if index >= len(lines):
            raise ValueError('자막 시간 행이 없습니다.')
        timing = TIMING.fullmatch(lines[index].strip())
        if not timing:
            raise ValueError('지원하지 않는 자막 시간 형식입니다. SRT 또는 WebVTT를 사용하세요.')
        start, end = seconds(timing[1]), seconds(timing[2])
        if end <= start:
            raise ValueError('자막 종료 시간은 시작 시간보다 커야 합니다.')
        content = html.unescape(re.sub(r'<[^>]*>', '', '\n'.join(lines[index + 1:])))
        cues.append({'start': start, 'end': end, 'text': content})
        if len(cues) > 30000:
            raise ValueError('자막 개수가 너무 많습니다.')
    if not cues:
        raise ValueError('표시할 자막이 없습니다.')
    return sorted(cues, key=lambda cue: cue['start'])


def read_subtitles(path):
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('자막은 4 MiB 이하여야 합니다.')
    try:
        return parse_subtitles(path.read_text(encoding='utf-8-sig'))
    except UnicodeError as error:
        raise ValueError('UTF-8 자막 파일이 필요합니다.') from error
