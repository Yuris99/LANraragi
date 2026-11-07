"""Portable Studio source records and bounded, read-only archive evidence."""
import io
import json
import re
import hashlib
import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from xml.etree import ElementTree
from sources import parse_source,source_family,hitomi_download_metadata

FORMAT='yuri-studio-source'
VERSION=1
MAX_METADATA=128*1024


class ArchiveRanges(io.RawIOBase):
    """ZipFile sees a seekable archive; only bounded ranges ever leave LANraragi."""
    def __init__(self,lrr,arcid):
        if not re.fullmatch('[0-9a-f]{40}',arcid):raise ValueError('작품 파일 식별자를 확인하세요.')
        self.lrr=lrr;self.path='/api/archives/'+arcid+'/download';self.position=0;self.transferred=0;self.requests=0
        with lrr.open(self.path,headers={'Range':'bytes=0-0'}) as response:
            value=re.fullmatch(r'bytes 0-0/([0-9]+)',response.headers.get('Content-Range',''))
            if response.status!=206 or not value or len(response.read(2))!=1:
                raise ValueError('원본 보존을 위한 압축 파일 부분 읽기를 지원하지 않습니다.')
            self.size=int(value[1])
        if not 0<self.size<=2*1024**3:raise ValueError('압축 파일 크기를 확인하세요.')

    def seekable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        position=offset+(self.position if whence==1 else self.size if whence==2 else 0)
        if whence not in (0,1,2) or not 0<=position<=self.size:raise ValueError('압축 파일 위치를 확인하세요.')
        self.position=position;return position

    def read(self,size=-1):
        size=min(self.size-self.position,self.size if size<0 else size)
        if not size:return b''
        if size>512*1024 or self.transferred+size>2*1024**2 or self.requests>=20:
            raise ValueError('원본 정보 읽기 한도를 초과했습니다.')
        start=self.position;end=start+size-1
        with self.lrr.open(self.path,headers={'Range':f'bytes={start}-{end}'}) as response:
            if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{self.size}':
                raise ValueError('압축 파일 부분 응답을 확인하세요.')
            raw=response.read(size+1)
        if len(raw)!=size:raise ValueError('원본 정보의 일부를 읽지 못했습니다.')
        self.position+=size;self.transferred+=size;self.requests+=1
        return raw


def _cbor(raw):
    """Restricted CBOR data reader for EHViewer; no object hooks or executable types."""
    position=0;nodes=0;end=object()
    def take(count):
        nonlocal position
        if count<0 or position+count>len(raw):raise ValueError('손상된 원본 정보입니다.')
        value=raw[position:position+count];position+=count;return value
    def read(depth=0):
        nonlocal nodes
        nodes+=1
        if depth>12 or nodes>20000:raise ValueError('원본 정보 구조 한도를 초과했습니다.')
        first=take(1)[0];major=first>>5;extra=first&31
        if first==255:return end
        if extra<24:length=extra
        elif extra in (24,25,26,27):length=int.from_bytes(take(1<<(extra-24)),'big')
        elif extra==31 and major in (4,5):length=None
        else:raise ValueError('지원하지 않는 원본 정보 형식입니다.')
        if length is not None and major in (2,3,4,5) and length>MAX_METADATA:raise ValueError('원본 정보 크기 한도입니다.')
        if major==0:return length
        if major==1:return -1-length
        if major in (2,3):
            value=take(length);return value.decode('utf-8') if major==3 else value
        if major==4:
            values=[]
            while length is None or len(values)<length:
                value=read(depth+1)
                if value is end:
                    if length is not None:raise ValueError('손상된 원본 정보입니다.')
                    break
                values.append(value)
            return values
        if major==5:
            values={}
            while length is None or len(values)<length:
                key=read(depth+1)
                if key is end:
                    if length is not None:raise ValueError('손상된 원본 정보입니다.')
                    break
                if not isinstance(key,(str,int)) or key in values:raise ValueError('중복되거나 잘못된 원본 정보 항목입니다.')
                value=read(depth+1)
                if value is end:raise ValueError('손상된 원본 정보입니다.')
                values[key]=value
            return values
        if major==7 and extra in (20,21,22):return {20:False,21:True,22:None}[extra]
        raise ValueError('지원하지 않는 원본 정보 항목입니다.')
    value=read()
    if position!=len(raw) or not isinstance(value,dict):raise ValueError('원본 정보 형식을 확인하세요.')
    return value


def ehviewer_identity(raw):
    if not raw or len(raw)>MAX_METADATA:raise ValueError('원본 정보 크기를 확인하세요.')
    if raw[0]>>5==5:
        value=_cbor(raw);kind='cbor'
    else:
        lines=raw.decode('utf-8-sig').splitlines();start=1 if lines and lines[0] in ('VERSION2','VERSION1') else 0
        if len(lines)<start+7:raise ValueError('EHViewer 원본 정보가 불완전합니다.')
        value={'gid':lines[start+1],'token':lines[start+2],'pages':lines[start+6]};kind='text'
    gid=value.get('gid');token=value.get('token');pages=value.get('pages')
    if isinstance(gid,bool) or not re.fullmatch('[1-9][0-9]{0,11}',str(gid)) or not isinstance(token,str) or not re.fullmatch('[A-Za-z0-9]{10}',token):
        raise ValueError('EHViewer 작품 번호와 토큰을 확인하세요.')
    if isinstance(pages,bool) or not str(pages).isdigit() or not 0<int(pages)<=20000:raise ValueError('원본 페이지 수를 확인하세요.')
    return {'provider':'ehentai','external_id':str(gid),'url':f'https://e-hentai.org/g/{gid}/{token}/',
            'pages':int(pages),'origin':{'kind':'embedded-ehviewer','file':'.ehviewer','encoding':kind,
            'sha256':hashlib.sha256(raw).hexdigest(),'url_basis':'gallery-id-and-token','original_site_variant':'unknown'}}


def archive_evidence(lrr,work):
    if not work.get('lrr_id'):return []
    with ArchiveRanges(lrr,work['lrr_id']) as stream,zipfile.ZipFile(stream) as archive:
        infos=archive.infolist()
        if len(infos)>10000:raise ValueError('압축 파일 항목 수 한도입니다.')
        matched=[i for i in infos if PurePosixPath(i.filename).name in ('.ehviewer','ComicInfo.xml','info.json') and not i.is_dir()]
        evidence=[];seen=set()
        for info in matched:
            name=PurePosixPath(info.filename).name
            if name in seen:raise ValueError('원본 정보 파일이 여러 개입니다. 직접 비교가 필요합니다.')
            seen.add(name)
            if info.file_size>MAX_METADATA or info.compress_size>MAX_METADATA or info.flag_bits&1:
                raise ValueError('원본 정보 파일의 크기·암호화를 확인하세요.')
            raw=archive.read(info)
            if name=='.ehviewer':
                try:evidence.append(ehviewer_identity(raw))
                except (ValueError,UnicodeError):
                    evidence.append({'requires_review':True,'issue':'invalid-embedded-format',
                        'origin':{'kind':'embedded-ehviewer','file':'.ehviewer','sha256':hashlib.sha256(raw).hexdigest()}})
            elif name=='info.json':
                try:data=json.loads(raw.decode('utf-8-sig'))
                except (ValueError,UnicodeError):continue
                if not isinstance(data,dict) or data.get('category')!='hitomi' or not isinstance(data.get('source'),str):continue
                source=parse_source(data['source'])
                pages=data.get('count') or work.get('pages')
                pages=pages if type(pages) is int and 0<pages<=20000 else None
                metadata=hitomi_download_metadata(source,data,pages)
                if metadata:
                    evidence.append({**source,'metadata':metadata,'pages':pages,
                        'origin':{'kind':'embedded-gallery-dl','file':'info.json','sha256':hashlib.sha256(raw).hexdigest(),'url_basis':'original-url'}})
            else:
                if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('XML 외부 선언은 허용하지 않습니다.')
                root=ElementTree.fromstring(raw)
                tags=[t.strip() for t in (root.findtext('Genre') or '').split(',') if t.strip()]
                artists=[t.strip() for t in (root.findtext('Writer') or '').split(',') if t.strip()]
                language=(root.findtext('LanguageISO') or '').strip().lower()
                language={'ja':'japanese','jp':'japanese','ko':'korean','en':'english','zh':'chinese'}.get(language,language)
                pages=(root.findtext('PageCount') or '').strip()
                metadata={'title':(root.findtext('Title') or '').strip(),'artists':artists,'languages':[language] if language else [],
                          'tags':tags,'pages':int(pages) if pages.isdigit() and 0<int(pages)<=20000 else None}
                item={'metadata':metadata,'pages':metadata['pages'],'origin':{'kind':'embedded-comicinfo','file':'ComicInfo.xml',
                      'sha256':hashlib.sha256(raw).hexdigest(),'url_basis':'original-url'}}
                url=(root.findtext('Web') or '').strip()
                if url:
                    try:source=parse_source(url)
                    except ValueError:source={}
                    item.update(source)
                evidence.append(item)
        identities={(source_family(e['provider']),e['external_id'],urlsplit(e['url']).path.split('/')[-2] if source_family(e['provider'])=='ehentai' else '') for e in evidence if e.get('url')}
        if len(identities)>1:
            # Preserve all evidence for manual comparison; never pick conflicting identities.
            for item in evidence:item['conflict']=True
        return evidence


def preferred_evidence(evidence):
    if not evidence or any(e.get('conflict') or e.get('requires_review') for e in evidence):return None
    evidence=[e for e in evidence if e.get('url')]
    if not evidence:return None
    # ComicInfo's explicit original host takes precedence over a reconstructed EH URL.
    return next((e for e in evidence if e['origin']['url_basis']=='original-url'),evidence[0])


def source_record(work,evidence=()):
    """Our own versioned format; no account cookies, credentials, or page-access tokens."""
    fields=('title','artists','languages','tags','raw_tags','pages','category','posted','uploader','rating','rating_count')
    sources=[]
    for source in work.get('sources',[]):
        sources.append({k:source[k] for k in ('provider','external_id','url')}|{
            'tags':list(source.get('tags',[])),
            'comments':[{k:c[k] for k in ('id','author','text','posted_at','source_url','collector','fetched_at') if k in c} for c in source.get('comments',[])],
            'metadata':{k:source.get('metadata',{}).get(k) for k in fields if k in source.get('metadata',{})},
            'verification':{'state':source.get('status','manual'),'fetched_at':source.get('fetched')}})
    original=[]
    for item in evidence:
        clean={k:item[k] for k in ('provider','external_id','url','pages','conflict','requires_review','issue') if k in item}
        clean['origin']={k:item.get('origin',{}).get(k) for k in ('kind','file','encoding','sha256','url_basis','original_site_variant') if k in item.get('origin',{})}
        if 'metadata' in item:clean['metadata']={k:item['metadata'][k] for k in fields if k in item['metadata']}
        clean['verification']={'state':'needs_review' if item.get('conflict') or item.get('requires_review') else 'local_metadata','remote_access_verified':False}
        original.append(clean)
    return {'format':FORMAT,'version':VERSION,
            'work':{'local_id':work['id'],'library_id':work.get('lrr_id'),'title':work['title'],'artist':work.get('artist',''),'pages':work.get('pages',0)},
            'sources':sources,'evidence':original,'inspection':{'state':'not_read'}}
