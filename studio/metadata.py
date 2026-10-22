"""Site-specific, bounded metadata readers. HTML is data, never executable code."""
import json
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
from sources import parse_source, tags_list, comments_list

MAX_DOCUMENT = 2 * 1024 * 1024


def visible_tag(tag):
    return isinstance(tag, str) and tag.split(':', 1)[0].strip().lower() not in {'date_added', 'timestamp', 'source'}


def canonical_tag(tag):
    """Only established namespace equivalences; original strings stay stored."""
    if ':' not in tag:
        return tag
    namespace, value = tag.split(':', 1)
    if namespace == 'language': value = value.casefold()
    namespace = {'series': 'parody', 'tag': 'other'}.get(namespace, namespace)
    return namespace + ':' + value


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []
        self.parent = None

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self):
        if self.tag in {'script', 'style', 'noscript'}:
            return ''
        return ''.join(child.text() if isinstance(child, Node) else child for child in self.children)

    def by_id(self, value):
        return next((n for n in self.walk() if n.attrs.get('id') == value), None)


class Document(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_DOCUMENT:
            raise ValueError('HTML 크기 제한을 초과했습니다.')
        self.root = Node()
        self.stack, self.count = [self.root], 0
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.count += 1
        if self.count > 20000 or len(self.stack) > 128:
            raise ValueError('HTML 구조 제한을 초과했습니다.')
        node = Node(tag, attrs)
        node.parent = self.stack[-1]
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def clean(node):
    return re.sub(r'\s+', ' ', node.text()).strip() if node else ''


def result(source, title, tags, **extra):
    if not isinstance(title, str) or not title.strip() or len(title) > 2000:
        raise ValueError('작품 제목을 확인하지 못했습니다.')
    raw_tags = tags_list(tags)
    tags = list(dict.fromkeys(canonical_tag(t) for t in raw_tags if visible_tag(t)))
    return {**source, 'title': title.strip(), 'tags': tags, 'raw_tags': raw_tags,
            'artists': [t.split(':', 1)[1] for t in tags if t.startswith('artist:')],
            'languages': [t.split(':', 1)[1] for t in tags if t.startswith('language:') and t != 'language:translated'],
            'collector': 'studio-metadata-v1', **extra}


def parse_html(url, text):
    source = parse_source(url)
    root = Document(text).root
    tags, comments, pages = [], [], None
    if source['provider'] in ('ehentai','exhentai'):
        # Verify gallery identity from declarations, never execute inline scripts.
        scripts = '\n'.join(''.join(c for c in n.children if isinstance(c, str))
                            for n in root.walk() if n.tag == 'script' and not n.attrs.get('src'))
        gids = set(re.findall(r'\b(?:var\s+)?gid\s*=\s*([0-9]+)\s*[;,]', scripts))
        tokens = set(re.findall(r'\b(?:var\s+)?token\s*=\s*[\"\x27]([A-Za-z0-9]+)[\"\x27]', scripts))
        if gids != {source['external_id']} or tokens != {source['url'].rstrip('/').split('/')[-1]}:
            raise ValueError('HTML의 출처 번호·토큰이 입력 URL과 일치하지 않습니다.')
        title = clean(root.by_id('gj')) or clean(root.by_id('gn'))
        taglist = root.by_id('taglist')
        if not taglist:
            raise ValueError('작품 태그 영역을 확인하지 못했습니다.')
        tags = [n.attrs['id'][3:].replace('_', ' ') for n in taglist.walk()
                if n.tag == 'a' and n.attrs.get('id', '').startswith('ta_')]
        detail = root.by_id('gdd')
        if detail:
            for row in detail.walk():
                if row.tag == 'tr':
                    cells = [c for c in row.children if isinstance(c, Node) and c.tag == 'td']
                    if len(cells) == 2 and clean(cells[0]).rstrip(':').lower() == 'length':
                        match = re.fullmatch(r'([0-9]+) pages?', clean(cells[1]))
                        if match: pages = int(match[1])
        area = root.by_id('cdiv')
        if area:
            for node in area.walk():
                if len(comments)>=100: break
                if 'c1' not in node.attrs.get('class', '').split(): continue
                body = next((n for n in node.walk() if 'c6' in n.attrs.get('class', '').split()), None)
                info = next((n for n in node.walk() if 'c3' in n.attrs.get('class', '').split()), None)
                anchor = next((n.attrs.get('name', '')[1:] for n in node.walk()
                               if re.fullmatch(r'c[0-9]+', n.attrs.get('name', ''))), '')
                if not anchor and node.parent:
                    siblings=[n for n in node.parent.children if isinstance(n,Node)]
                    position=siblings.index(node)
                    previous=siblings[position-1] if position else None
                    if previous and re.fullmatch(r'c[0-9]+',previous.attrs.get('name','')):
                        anchor=previous.attrs['name'][1:]
                author = next((clean(n) for n in info.walk() if n.tag == 'a'), '') if info else ''
                if body and anchor:
                    comments.append({'id': anchor, 'text': clean(body), 'author': author,
                                     'posted_at': clean(info), 'source_url': source['url'],
                                     'collector': 'studio-eh-html-v1'})
        return result(source, title, tags, pages=pages, comments=comments_list(comments),
                      title_original=clean(root.by_id('gn')), title_localized=clean(root.by_id('gj')))
    if source['provider'] != 'hitomi':
        raise ValueError('HTML 가져오기는 E-Hentai·Hitomi를 지원합니다.')
    title_node = root.by_id('gallery-brand')
    if not title_node: raise ValueError('Hitomi 작품 영역이 없습니다.')
    identities = {re.search(r'/reader/([0-9]+)\.html$', n.attrs.get('href', ''))[1]
                  for n in title_node.walk() if n.tag == 'a' and re.search(r'/reader/([0-9]+)\.html$', n.attrs.get('href', ''))}
    if identities != {source['external_id']}:
        raise ValueError('HTML의 Hitomi 번호가 입력 URL과 일치하지 않습니다.')
    for field, namespace in [('artists', 'artist'), ('groups', 'group'), ('language', 'language'),
                             ('series', 'series'), ('characters', 'character'), ('tags', 'tag')]:
        area = root.by_id(field)
        if not area: continue
        for node in area.walk():
            if node.tag != 'a': continue
            path = unquote(urlsplit(node.attrs.get('href', '')).path)
            value = clean(node)
            if field == 'tags':
                match = re.fullmatch(r'/tag/(.+)-all\.html', path)
                if not match: continue
                value = match[1]
                tags.append(value if value.startswith(('female:', 'male:')) else 'tag:' + value)
            elif value:
                tags.append(namespace + ':' + value)
    return result(source, clean(title_node), tags, pages=None, comments=[])


def parse_hitomi_json(url, document):
    source = parse_source(url)
    match = re.fullmatch(r'\s*var\s+galleryinfo\s*=\s*(\{.*\})\s*;?\s*', document, re.S)
    if source['provider'] != 'hitomi' or not match: raise ValueError('Hitomi 메타데이터 형식이 변경됐습니다.')
    item = json.loads(match[1])
    if str(item.get('id')) != source['external_id']: raise ValueError('작품 번호가 일치하지 않습니다.')
    tags = []
    for plural, singular in [('artists', 'artist'), ('groups', 'group'), ('parodys', 'parody'), ('characters', 'character')]:
        for entry in item.get(plural) or []:
            if isinstance(entry, dict) and isinstance(entry.get(singular), str): tags.append(singular + ':' + entry[singular])
    for tag in item.get('tags') or []:
        if isinstance(tag, dict) and isinstance(tag.get('tag'), str):
            namespace = 'female' if tag.get('female') in (1, '1') else 'male' if tag.get('male') in (1, '1') else 'tag'
            tags.append(namespace + ':' + tag['tag'])
    if isinstance(item.get('language'), str): tags.append('language:' + item['language'])
    files = item.get('files')
    return result(source, item.get('japanese_title') or item.get('title'), tags,
                  pages=len(files) if isinstance(files, list) else None, comments=[])


def fetch_metadata(url, fetch=None):
    from connectors import public_document
    source = parse_source(url)
    fetch = fetch or public_document
    if source['provider'] == 'hitomi':
        return parse_hitomi_json(url, fetch('https://ltn.gold-usergeneratedcontent.net/galleries/' + source['external_id'] + '.js'))
    if source['provider'] in ('ehentai','exhentai'): return parse_html(url, fetch(source['url']))
    raise ValueError('이 출처의 직접 정보 수집기는 아직 지원하지 않습니다.')


def compare_metadata(first, second):
    """Cross-site evidence, never equal-number inference or a file/edition merge."""
    def norm(value):
        return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', str(value)).casefold())
    def title_key(item):
        value = item.get('title', '')
        for artist in item.get('artists', []):
            value = re.sub(r'^\[' + re.escape(artist) + r'\]\s*', '', value, flags=re.I)
        value = re.sub(r'(?:\s*\[(?:korean|japanese|english|chinese|digital|translated)\])+\s*$', '', value, flags=re.I)
        return norm(value)
    from difflib import SequenceMatcher
    title = SequenceMatcher(None, title_key(first), title_key(second)).ratio()
    artists = bool({norm(a) for a in first.get('artists', [])} & {norm(a) for a in second.get('artists', [])})
    languages = bool(set(first.get('languages', [])) & set(second.get('languages', [])))
    pages = first.get('pages') is not None and first.get('pages') == second.get('pages')
    a, b = set(first.get('tags', [])), set(second.get('tags', []))
    overlap = len(a & b) / len(a | b) if a | b else 0
    exact_title = bool(title_key(first)) and title_key(first) == title_key(second)
    return {'title_similarity': round(title, 3), 'artist_match': artists, 'language_match': languages,
            'page_match': pages, 'tag_similarity': round(overlap, 3),
            'automatic_eligible': first.get('provider') != second.get('provider') and exact_title and artists and languages and pages and overlap >= .7,
            'message': '출처 연결의 비교 근거입니다. 파일 병합·삭제와 판본 통합은 실행하지 않습니다.'}


def public_artist_index(artist,offset=None):
    """Read only the latest eight IDs from the normal public Hitomi artist index."""
    import urllib.request
    import urllib.error
    from urllib.parse import quote
    from connectors import NoRedirect
    if not isinstance(artist,str) or not artist or len(artist)>150: raise ValueError('작가 이름을 확인하세요.')
    url = 'https://ltn.gold-usergeneratedcontent.net/artist/' + quote(artist,safe='') + '-all.nozomi'
    position=0 if offset is None else offset
    if type(position) is not int or not 0<=position<=100000:raise ValueError('작가 색인 범위를 확인하세요.')
    request = urllib.request.Request(url,headers={'Range':f'bytes={position*4}-{position*4+31}','User-Agent':'LibraryStudio/0.1'})
    try:response=urllib.request.build_opener(NoRedirect()).open(request,timeout=20)
    except urllib.error.HTTPError as error:
        if error.code==416 and position:return {'ids':[],'complete':True}
        raise
    with response:
        if response.status not in (200,206): raise ValueError('작가 색인 응답을 확인하지 못했습니다.')
        if response.headers.get_content_type().startswith('text/') or response.headers.get_content_type()=='application/json':
            raise ValueError('작가 색인 대신 오류 문서가 반환됐습니다.')
        scope=re.fullmatch(r'bytes ([0-9]+)-([0-9]+)/([0-9]+)',response.headers.get('Content-Range',''))
        if response.status==206 and (not scope or int(scope[1])!=position*4):
            raise ValueError('작가 색인의 응답 범위가 다릅니다.')
        if response.status==200 and position:raise ValueError('작가 색인의 범위 요청이 지원되지 않습니다.')
        raw=response.read(32)
    if len(raw)%4: raise ValueError('작가 색인 형식이 변경됐습니다.')
    if scope and (int(scope[2])-int(scope[1])+1!=len(raw) or int(scope[3])%4):raise ValueError('작가 색인이 불완전합니다.')
    ids=[str(int.from_bytes(raw[i:i+4],'big')) for i in range(0,len(raw),4)]
    return ids if offset is None else {'ids':ids,'complete':len(raw)<32 or bool(scope and int(scope[2])+1>=int(scope[3]))}


def counterpart_candidates(metadata,fetch=None,index_fetch=None,target=None,cursor=None):
    """Bounded same-title discovery on the other site, without downloading images.

    Artist index checks are deliberately incomplete (latest eight); errors are
    reported, never substituted by another source or treated as no matches.
    """
    import urllib.error
    from urllib.parse import quote,urljoin,parse_qs
    from connectors import public_document
    fetch=fetch or public_document
    target=target or ('ehentai' if metadata['provider']=='hitomi' else 'hitomi')
    if target not in ('ehentai','exhentai','hitomi') or target==metadata['provider']:
        raise ValueError('다른 출처를 지정하세요.')
    output={'provider':target,'items':[],'bounded':True,'failures':0,'status':'checked',
            'message':'제한된 후보 검색입니다. 결과 없음은 다른 사이트에 작품이 없다는 뜻이 아닙니다.'}
    try:
        if cursor is not None and (not isinstance(cursor,dict) or any(type(v) is not int or v<0 for v in cursor.values())):raise ValueError('검색 위치를 확인하세요.')
        if target=='hitomi':
            if not metadata.get('artists'):
                return {**output,'status':'needs_artist','message':'Hitomi 작가 색인 검색에는 작가 정보가 필요합니다.'}
            position=(cursor or {}).get('offset',0)
            page=(index_fetch or public_artist_index)(metadata['artists'][0],position) if cursor is not None else (index_fetch or public_artist_index)(metadata['artists'][0])
            ids=page['ids'] if isinstance(page,dict) else page
            if cursor is not None and not page.get('complete',False):
                output['next_cursor']={'offset':position+8}
                if position+8>100000:output['status']='search_limit';output.pop('next_cursor')
            urls=['https://hitomi.la/galleries/'+number+'.html' for number in list(dict.fromkeys(ids))[:8]
                  if isinstance(number,str) and re.fullmatch(r'[1-9][0-9]{0,11}',number)]
        else:
            # Normal gallery search, not an alternate path to blocked content.
            title=metadata['title'][:150]
            host='exhentai.org' if target=='exhentai' else 'e-hentai.org'
            page_number=(cursor or {}).get('page',0);offset=(cursor or {}).get('offset',0)
            if page_number>1000:raise ValueError('검색 페이지 범위를 확인하세요.')
            search_url='https://'+host+'/?f_search='+quote(title,safe='')+('&page='+str(page_number) if page_number else '')
            html=fetch(search_url)
            root=Document(html).root
            urls=[];has_next=False
            for node in root.walk():
                href=node.attrs.get('href','')
                if node.tag=='a' and re.fullmatch(r'https://'+re.escape(host)+r'/g/[0-9]+/[A-Za-z0-9]+/',href) and href not in urls:
                    urls.append(href)
                if node.tag=='a':
                    link=urlsplit(urljoin(search_url,href));query=parse_qs(link.query)
                    if link.hostname==host and link.path=='/' and query.get('f_search')==[title] and len(query.get('page',[]))==1 and query['page'][0].isdigit() and int(query['page'][0])>page_number:
                        has_next=True
            if cursor is not None:
                if offset+5<len(urls):output['next_cursor']={'page':page_number,'offset':offset+5}
                elif has_next and page_number<1000:output['next_cursor']={'page':page_number+1,'offset':0}
                elif has_next:output['status']='search_limit'
            urls=urls[offset:offset+5]
        if not urls: output['status']='no_candidates'
        for url in urls:
            try:
                candidate=fetch_metadata(url,fetch)
                output['items'].append({'metadata':candidate,'comparison':compare_metadata(metadata,candidate)})
            except urllib.error.HTTPError as error:
                if error.code in (404,410):continue
                output['failures']+=1
                if error.code in (301,302,303,307,308,401,403,429):
                    output.update(status='access_required',message='접근 제한 응답으로 후보 조회를 중단했습니다. 자동 연결하지 않습니다.')
                    return output
            except (ValueError,KeyError,TypeError,OSError):
                output['failures']+=1
        output['items'].sort(key=lambda item:(item['comparison']['automatic_eligible'],item['comparison']['artist_match'],item['comparison']['title_similarity']),reverse=True)
        if output['failures']:output['status']='partial'
        elif output.get('next_cursor'):output['status']='scanning'
    except urllib.error.HTTPError as error:
        output.update(status='access_required' if error.code in (301,302,303,307,308,401,403,429) else 'unavailable',message='대상 사이트 응답을 확인하지 못했습니다. 다른 출처로 대체하지 않습니다.')
    except (OSError,ValueError,KeyError,TypeError):
        output.update(status='unavailable',message='대상 사이트의 연결 또는 색인 형식을 확인하지 못했습니다.')
    return output
