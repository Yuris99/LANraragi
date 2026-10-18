"""NAS-local catalog-aware plan from a private copy-review report.

Revalidate candidate files and read a consistent SQLite snapshot. No DB/media
writes. Only a new private plan is written; stdout contains aggregate counts.
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import time
from archive_in_place import directory, stamp

spec=importlib.util.spec_from_file_location('copy_review',Path(__file__).with_name('review-library-storage.py'))
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)


def read_report(path):
    path=Path(path).absolute()
    with directory(path.parent) as parent:
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size>16*1024**2:raise ValueError('report_type_or_size')
            raw=stream.read(16*1024**2+1)
            if stamp(before)!=stamp(os.fstat(stream.fileno())):raise ValueError('report_changed')
    report=json.loads(raw)
    if report.get('operation')!='review' or report.get('errors')!=0:raise ValueError('successful_review_required')
    if not isinstance(report.get('candidates'),list) or len(report['candidates'])>5000:raise ValueError('candidate_limit')
    return report,hashlib.sha256(raw).hexdigest()


def relative_file(root,value):
    if not isinstance(value,str) or not value or '\\' in value or '\0' in value:raise ValueError('relative_path_required')
    parts=value.split('/')
    if any(part in ('','.','..') for part in parts) or PurePosixPath(value).is_absolute():raise ValueError('relative_path_required')
    return Path(root)/value


def locator(path):
    with directory(path.parent) as parent:
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):raise ValueError('regular_file_required')
            value=hashlib.sha1(stream.read(512000)).hexdigest()
            if stamp(before)!=stamp(os.fstat(stream.fileno())):raise ValueError('file_changed')
    return value  # Locator only. Full SHA256 and every page are checked separately.


def preservation(db,row):
    if row is None:return None
    work=dict(row);identity=work['id']
    return {'work':work,
        'sources':[dict(r) for r in db.execute('SELECT * FROM sources WHERE work_id=?',(identity,))],
        'user_tags':[r[0] for r in db.execute('SELECT tag FROM user_tags WHERE work_id=?',(identity,))],
        'local_numbers':[r[0] for r in db.execute('SELECT number FROM work_numbers WHERE work_id=?',(identity,))],
        'jobs':[{k:r[k] for k in r.keys() if k!='lease'} for r in db.execute('SELECT * FROM jobs WHERE work_id=?',(identity,))]}


def build_plan(report,database,library,copies):
    library=Path(library).absolute();copies=Path(copies).absolute()
    if library.resolve().is_relative_to(copies.resolve()) or copies.resolve().is_relative_to(library.resolve()):raise ValueError('disjoint_roots_required')
    grouped=collections.defaultdict(list)
    for item in report['candidates']:
        if not isinstance(item,dict):raise ValueError('candidate_format')
        relative_file(copies,item['copy']);relative_file(library,item['library'])
        for key in ['copy_sha256','library_sha256']:
            if not re.fullmatch('[0-9a-f]{64}',str(item.get(key,''))):raise ValueError('candidate_digest_required')
        grouped[item['copy']].append(item)
    database=Path(database).absolute()
    if database.is_symlink() or not database.is_file() or database.resolve()!=database:raise ValueError('real_database_required')
    summary={'operation':'cleanup-plan','candidate_pairs':len(report['candidates']),'distinct_copies':len(grouped),
             'ambiguous_copies':0,'revalidated_pairs':0,'catalog_pairs':0,'held_copies':0,
             'copies_with_extra_or_different_metadata':0,'copies_with_saved_user_state':0,
             'source_removed':0,'files_moved':0,'database_modified':False}
    if not report.get('errors') and isinstance(report.get('proposed_names'),list):
        summary['reviewed_library_archives']=len(report['proposed_names'])
        summary['reviewed_copy_archives']=report['scanned']-len(report['proposed_names'])
        summary['copies_without_page_match']=summary['reviewed_copy_archives']-len(grouped)
    plan={'format':1,'created':time.time(),'summary':summary,'items':[],
          'execution':'not_implemented_no_delete_or_move','requires_fresh_revalidation':True,
          'required_before_cleanup':['consistent_database_backup','archive_and_extra_metadata_backup',
             'source_tag_comment_and_user_state_merge','old_uuid_and_local_number_redirects',
             'backend_survivor_download_verification','index_reconciliation']}
    db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=10);db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        for copy,items in grouped.items():
            entry={'copy':copy,'holds':[],'targets':[]};plan['items'].append(entry)
            if len({item['library'] for item in items})!=1:
                entry['holds'].append('multiple_library_matches');summary['ambiguous_copies']+=1
            has_state=False;different_metadata=False
            for item in items:
                target={'library':item['library'],'holds':[]};entry['targets'].append(target)
                try:
                    source=relative_file(library,item['library']);duplicate=relative_file(copies,copy)
                    before=[stamp(path.lstat()) for path in [source,duplicate]]
                    original_info=review.inspect_archive(source);copy_info=review.inspect_archive(duplicate)
                    if original_info['archive_sha256']!=item['library_sha256'] or copy_info['archive_sha256']!=item['copy_sha256']:
                        raise ValueError('archive_changed_since_review')
                    if original_info['page_signature']!=copy_info['page_signature']:raise ValueError('page_stream_mismatch')
                    summary['revalidated_pairs']+=1
                    original_id=locator(source);copy_id=locator(duplicate)
                    if before!=[stamp(path.lstat()) for path in [source,duplicate]]:raise ValueError('candidate_changed_during_plan')
                    if original_id==copy_id:target['holds'].append('shared_partial_archive_id')
                    original=db.execute('SELECT * FROM works WHERE lrr_id=?',(original_id,)).fetchone()
                    old=db.execute('SELECT * FROM works WHERE lrr_id=?',(copy_id,)).fetchone()
                    upload=db.execute('SELECT * FROM uploads WHERE sha256=?',(copy_info['archive_sha256'],)).fetchone()
                    if not original:target['holds'].append('survivor_not_in_catalog')
                    elif 'archive_filename' not in original.keys() or original['archive_filename']!=source.name:target['holds'].append('survivor_filename_not_confirmed_sync_first')
                    if not old:target['holds'].append('copy_not_in_catalog')
                    if not upload or upload['stored_name']!=copy or upload['lrr_id']!=copy_id:target['holds'].append('copy_upload_record_not_confirmed')
                    target.update(copy_sha256=copy_info['archive_sha256'],library_sha256=original_info['archive_sha256'],
                                  copy_metadata=copy_info['other_members'],library_metadata=original_info['other_members'],
                                  survivor=preservation(db,original),copy_catalog=preservation(db,old))
                    different_metadata|=copy_info['other_members']!=original_info['other_members']
                    if old:
                        saved=target['copy_catalog']
                        has_state|=bool(old['favorite'] or old['rating'] or old['progress'] or old['last_read'] or saved['user_tags'] or saved['sources'])
                    for saved in [target['survivor'],target['copy_catalog']]:
                        if saved and any(j['state'] in ('queued','running') for j in saved['jobs']):target['holds'].append('active_download_job')
                    if not target['holds']:summary['catalog_pairs']+=1
                except (OSError,ValueError,KeyError,RuntimeError,review.zipfile.BadZipFile) as error:
                    # Do not put private filenames/errors on stdout.
                    target['holds'].append('file_or_report_revalidation_failed')
                entry['holds'].extend(target['holds'])
            if entry['holds']:summary['held_copies']+=1
            summary['copies_with_extra_or_different_metadata']+=int(different_metadata)
            summary['copies_with_saved_user_state']+=int(has_state)
    finally:db.close()
    return plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['prior-report','database','library-root','copies-root','output']:parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    prior=args.prior_report
    if prior=='latest':
        paths=sorted(Path('/prior-reports').glob('copy-review-*.json'))
        if not paths:raise ValueError('prior_report_required')
        prior=paths[-1]
    report,digest=read_report(prior)
    output=Path(args.output).absolute()
    for root in [args.library_root,args.copies_root]:
        if output.is_relative_to(Path(root).resolve()):raise ValueError('output_outside_media_required')
    plan=build_plan(report,args.database,args.library_root,args.copies_root);plan['prior_report_sha256']=digest
    with directory(output.parent) as parent:fd=os.open(output.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
    with os.fdopen(fd,'w') as stream:json.dump(plan,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
    print(json.dumps(plan['summary']|{'private_plan_saved_locally':True},sort_keys=True))


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):
        raise SystemExit('cleanup_plan=failed; media_and_database_unchanged; review_inputs_locally')
