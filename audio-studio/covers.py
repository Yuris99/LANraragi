"""Public DLsite/RPLAY artwork and genre metadata, cached in app data only."""
import json
import ipaddress
import re
import socket
import threading
import tempfile
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

IMAGE_LIMIT = 3 * 1024 * 1024
PAGE_LIMIT = 256 * 1024


class CoverUnavailable(ValueError):
    pass


def allowed_url(url, external_id, image=False, product=False):
    dlsite = bool(re.fullmatch('RJ[0-9]{6,12}', external_id))
    if not isinstance(url, str) or not (dlsite or re.fullmatch('[a-f0-9]{24}', external_id)):
        return False
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.fragment):
            return False
        if product:
            return (dlsite and parsed.hostname == 'www.dlsite.com'
                    and parsed.path == '/maniax/api/=/product.json' and parsed.query in ('workno=' + external_id, 'workno=' + external_id + '&locale=ko_KR'))
        if parsed.query:
            return False
        if dlsite:
            if image:
                return (parsed.hostname == 'img.dlsite.jp' and re.fullmatch(
                    r'/modpub/images2/work/doujin/RJ[0-9]{6,12}/' + re.escape(external_id) + r'_img_(?:main|sam)\.(?:jpg|png|webp)', parsed.path) is not None)
            return parsed.hostname == 'www.dlsite.com' and parsed.path == '/maniax/work/=/product_id/' + external_id + '.html'
        if image:
            return (parsed.hostname == 'pb3.rplay.live'
                    and re.fullmatch('/thumbnail/' + re.escape(external_id) + r'(?:_[a-z]{2})?', parsed.path) is not None)
        return parsed.hostname == 'rplay.live' and parsed.path == '/play/' + external_id
    except ValueError:
        return False


def image_type(data):
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'image/webp'
    raise CoverUnavailable('지원되는 표지 이미지가 아닙니다.')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise CoverUnavailable('표지 요청의 외부 이동을 허용하지 않습니다.')


def public_get(url, limit):
    # Exact public hosts and paths are checked by callers; redirects/proxy credentials are never used.
    addresses = socket.getaddrinfo(urlsplit(url).hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
        raise CoverUnavailable('공개 표지 주소가 필요합니다.')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, headers={'User-Agent': 'AudioStudio/0.1', 'Accept-Encoding': 'identity'})
    with opener.open(request, timeout=8) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise CoverUnavailable('표지 응답이 너무 큽니다.')
        return data


class OpenGraph(HTMLParser):
    image = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'meta' and (values.get('property') or values.get('name', '')).lower() == 'og:image':
            self.image = values.get('content')


def metadata_image(value, external_id, depth=0):
    if depth > 6:
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            if any(word in key.lower() for word in ('thumbnail', 'cover', 'image', 'poster')):
                candidate = item.get('url') if isinstance(item, dict) else item
                if isinstance(candidate, str):
                    candidate = 'https:' + candidate if candidate.startswith('//') else candidate
                    if allowed_url(candidate, external_id, image=True):
                        return candidate
            if isinstance(item, (dict, list)):
                found = metadata_image(item, external_id, depth + 1)
                if found:
                    return found
    elif isinstance(value, list):
        for item in value:
            found = metadata_image(item, external_id, depth + 1)
            if found:
                return found
    return None


class RplayCovers:
    def __init__(self, directory, fetch=public_get, media_root=None):
        self.directory = Path(directory)
        self.fetch = fetch
        self.guard = threading.Lock()
        self.locks = {}
        self.failed = {}
        self.slots = threading.BoundedSemaphore(2)
        self.media_root = Path(media_root).resolve() if media_root is not None else None

    def lock(self, key):
        with self.guard:
            return self.locks.setdefault(key, threading.Lock())

    def write(self, file, data):
        self.directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=self.directory, prefix=file.stem, suffix='.tmp', delete=False) as output:
            output.write(data)
            temporary = Path(output.name)
        try:
            temporary.replace(file)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def sources(edition):
        sources = list(edition['sources'])
        info = edition.get('credits', {}).get('nas_import', {})
        external_id = info.get('source_id', '')
        if (info.get('provider', '').lower() == 'dlsite' and isinstance(external_id, str) and re.fullmatch('RJ[0-9]{6,12}', external_id)
                and not any(s['provider'] == 'dlsite' and s['external_id'] == external_id for s in sources)):
            sources.append({'provider': 'dlsite', 'external_id': external_id, 'snapshots': [{
                'submitted_url': 'https://www.dlsite.com/maniax/work/=/product_id/' + external_id + '.html', 'raw_metadata': {}}]})
        return sources

    def local_cover(self, edition):
        info = edition.get('credits', {}).get('nas_import', {})
        relative = info.get('root', '')
        if not self.media_root or not isinstance(relative, str) or not relative.lower().startswith('dlsite/') or '\\' in relative or ':' in relative:
            return None
        directory = self.media_root / ('DLsite/' + relative.split('/', 1)[1])
        try:
            resolved = directory.resolve()
            if not resolved.is_relative_to(self.media_root) or '..' in Path(relative).parts:
                return None
            names = ['folder.jpg', 'folder.png', 'cover.jpg', 'cover.png', 'パッケージ.png', 'パッケージ.jpg', 'ジャケット.jpg', 'ジャケット.png']
            external_id = info.get('source_id', '')
            if isinstance(external_id, str) and re.fullmatch('RJ[0-9]{6,12}', external_id):
                names.insert(0, external_id + '_img_main.jpg')
            for name in names:
                file = directory / name
                if file.is_symlink() or not file.resolve().is_relative_to(resolved) or not file.is_file():
                    continue
                with file.open('rb') as image:
                    data = image.read(IMAGE_LIMIT + 1)
                if len(data) <= IMAGE_LIMIT:
                    try:
                        return data, image_type(data)
                    except CoverUnavailable:
                        pass
        except OSError:
            pass
        return None

    def read_info(self, external_id):
        file = self.directory / ('dlsite-' + external_id + '.json')
        if self.directory.is_symlink() or file.is_symlink():
            raise CoverUnavailable('표지 캐시는 앱 데이터 폴더 안에 있어야 합니다.')
        try:
            if file.stat().st_size <= PAGE_LIMIT:
                info = json.loads(file.read_text(encoding='utf-8'))
                image_id = info.get('image_external_id', external_id)
                if (info.get('version') == 3 and info.get('external_id') == external_id
                        and isinstance(info.get('tags'), list) and all(isinstance(tag, str) for tag in info['tags'])
                        and isinstance(info.get('titles'), dict) and all(key in ('ja', 'ko') and isinstance(value, str) for key, value in info['titles'].items())
                        and isinstance(image_id, str) and re.fullmatch('RJ[0-9]{6,12}', image_id)
                        and (not info.get('image') or allowed_url(info['image'], image_id, image=True))):
                    return info
        except (OSError, ValueError, AttributeError):
            pass
        return None

    def product(self, external_id, korean=False):
        url = 'https://www.dlsite.com/maniax/api/=/product.json?workno=' + external_id + ('&locale=ko_KR' if korean else '')
        if not allowed_url(url, external_id, product=True):
            raise CoverUnavailable('허용되지 않는 상품 정보 주소입니다.')
        with self.slots:
            raw = self.fetch(url, PAGE_LIMIT)
        if len(raw) > PAGE_LIMIT:
            raise CoverUnavailable('상품 정보가 너무 큽니다.')
        value = json.loads(raw)
        product = value[0] if isinstance(value, list) and value else value
        if not isinstance(product, dict) or product.get('workno') != external_id:
            raise CoverUnavailable('상품 식별자가 일치하지 않습니다.')
        return product

    @staticmethod
    def related_ids(product):
        translation = product.get('translation_info') or {}
        return {value for value in [product.get('workno'), translation.get('original_workno'), translation.get('parent_workno'),
                *(e.get('workno') for e in product.get('language_editions') or [] if isinstance(e, dict))]
                if isinstance(value, str) and re.fullmatch('RJ[0-9]{6,12}', value)}

    def product_info(self, external_id, refresh=False):
        key = 'info:' + external_id
        with self.lock(key):
            file = self.directory / ('dlsite-' + external_id + '.json')
            cached = self.read_info(external_id)
            if cached and not refresh:
                return cached
            if refresh:
                self.failed.pop(key, None)
            if self.failed.get(key, 0) > time.monotonic():
                raise CoverUnavailable('공개 상품 정보를 찾을 수 없습니다.')
            try:
                product = self.product(external_id)
                genres = product.get('genres_replaced') or product.get('genres') or []
                genres = genres if isinstance(genres, list) else []
                tags = list(dict.fromkeys(genre['name'].strip() for genre in genres if isinstance(genre, dict) and isinstance(genre.get('name'), str) and genre['name'].strip()))
                related = self.related_ids(product)
                image_main = product.get('image_main') or {}
                image_id = image_main.get('workno', external_id) if isinstance(image_main, dict) else external_id
                image_id = image_id if image_id in related else external_id
                image = metadata_image({'image_main': image_main}, image_id)
                titles, title_sources = {}, {}
                language = str((product.get('translation_info') or {}).get('lang') or 'JPN').upper()
                if isinstance(product.get('work_name'), str) and product['work_name'].strip():
                    key_language = 'ko' if language in ('KO_KR', 'KOR', 'KO') else 'ja' if language in ('JPN', 'JA_JP', 'JA', '') else None
                    try:
                        title_product = self.product(external_id, korean=True) if key_language == 'ko' else product
                    except (OSError, ValueError, urllib.error.URLError):
                        title_product = {}
                    if key_language:
                        titles[key_language] = str(title_product.get('work_name') or '').strip()
                        title_sources[key_language] = external_id
                for target_language, language_codes in [('ja', ('JPN', 'JA_JP', 'JA')), ('ko', ('KO_KR', 'KOR', 'KO'))]:
                    if target_language in titles:
                        continue
                    target = next((e.get('workno') for e in product.get('language_editions') or []
                                   if isinstance(e, dict) and set(str(e.get('lang', '')).upper().split(',')).intersection(language_codes) and e.get('workno') in related), None)
                    if not target or target == external_id:
                        continue
                    try:
                        translated = self.product(target, korean=target_language == 'ko')
                        # Only the original product's explicit official language link can supply a title.
                        if related.intersection(self.related_ids(translated)) and isinstance(translated.get('work_name'), str) and translated['work_name'].strip():
                            titles[target_language] = translated['work_name'].strip()
                            title_sources[target_language] = target
                    except (OSError, ValueError, urllib.error.URLError):
                        pass
                titles = {language: title for language, title in titles.items() if title and (language != 'ko' or any('\uac00' <= c <= '\ud7a3' for c in title))}
                title_sources = {language: source_id for language, source_id in title_sources.items() if language in titles}
                info = {'version': 3, 'external_id': external_id, 'tags': tags, 'image': image,
                        'image_external_id': image_id, 'titles': titles, 'title_sources': title_sources}
                self.write(file, json.dumps(info, ensure_ascii=False).encode('utf-8'))
                return info
            except (OSError, ValueError, urllib.error.URLError):
                self.failed[key] = time.monotonic() + 300
                raise CoverUnavailable('공개 상품 정보를 가져올 수 없습니다.') from None

    def info(self, edition, cached_only=False):
        for source in self.sources(edition):
            if source['provider'].lower() == 'dlsite' and re.fullmatch('RJ[0-9]{6,12}', source['external_id']):
                return self.read_info(source['external_id']) if cached_only else self.product_info(source['external_id'])
        raise CoverUnavailable('연결된 DLsite 상품 식별자가 없습니다.')

    def get(self, edition, retry=False):
        local = self.local_cover(edition)
        if local:
            return local
        for source in self.sources(edition):
            external_id = source['external_id']
            provider = source['provider'].lower()
            if provider not in ('dlsite', 'rplay') or not re.fullmatch('RJ[0-9]{6,12}' if provider == 'dlsite' else '[a-f0-9]{24}', external_id):
                continue
            snapshots = [s for s in reversed(source['snapshots']) if allowed_url(s['submitted_url'], external_id)]
            if not snapshots and provider == 'dlsite':
                # Translation URLs can name a parent RJ; request only the saved source ID's canonical public endpoint.
                snapshots = [{'submitted_url': 'https://www.dlsite.com/maniax/work/=/product_id/' + external_id + '.html', 'raw_metadata': {}}]
            if not snapshots:
                continue
            key = provider + ':' + external_id
            with self.lock(key):
                file = self.directory / (('dlsite-' if provider == 'dlsite' else '') + external_id + '.cover')
                if self.directory.is_symlink() or file.is_symlink():
                    raise CoverUnavailable('표지 캐시는 앱 데이터 폴더 안에 있어야 합니다.')
                try:
                    if file.stat().st_size <= IMAGE_LIMIT:
                        data = file.read_bytes()
                        return data, image_type(data)
                except (OSError, CoverUnavailable):
                    pass
                if retry:
                    self.failed.pop(key, None)
                if self.failed.get(key, 0) > time.monotonic():
                    raise CoverUnavailable('공개 표지를 찾을 수 없습니다.')
                try:
                    image = next((url for s in snapshots if (url := metadata_image(s['raw_metadata'], external_id))), None)
                    candidates = [(image, external_id)] if image else []
                    if provider == 'dlsite':
                        try:
                            info = self.product_info(external_id, refresh=retry)
                            if info['image']:
                                candidates.append((info['image'], info['image_external_id']))
                        except CoverUnavailable:
                            pass
                    with self.slots:
                        for image, image_id in dict.fromkeys(candidates):
                            try:
                                if not allowed_url(image, image_id, image=True):
                                    continue
                                data = self.fetch(image, IMAGE_LIMIT)
                                if len(data) > IMAGE_LIMIT:
                                    continue
                                content_type = image_type(data)
                                self.write(file, data)
                                return data, content_type
                            except (OSError, ValueError, urllib.error.URLError):
                                continue
                        # Old sidecars can contain obsolete artwork URLs; a failed one does not block the official fallback.
                        parser = OpenGraph()
                        parser.feed(self.fetch(snapshots[0]['submitted_url'], PAGE_LIMIT).decode('utf-8', 'replace'))
                        image = parser.image
                        if not image or not allowed_url(image, external_id, image=True):
                            raise CoverUnavailable('공개 표지를 찾을 수 없습니다.')
                        data = self.fetch(image, IMAGE_LIMIT)
                        if len(data) > IMAGE_LIMIT:
                            raise CoverUnavailable('표지 이미지가 너무 큽니다.')
                        content_type = image_type(data)
                        self.write(file, data)
                        return data, content_type
                except (OSError, ValueError, urllib.error.URLError):
                    self.failed[key] = time.monotonic() + 300
                    raise CoverUnavailable('공개 표지를 가져올 수 없습니다.') from None
        raise CoverUnavailable('연결된 공개 원본 주소가 없습니다.')
