"""Source candidates from our portable record or the original first-page image."""
import hashlib
import re
import urllib.error
from urllib.parse import parse_qs,urlsplit,urljoin
import urllib.request
from metadata import Document,fetch_metadata,compare_metadata,counterpart_candidates
from source_record import preferred_evidence
from sources import parse_source


def preview_url(url):
    if not isinstance(url,str) or len(url)>1024:raise ValueError('표지 주소를 확인하세요.')
    value=urlsplit(url)
    if value.scheme!='https' or value.hostname!='ehgt.org' or value.username or value.password or value.port or value.query or value.fragment or '..' in value.path or not re.fullmatch(r'/[A-Za-z0-9_./-]+\.(?:jpe?g|png|webp)',value.path,re.I):
        raise ValueError('허용된 후보 표지 주소가 아닙니다.')
    return url


def preview_image(url):
    url=preview_url(url)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    with urllib.request.build_opener(NoRedirect()).open(url,timeout=15) as response:
        raw=response.read(768*1024+1)
    if len(raw)>768*1024:raise ValueError('후보 표지 이미지 크기 한도입니다.')
    return raw


def baseline(work,record):
    metadata=next((s.get('metadata') for s in work.get('sources',[]) if s.get('metadata',{}).get('title')),None)
    if not metadata:metadata=next((e['metadata'] for e in record.get('evidence',[]) if e.get('metadata',{}).get('title')),None)
    metadata=metadata or {}
    hint=work.get('organization',{})
    return {'provider':'local','title':metadata.get('title') or hint.get('title') or work['title'],
            'artists':metadata.get('artists') or ([work.get('artist') or hint.get('artist')] if work.get('artist') or hint.get('artist') else []),
            'languages':metadata.get('languages',[]),'tags':metadata.get('tags',[]),
            'pages':work.get('pages') or metadata.get('pages') or next((e.get('pages') for e in record.get('evidence',[]) if e.get('pages')),None)}


def first_page_hash(lrr,work,page=1):
    arcid=work.get('lrr_id')
    if not arcid or not re.fullmatch('[0-9a-f]{40}',arcid):raise ValueError('이미지 검색에는 연결된 만화 파일이 필요합니다.')
    if type(page) is not int or not 1<=page<=20000:raise ValueError('검색할 페이지를 확인하세요.')
    pages=lrr.json('/api/archives/'+arcid+'/files').get('pages',[])
    if page>len(pages):raise ValueError('검색할 페이지가 없습니다.')
    value=urlsplit(pages[page-1])
    if value.netloc or value.fragment or value.path!='/api/archives/'+arcid+'/page':raise ValueError('만화 페이지 주소를 확인하세요.')
    path=value.path+('?'+value.query if value.query else '')
    digest=hashlib.sha1();size=0
    with lrr.open(path) as response:
        if response.status!=200:raise ValueError('검색할 만화 페이지를 읽지 못했습니다.')
        prefix=response.read(32);size+=len(prefix)
        if not (prefix.startswith(b'\xff\xd8\xff') or prefix.startswith(b'\x89PNG\r\n\x1a\n') or prefix.startswith(b'RIFF') and prefix[8:12]==b'WEBP'):
            raise ValueError('검색할 페이지의 이미지 형식을 확인하세요.')
        digest.update(prefix)
        while chunk:=response.read(256*1024):
            size+=len(chunk)
            if size>16*1024**2:raise ValueError('검색 이미지 크기 한도는 16MiB입니다.')
            digest.update(chunk)
    return digest.hexdigest(),'/api/media/'+arcid+'/page'+('?'+value.query if value.query else '')


def candidates(work,record,method,fetch,index_fetch=None,lrr=None,cursor=None,page=1,default_provider='ehentai',from_url=None):
    if method not in ('embedded','image','title','hitomi'):raise ValueError('지원하는 후보 검색 방법을 선택하세요.')
    if default_provider not in ('ehentai','exhentai'):raise ValueError('검색할 출처 계열을 확인하세요.')
    cursor={} if cursor is None else cursor
    if not isinstance(cursor,dict) or set(cursor)-{'page','offset'} or any(type(v) is not int or not 0<=v<=100000 for v in cursor.values()):raise ValueError('검색 위치를 확인하세요.')
    base=baseline(work,record)
    result={'items':[],'baseline':base,'method':method,'status':'checked','failures':0,'message':'후보를 비교한 뒤 연결할 출처를 선택하세요.'}
    if from_url is not None:
        if method!='hitomi' or parse_source(from_url)['provider'] not in ('ehentai','exhentai'):
            raise ValueError('히토미 검색에 사용할 이헨·익헨 후보 주소를 확인하세요.')
        try:seed=fetch_metadata(from_url,fetch)
        except urllib.error.HTTPError as error:
            return {**result,'status':'access_required' if error.code in (401,403,429) else 'unavailable','message':'선택한 원본 후보를 읽지 못했습니다. 접근 상태를 확인하세요.'}
        except (OSError,ValueError):
            return {**result,'status':'unavailable','message':'선택한 원본 후보 정보를 확인하지 못했습니다.'}
        base={**seed,'provider':'local','pages':base['pages'] or seed.get('pages'),
              'languages':base['languages'] or seed['languages']}
        result.update(baseline=base,seed_url=seed['url'],message='이미지 후보의 작가·제목으로 히토미를 찾았습니다. 이미지 일치가 확정된 결과는 아니므로 표지·언어·페이지 수를 비교하세요.')
    preferred=preferred_evidence(record.get('evidence',[]))
    linked=next((s['provider'] for s in work.get('sources',[]) if s['provider'] in ('ehentai','exhentai')),None)
    provider=preferred['provider'] if preferred and preferred['provider'] in ('ehentai','exhentai') else linked or default_provider
    if method in ('title','hitomi'):
        value=counterpart_candidates(base,fetch,index_fetch,target='hitomi' if method=='hitomi' else provider,cursor=cursor)
        if from_url:value['message']=result['message']+' '+value['message']
        return {**result,**value}
    try:
        urls=[]
        if method=='embedded':
            evidence=[preferred] if preferred else record.get('evidence',[])
            urls=list(dict.fromkeys(e['url'] for e in evidence if e.get('url')))[:5]
            if not urls:result.update(status='no_candidates',message='원본 작품 주소를 복원할 정보가 없습니다. 이미지·제목 검색을 사용하세요.')
        else:
            digest,image=first_page_hash(lrr,work,page)
            host='exhentai.org' if provider=='exhentai' else 'e-hentai.org'
            position=cursor.get('page',0);offset=cursor.get('offset',0)
            if position>1000:raise ValueError('검색 페이지 범위를 확인하세요.')
            search='https://'+host+'/?f_shash='+digest+'&fs_similar=1&fs_covers=1'+('&page='+str(position) if position else '')
            html=fetch(search)
            if re.search(r'<title>\s*(?:just a moment|attention required)|cf-chl-|challenge-platform',html,re.I):
                return {**result,'status':'access_required','message':'검색 사이트의 사람 인증이 필요합니다. NAS 브라우저에서 정상 접근을 확인하세요.'}
            root=Document(html).root;next_page=False
            for node in root.walk():
                if node.tag!='a':continue
                href=node.attrs.get('href','')
                if re.fullmatch('https://'+re.escape(host)+r'/g/[0-9]+/[A-Za-z0-9]+/',href) and href not in urls:urls.append(href)
                link=urlsplit(urljoin(search,href));query=parse_qs(link.query)
                if link.hostname==host and link.path=='/' and query.get('f_shash')==[digest] and len(query.get('page',[]))==1 and query['page'][0].isdigit() and int(query['page'][0])>position:next_page=True
            if offset+5<len(urls):result['next_cursor']={'page':position,'offset':offset+5}
            elif next_page and position<1000:result['next_cursor']={'page':position+1,'offset':0}
            urls=urls[offset:offset+5]
            result.update(image=image,search_url=search,image_hash=digest)
            if not urls:result.update(status='no_candidates',message='이 이미지의 검색 후보가 없습니다. 사이트에 색인된 이미지가 아니거나 단색 표지일 수 있습니다. 다른 페이지·제목으로 검색하세요.')
        for url in urls:
            try:
                metadata=fetch_metadata(url,fetch)
                result['items'].append({'metadata':metadata,'comparison':compare_metadata(base,metadata)})
            except urllib.error.HTTPError as error:
                if error.code in (404,410):continue
                raise
            except (ValueError,TypeError,KeyError):result['failures']+=1
    except urllib.error.HTTPError as error:
        result.update(status='access_required' if error.code in (301,302,303,307,308,401,403,429) else 'unavailable',message='사이트 접근 응답을 확인해야 합니다. 추가 검색과 자동 연결을 중지했습니다.')
    except OSError:
        result.update(status='unavailable',message='검색 사이트 연결을 확인하지 못했습니다.')
    if result['failures'] and result['status']=='checked':result['status']='partial'
    return result
