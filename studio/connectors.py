"""Bounded public comment connectors. No login, cookies, redirects or bypasses."""
from datetime import datetime, timezone
import json
import http.cookiejar
import os
import time
import urllib.request
from sources import parse_source, comments_list

MAX_BYTES=1024*1024
MAX_COMMENTS=100


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_json(url):
    # Default proxy/CA settings remain active. Redirects to login/challenge pages fail.
    handlers=[NoRedirect()]
    cookie_path=os.environ.get('STUDIO_NHENTAI_COOKIES')
    if cookie_path:
        # Standard domain/expiry handling; never print, modify or export the file.
        jar=http.cookiejar.MozillaCookieJar(cookie_path)
        jar.load(ignore_discard=True,ignore_expires=False)
        handlers.append(urllib.request.HTTPCookieProcessor(jar))
    opener=urllib.request.build_opener(*handlers)
    request=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'LibraryStudio/0.1'})
    with opener.open(request,timeout=20) as response:
        if response.headers.get_content_type()!='application/json':
            raise ValueError('댓글 서버가 JSON 대신 로그인 또는 제한 화면을 반환했습니다.')
        raw=response.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('댓글 응답 크기 제한을 초과했습니다.')
    return json.loads(raw)


def fetch_comments(url, fetch=public_json):
    source=parse_source(url)
    if source['provider']!='nhentai':
        return {'status':'unsupported','comments':[],
                'message':'이 출처의 댓글 수집기는 아직 지원하지 않습니다. JSON 가져오기를 사용하세요.'}
    payload=fetch('https://nhentai.net/api/gallery/'+source['external_id']+'/comments')
    if not isinstance(payload,list):raise ValueError('댓글 응답 형식이 변경됐습니다.')
    fetched=time.time();items=[]
    for item in payload[:MAX_COMMENTS]:
        if not isinstance(item,dict) or not isinstance(item.get('body'),str) or not isinstance(item.get('poster'),dict):
            raise ValueError('댓글 항목 형식이 변경됐습니다.')
        if type(item.get('id')) is not int or type(item.get('post_date')) is not int:
            raise ValueError('댓글 ID 또는 작성 시간 형식이 변경됐습니다.')
        author=item['poster'].get('username')
        if not isinstance(author,str):raise ValueError('댓글 작성자 형식이 변경됐습니다.')
        items.append({'id':str(item['id']),'author':author,'text':item['body'],
                      'posted_at':datetime.fromtimestamp(item['post_date'],timezone.utc).isoformat(),
                      'source_url':source['url'],'collector':'nhentai-public-json-v1','fetched_at':str(fetched)})
    return {'status':'limited' if len(payload)>MAX_COMMENTS else 'fetched',
            'comments':comments_list(items),'fetched_at':fetched,
            'message':'최대 100개 댓글을 갱신했습니다. 서버 응답에 없는 기존 댓글은 보존합니다.'}


def public_document(url, payload=None):
    """Public metadata only, fixed call sites, bounded bytes and no redirects/cookies."""
    raw = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=raw, headers={
        'User-Agent':'LibraryStudio/0.1', 'Accept':'application/json,text/html,text/javascript',
        **({'Content-Type':'application/json'} if raw is not None else {})})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
        data = response.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError('metadata_response_limit')
    return data.decode('utf-8')


def source_candidates(number, fetch=None):
    """Check all three independent identities; never link, download, or fall back."""
    import concurrent.futures
    import re
    import urllib.error
    from urllib.parse import quote
    from html import unescape
    if not isinstance(number,str) or not re.fullmatch(r'[0-9]{1,12}',number):
        raise ValueError('확인할 번호는1~12자리 숫자여야 합니다.')
    fetch=fetch or public_document
    def one(provider):
        result={'provider':provider,'number':number,'status':'unavailable','url':None,'title':'','artists':[]}
        try:
            if provider=='ehentai':
                # GID search is supported by the existing upstream E-Hentai plugin.
                search='https://e-hentai.org/?f_search='+quote('gid:'+number,safe='')
                text=fetch(search)
                urls=set(re.findall(r'https://e-hentai\.org/g/'+re.escape(number)+r'/[A-Za-z0-9]+/',unescape(text)))
                if len(urls)!=1:
                    result.update(status='needs_url',message='공개 번호 검색에서 정확한 URL을 확정하지 못했습니다. 원본 URL을 입력하세요.')
                    return result
                url=urls.pop();source=parse_source(url);token=source['url'].rstrip('/').split('/')[-1]
                document=json.loads(fetch('https://api.e-hentai.org/api.php',{'method':'gdata','gidlist':[[int(number),token]],'namespace':1}))
                item=document['gmetadata'][0]
                if str(item.get('gid'))!=number or item.get('error'):raise ValueError('metadata_identity_mismatch')
                title=item.get('title_jpn') or item.get('title')
                artists=[t.split(':',1)[1] for t in item.get('tags',[]) if isinstance(t,str) and t.startswith('artist:')]
            elif provider=='hitomi':
                # Same current metadata host used by the fork's Hitomi plugin.
                text=fetch('https://ltn.gold-usergeneratedcontent.net/galleries/'+number+'.js')
                match=re.fullmatch(r'\s*var\s+galleryinfo\s*=\s*(\{.*\})\s*;?\s*',text,re.S)
                if not match:raise ValueError('metadata_format_changed')
                item=json.loads(match[1])
                if str(item.get('id'))!=number:raise ValueError('metadata_identity_mismatch')
                title=item.get('japanese_title') or item.get('title')
                artists=[a['artist'] for a in item.get('artists',[]) if isinstance(a,dict) and isinstance(a.get('artist'),str)]
                url='https://hitomi.la/galleries/'+number+'.html'
            else:
                item=json.loads(fetch('https://nhentai.net/api/gallery/'+number))
                if str(item.get('id'))!=number:raise ValueError('metadata_identity_mismatch')
                title=item['title'].get('japanese') or item['title'].get('english') or item['title'].get('pretty')
                artists=[t['name'] for t in item.get('tags',[]) if isinstance(t,dict) and t.get('type')=='artist' and isinstance(t.get('name'),str)]
                url='https://nhentai.net/g/'+number+'/'
            if not isinstance(title,str) or not title.strip():raise ValueError('metadata_title_missing')
            result.update(status='found',url=parse_source(url)['url'],title=title[:1000],artists=[a[:150] for a in artists[:20]],message='번호가 같은 후보입니다. 제목·작가를 비교해 선택하세요.')
        except urllib.error.HTTPError as error:
            status='not_found' if error.code in (404,410) else 'access_required' if error.code in (301,302,303,307,308,401,403,429) else 'unavailable'
            result.update(status=status,message='접근 제한 또는 로그인 필요' if status=='access_required' else '해당 번호 응답을 확인하지 못했습니다.')
        except (ValueError,KeyError,TypeError,IndexError,AttributeError,UnicodeError):
            result.update(status='invalid_response',message='메타데이터 형식 또는 작품 번호를 검증하지 못했습니다.')
        except OSError:
            result.update(status='unavailable',message='네트워크 연결을 확인하지 못했습니다.')
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(one,['ehentai','hitomi','nhentai']))
