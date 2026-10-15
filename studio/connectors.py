"""Bounded public comment connectors. No login, cookies, redirects or bypasses."""
from datetime import datetime, timezone
import json
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
    opener=urllib.request.build_opener(NoRedirect())
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
