"""Source identity is (provider, external_id), never an unqualified number."""
import re
import unicodedata
from urllib.parse import urlsplit


def parse_source(url):
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('올바른 작품 URL을 입력하세요.')
    value = urlsplit(url.strip())
    if value.scheme != 'https' or value.username or value.password or value.port:
        raise ValueError('HTTPS 작품 URL만 사용할 수 있습니다.')
    host = (value.hostname or '').lower()
    if value.query or value.fragment:
        raise ValueError('검색·추적 매개변수가 없는 작품 URL을 입력하세요.')
    if host in ('e-hentai.org', 'exhentai.org'):
        match = re.fullmatch(r'/g/(\d+)/([a-zA-Z0-9]+)/?', value.path)
        if match:
            return dict(provider='exhentai' if host=='exhentai.org' else 'ehentai', external_id=match[1],
                        url=f'https://{host}/g/{match[1]}/{match[2]}/')
    if host == 'hitomi.la':
        match = re.fullmatch(r'/(?:galleries|reader)/(\d+)\.html', value.path)
        if not match:
            match = re.fullmatch(r'/(?:manga|doujinshi|artistcg|gamecg|imageset)/[^/]+-(\d+)\.html', value.path)
        if match:
            return dict(provider='hitomi', external_id=match[1],
                        url='https://hitomi.la'+value.path)
    if host == 'nhentai.net':
        match = re.fullmatch(r'/g/(\d+)/?', value.path)
        if match:
            return dict(provider='nhentai', external_id=match[1],
                        url=f'https://nhentai.net/g/{match[1]}/')
    raise ValueError('지원하는 사이트의 작품 상세 URL을 입력하세요.')


def tags_list(value):
    if isinstance(value, str):
        value = value.split(',')
    if not isinstance(value, list) or len(value) > 2000:
        raise ValueError('태그는 문자열 목록이어야 합니다.')
    if any(not isinstance(x, str) or len(x) > 300 for x in value):
        raise ValueError('태그 형식이 올바르지 않습니다.')
    return list(dict.fromkeys(x.strip() for x in value if x.strip()))


def comments_list(value):
    if not isinstance(value, list) or len(value) > 10000:
        raise ValueError('댓글은 목록이어야 합니다.')
    result = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get('text'), str):
            raise ValueError('댓글에는 text 필드가 필요합니다.')
        result.append({k: str(item.get(k, ''))[:20000 if k == 'text' else 500]
                       for k in ('id', 'author', 'text', 'posted_at', 'source_url', 'collector', 'fetched_at')})
    return result


def filename_hints(filename):
    """Conservative local evidence only; a bare number never identifies a site."""
    from pathlib import PurePosixPath
    name = PurePosixPath(str(filename).replace('\\', '/')).name
    name = re.sub(r'\.(?:cbz|zip|cbr|rar|7z|pdf)$', '', name, flags=re.I)[:1000]
    basename=name
    name=re.sub(r'\s+\[L[1-9][0-9]*\]\s*$','',name,flags=re.I)
    numbers = []
    for match in re.finditer(r'(?<!\w)([HEXNU]?)([0-9]{3,12})(?!\w)', name, re.I):
        prefix, number = match.groups()
        # Years and chapter/page labels without a provider prefix are ambiguous.
        if not prefix and (1900 <= int(number) <= 2099 or re.search(r'(?:chapter|ch|vol|page|p)\s*$', name[:match.start()], re.I)):
            continue
        hint = {'number': number, 'provider': {'h':'hitomi','e':'ehentai','x':'exhentai','n':'nhentai'}.get(prefix.lower())}
        if hint not in numbers: numbers.append(hint)
    artist = ''
    # Only a leading bracket is an author hint, never arbitrary title parentheses.
    match = re.match(r'^\s*(?:[\[(]?[HEXNU]?\d{3,12}[\])]?\s*[-_. ]*\s*)?\[([^\[\]]{1,150})\]', name, re.I)
    if match:
        value = match[1].strip()
        if not re.fullmatch(r'[HEXNU]?\d+|(?:C|COMIC1)\d+|(?:english|korean|japanese|chinese|digital|韓国語|日本語)', value, re.I):
            artist = value
    title=name
    if match and artist:title=name[match.end():].strip()
    if len(numbers)==1:
        token=re.escape(({'hitomi':'H','ehentai':'E','exhentai':'X','nhentai':'N'}.get(numbers[0]['provider'],'U' if re.search(r'(?<!\w)U'+numbers[0]['number']+r'(?!\w)',name,re.I) else '')+numbers[0]['number']))
        title=re.sub(r'\s*[\[({]'+token+r'[\])}]\s*$','',title,flags=re.I).strip()
        title=re.sub(r'^'+token+r'\s*[-_. ]+','',title,flags=re.I).strip()
    return {'filename': basename, 'title':title or name, 'numbers': numbers, 'artist': artist,
            'ambiguous': len(numbers) != 1,
            'provenance': 'filename-hint-only'}


def clean_title(title, artists=(), source_ids=()):
    """Derived display/search text; never rename a file or overwrite its title."""
    original = str(title or '').strip()
    value = re.sub(r'\.(?:cbz|zip|cbr|rar|7z|pdf)$', '', original, flags=re.I)
    def key(text):
        return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', text).casefold())
    names = [artists] if isinstance(artists, str) else list(artists)
    known = {key(name) for name in names if name}
    known.update(key(part) for name in names for part in re.split(r'[,、]', name) if part.strip())
    value = re.sub(r'^\s*\((?:C\d+|COMIC1[^)]*|COMITIA\s*\d+|コミティア\d+)\)\s*', '', value, flags=re.I)
    prefix = re.match(r'^\[([^\[\]]+)\]\s*', value)
    if prefix and (key(prefix[1]) in known or {key(part.strip()) for part in re.split(r'[,、]', prefix[1])} <= known or re.search(r'\([^()]+\)$', prefix[1])):
        value = value[prefix.end():]
    value = re.sub(r'(?:\s*\[(?:korean|japanese|english|chinese|digital|translated|韓国翻訳|韓国語|日本語)\])+\s*$', '', value, flags=re.I)
    suffix = re.search(r'\s*[\[({]([HEXNLU]?\d{1,12})[\])}]\s*$', value, flags=re.I)
    if suffix and suffix[1].upper().lstrip('HEXNLU') in {str(n).upper().lstrip('HEXNLU') for n in source_ids}:
        value = value[:suffix.start()]
    value = re.sub(r'(?:\s*\[(?:korean|japanese|english|chinese|digital|translated|韓国翻訳|韓国語|日本語)\])+\s*$', '', value, flags=re.I)
    return value.strip() or original


def canonical_archive_name(title, artist='', provider=None, number=None):
    """A proposed basename, never a filesystem instruction or move operation."""
    def clean(value):
        value=re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', '_', str(value)).strip(' .')
        return value.encode('utf-8')[:90].decode('utf-8','ignore')
    title = clean(title) or 'Untitled'
    artist = clean(artist) or 'Unknown'
    prefix = {'hitomi':'H','ehentai':'E','exhentai':'X','nhentai':'N'}.get(provider, 'U')
    identity = f' [{prefix}{number}]' if isinstance(number,str) and re.fullmatch(r'\d{1,12}',number) else ''
    return f'[{artist}] {title}{identity}.cbz'
