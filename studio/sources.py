"""Source identity is (provider, external_id), never an unqualified number."""
import re
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
            return dict(provider='ehentai', external_id=match[1],
                        url=f'https://{host}/g/{match[1]}/{match[2]}/')
    if host == 'hitomi.la':
        match = re.fullmatch(r'/(?:galleries|reader)/(\d+)\.html', value.path)
        if not match:
            match = re.fullmatch(r'/(?:manga|doujinshi|artistcg|gamecg|imageset)/[^/]+-(\d+)\.html', value.path)
        if match:
            return dict(provider='hitomi', external_id=match[1],
                        url=f'https://hitomi.la/galleries/{match[1]}.html')
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
                       for k in ('id', 'author', 'text', 'posted_at')})
    return result
