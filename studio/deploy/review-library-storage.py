"""NAS-local read-only duplicate/filename review. Never moves/deletes files or DB rows.

All report paths are local. A matching page stream is only a candidate: metadata,
bookmarks, sources, comments and read progress require separate preservation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile
from archive_in_place import directory, stamp
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sources import filename_hints, canonical_archive_name

IMAGES={'.jpg','.jpeg','.png','.webp','.gif','.avif','.jxl'}
MAX_BYTES=2*1024**3


def natural(name):
    return tuple((1,int(part)) if part.isdigit() else (0,part.casefold()) for part in re.split(r'(\d+)',name))


def inspect_archive(path):
    path=Path(path).absolute()
    with directory(path.parent) as parent:
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size>MAX_BYTES:raise ValueError('archive_limit_or_type')
            digest=hashlib.file_digest(stream,'sha256').hexdigest();stream.seek(0)
            with zipfile.ZipFile(stream) as archive:
                entries=archive.infolist()
                if len(entries)>20000 or sum(e.file_size for e in entries)>MAX_BYTES:raise ValueError('expanded_archive_limit')
                if len({e.filename for e in entries})!=len(entries):raise ValueError('duplicate_member_names')
                images=[];other=[]
                for entry in sorted(entries,key=lambda e:natural(e.filename)):
                    if entry.is_dir():continue
                    if entry.flag_bits&1 or stat.S_ISLNK(entry.external_attr>>16):raise ValueError('encrypted_or_link_member')
                    member=hashlib.sha256();received=0
                    with archive.open(entry) as source:
                        while block:=source.read(256*1024):
                            received+=len(block)
                            if received>entry.file_size:raise ValueError('member_size_mismatch')
                            member.update(block)
                    if received!=entry.file_size:raise ValueError('member_size_mismatch')
                    value=(entry.filename,received,member.hexdigest())
                    (images if Path(entry.filename).suffix.lower() in IMAGES else other).append(value)
            if stamp(before)!=stamp(os.fstat(stream.fileno())):raise ValueError('archive_changed_during_review')
    if not images:raise ValueError('no_image_pages')
    signature=hashlib.sha256(json.dumps([(size,sha) for _,size,sha in images]).encode()).hexdigest()
    return {'archive_sha256':digest,'page_signature':signature,'pages':len(images),'bytes':before.st_size,'other_members':other}


def review(library,copies,max_archives=5000):
    result={'operation':'review','candidates':[],'proposed_names':[],'errors':0,'scanned':0,'source_removed':0,'files_moved':0}
    originals={}
    roots=[Path(value).resolve(strict=True) for value in [library,copies]]
    if roots[0].is_relative_to(roots[1]) or roots[1].is_relative_to(roots[0]):raise ValueError('media_roots_must_be_disjoint')
    visited=0
    for label,root in [('library',Path(library)),('copies',Path(copies))]:
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():raise ValueError('absolute_real_directory_required')
        for current,dirs,files in os.walk(root,followlinks=False):
            visited+=1
            if visited>20000 or len(Path(current).relative_to(root).parts)>16:raise ValueError('directory_scan_limit')
            dirs[:]=sorted(d for d in dirs if d not in {'@eaDir','@tmp','#recycle'} and not (Path(current)/d).is_symlink())
            for name in sorted(files):
                if Path(name).suffix.lower() not in {'.cbz','.zip'}:continue
                result['scanned']+=1
                if result['scanned']>max_archives:raise ValueError('archive_count_limit')
                path=Path(current)/name
                try:info=inspect_archive(path)
                except (OSError,ValueError,RuntimeError,zipfile.BadZipFile):result['errors']+=1;continue
                relative=str(path.relative_to(root));key=info['page_signature']
                if label=='library':
                    originals.setdefault(key,[]).append({'relative':relative,**info})
                    hint=filename_hints(name)
                    number=hint['numbers'][0] if not hint['ambiguous'] else {}
                    result['proposed_names'].append({'relative':relative,'proposed_basename':canonical_archive_name(hint['title'],hint['artist'],number.get('provider'),number.get('number')),'status':'review_only'})
                elif key in originals:
                    for original in originals[key]:
                        result['candidates'].append({'copy':relative,'library':original['relative'],
                            'pages':info['pages'],'same_archive_bytes':info['archive_sha256']==original['archive_sha256'],
                            'copy_sha256':info['archive_sha256'],'library_sha256':original['archive_sha256'],
                            'copy_other_members':info['other_members'],'library_other_members':original['other_members'],
                            'status':'requires_catalog_and_metadata_preservation','delete_authorized_by_report':False})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library-root',required=True)
    parser.add_argument('--copies-root',required=True)
    parser.add_argument('--report',required=True,help='New NAS-local private JSON path, never upload it')
    args=parser.parse_args();report=Path(args.report).absolute()
    # Report output is the only write; choose a dedicated path outside both inputs.
    for root in [args.library_root,args.copies_root]:
        if report.is_relative_to(Path(root).resolve()):raise ValueError('report_must_be_outside_media')
    result=review(args.library_root,args.copies_root)
    with directory(report.parent) as parent:
        fd=os.open(report.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
    with os.fdopen(fd,'w') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
    print(json.dumps({key:result[key] for key in ['operation','scanned','errors','source_removed','files_moved']}|{'page_match_candidates':len(result['candidates']),'report_saved_locally':True}))


if __name__=='__main__':main()
