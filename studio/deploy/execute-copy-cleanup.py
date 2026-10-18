"""Execute user-authorized app-copy retirement. Originals always read-only.

Internal prepare/proof/apply stages are run by one NAS-local apply wrapper. No
planning command is required from the operator. Full archive backups, catalog
backup, aliases and a durable retirement journal precede exact copy unlink.
"""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import time
import tempfile
import uuid
from archive_in_place import directory,stamp
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import Store
from backup import copy_database
PHASE='startup'


def phase(value):
    global PHASE
    PHASE=value


spec=importlib.util.spec_from_file_location('cleanup_plan',Path(__file__).with_name('plan-copy-cleanup.py'))
planner=importlib.util.module_from_spec(spec);spec.loader.exec_module(planner)


def write_new(path,value):
    with directory(path.parent) as parent:fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
    with os.fdopen(fd,'w') as output:json.dump(value,output,ensure_ascii=False);output.flush();os.fsync(output.fileno())


def read_private(path):
    with directory(path.parent) as parent:fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>16*1024**2:raise ValueError('private_document_limit')
        return json.load(stream)


def prepare(prior,database,library,copies,workspace):
    report,_=planner.read_report(prior)
    with planner.catalog_snapshot(database,workspace) as snapshot:
        plan=planner.build_plan(report,snapshot,library,copies)
        with sqlite3.connect(snapshot.as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            retired={r['sha256']:dict(r) for r in db.execute('SELECT * FROM copy_retirements')}
    operation={'operation_id':uuid.uuid4().hex,'created':time.time(),'items':[],'held':0,'already_removed':0,'hold_reasons':plan['summary']['hold_reasons']}
    for group in plan['items']:
        if len(group['targets'])!=1:operation['held']+=1;continue
        item=group['targets'][0]
        candidate=next(r for r in report['candidates'] if r['copy']==group['copy'] and r['library']==item['library'])
        old=retired.get(candidate['copy_sha256'])
        if old:
            data=json.loads(old['details'])
            if data['copy']!=group['copy'] or data['library']!=item['library'] or data['library_sha256']!=candidate['library_sha256']:raise ValueError('retirement_journal_conflict')
            if old['state']=='deleted':operation['already_removed']+=1;continue
            operation['items'].append(data);continue
        if group['holds']:operation['held']+=1;continue
        operation['items'].append({'copy':group['copy'],'library':item['library'],
            'sha256':item['copy_sha256'],'library_sha256':item['library_sha256'],
            'old_id':item['copy_catalog']['work']['id'],'work_id':item['survivor']['work']['id'],
            'copy_lrr_id':item['copy_catalog']['work']['lrr_id'],'lrr_id':item['survivor']['work']['lrr_id'],
            'pages':candidate['pages'],
            'copy_bytes':planner.relative_file(copies,group['copy']).stat().st_size,
            'library_bytes':planner.relative_file(library,item['library']).stat().st_size})
    proofs={}
    for item in operation['items']:
        original=planner.relative_file(library,item['library']);info=planner.review.inspect_archive(original)
        if info['archive_sha256']!=item['library_sha256']:raise ValueError('survivor_changed')
        rows=[{'lrr_id':item['lrr_id'],'sha256':item['library_sha256'],'bytes':item['library_bytes']}]
        duplicate=planner.relative_file(copies,item['copy'])
        if duplicate.exists():rows.append({'lrr_id':item['copy_lrr_id'],'sha256':item['sha256'],'bytes':item['copy_bytes']})
        elif item['sha256'] not in retired:raise ValueError('copy_missing_before_retirement')
        for row in rows:
            if row['lrr_id'] in proofs and proofs[row['lrr_id']]!=row:raise ValueError('partial_archive_id_conflict')
            proofs[row['lrr_id']]=row
    operation['proof_request']={'operation_id':operation['operation_id'],'items':list(proofs.values())}
    return operation


def archive_backup(source,destination,expected):
    if destination.is_symlink():raise ValueError('archive_backup_link')
    if destination.exists():
        with destination.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:raise ValueError('archive_backup_conflict')
        return
    temporary=destination.with_name('.'+destination.name+'.'+uuid.uuid4().hex)
    try:
        with directory(source.parent) as parent:fd=os.open(source.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(fd,'rb') as stream,temporary.open('xb') as output:
            before=os.fstat(stream.fileno());digest=hashlib.sha256()
            if not stat.S_ISREG(before.st_mode):raise ValueError('regular_copy_required')
            while block:=stream.read(256*1024):digest.update(block);output.write(block)
            output.flush();os.fsync(output.fileno());os.chmod(temporary,0o600)
            if digest.hexdigest()!=expected or stamp(before)!=stamp(os.fstat(stream.fileno())):raise ValueError('copy_changed_during_backup')
        os.link(temporary,destination)
        with directory(destination.parent) as parent:os.fsync(parent)
    finally:temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def writer_ids(uid,gid):
    old_uid=os.geteuid();old_gid=os.getegid();old_groups=os.getgroups()
    try:
        if old_uid==0:os.setgroups([]);os.setegid(gid);os.seteuid(uid)
        elif old_uid!=uid or old_gid!=gid:raise ValueError('catalog_writer_identity_mismatch')
        yield
    finally:
        if old_uid==0:os.seteuid(old_uid);os.setegid(old_gid);os.setgroups(old_groups)


def open_transaction(database,uid,gid):
    phase('open_catalog_writer')
    with writer_ids(uid,gid):
        db=sqlite3.connect(database,timeout=10);db.row_factory=sqlite3.Row
        try:db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
        except BaseException:db.close();raise
    return db


def save_catalog_backup(database,workspace):
    # SQLite calls stay under the configured app identity, including WAL/SHM.
    scratch=Path(tempfile.mkdtemp(prefix='.copy-cleanup-backup-',dir=Path(database).parent))
    temporary=scratch/'before.db'
    try:
        phase('backup_catalog')
        copy_database(database,temporary)
        with temporary.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        previous=os.geteuid()
        try:
            if os.getuid()==0:os.seteuid(0)
            archive_backup(temporary,workspace/('database-before-'+uuid.uuid4().hex+'.db'),digest)
        finally:
            if os.getuid()==0:os.seteuid(previous)
    finally:
        temporary.unlink(missing_ok=True);scratch.rmdir()


def apply(operation,proof,database,library,copies,workspace,uid,gid,interrupt=None):
    if proof.get('operation_id')!=operation['operation_id'] or not 0<=time.time()-proof.get('created',0)<=600:raise ValueError('backend_proof_expired_or_mismatched')
    for row in operation['proof_request']['items']:
        if proof.get('verified',{}).get(row['lrr_id'])!=row['sha256']:raise ValueError('backend_proof_incomplete')
    backup_root=workspace/'archives';backup_root.mkdir(mode=0o700,exist_ok=True)
    if backup_root.is_symlink():raise ValueError('archive_backup_directory_link')
    required=sum(i['copy_bytes'] for i in operation['items'] if not (backup_root/(i['sha256']+'.cbz')).exists())+Path(database).stat().st_size*len(operation['items'])+16*1024**2
    if shutil.disk_usage(workspace).free<required:raise ValueError('cleanup_backup_space_required')
    result={'operation':'cleanup-apply','removed':0,'merged':0,'held':operation['held'],'already_removed':operation['already_removed'],'originals_modified':0,'hold_reasons':dict(operation.get('hold_reasons',{}))}
    # Same import lock as the fixed NAS folder worker. The original root is RO.
    with directory(Path(database).parent) as parent:fd=os.open('folder-pilot.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=parent)
    with os.fdopen(fd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for item in operation['items']:
            original=planner.relative_file(library,item['library']);duplicate=planner.relative_file(copies,item['copy'])
            original_stamp=stamp(original.lstat());original_info=planner.review.inspect_archive(original)
            if stamp(original.lstat())!=original_stamp:raise ValueError('survivor_changed_during_check')
            if original_info['archive_sha256']!=item['library_sha256']:raise ValueError('survivor_changed_before_unlink')
            exists=duplicate.exists()
            if exists:
                copy_stamp=stamp(duplicate.lstat());copy_info=planner.review.inspect_archive(duplicate)
                if stamp(duplicate.lstat())!=copy_stamp:raise ValueError('copy_changed_during_check')
                if copy_info['archive_sha256']!=item['sha256'] or copy_info['page_signature']!=original_info['page_signature']:raise ValueError('copy_changed_before_unlink')
                archive_backup(duplicate,backup_root/(item['sha256']+'.cbz'),item['sha256'])
            else:
                backup=backup_root/(item['sha256']+'.cbz')
                if not backup.is_file() or backup.is_symlink():raise ValueError('pending_retirement_backup_missing')
                with backup.open('rb') as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest()!=item['sha256']:raise ValueError('pending_retirement_backup_corrupt')
            with writer_ids(uid,gid):
                db=open_transaction(database,uid,gid)
                try:
                    previous=db.execute('SELECT * FROM copy_retirements WHERE sha256=?',(item['sha256'],)).fetchone()
                    if not exists and not previous:raise ValueError('copy_missing_without_journal')
                    if not previous:
                        save_catalog_backup(database,workspace)
                        upload=db.execute('SELECT * FROM uploads WHERE sha256=?',(item['sha256'],)).fetchone()
                        survivor=db.execute('SELECT * FROM works WHERE id=?',(item['work_id'],)).fetchone()
                        if not upload or upload['stored_name']!=item['copy'] or upload['lrr_id']!=item['copy_lrr_id']:raise ValueError('copy_upload_changed')
                        if not survivor or survivor['lrr_id']!=item['lrr_id'] or survivor['archive_filename'] not in {original.name,original.stem}:raise ValueError('survivor_catalog_changed')
                        phase('merge_catalog')
                        if Store.consolidate_copy(db,item['old_id'],item['work_id'],item['sha256'],item['copy_lrr_id'],item):result['merged']+=1
                    elif previous['work_id']!=item['work_id'] or previous['old_work_id']!=item['old_id']:raise ValueError('retirement_journal_conflict')
                    db.commit()
                except ValueError as error:
                    db.rollback()
                    if str(error) in {'manual_metadata_conflict','merged_user_tag_limit','active_download_job','progress_page_mismatch'}:
                        result['held']+=1
                        result['hold_reasons'][str(error)]=result['hold_reasons'].get(str(error),0)+1
                        continue
                    raise
                except BaseException:db.rollback();raise
                finally:db.close()
            if interrupt:interrupt('after_catalog_merge')
            if stamp(original.lstat())!=original_stamp:raise ValueError('survivor_changed_after_merge')
            if exists:
                with directory(duplicate.parent) as parent:
                    if stamp(os.stat(duplicate.name,dir_fd=parent,follow_symlinks=False))!=copy_stamp:raise ValueError('copy_changed_after_merge')
                    phase('unlink_verified_copy')
                    os.unlink(duplicate.name,dir_fd=parent);os.fsync(parent)
                result['removed']+=1
            if interrupt:interrupt('after_copy_unlink')
            with writer_ids(uid,gid):
                db=open_transaction(database,uid,gid)
                try:db.execute("UPDATE copy_retirements SET state='deleted' WHERE sha256=?",(item['sha256'],));db.commit()
                finally:db.close()
            print(json.dumps({'cleanup_progress_removed':result['removed'],'cleanup_progress_merged':result['merged']}),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['prepare','apply'])
    for name in ['database','library-root','copies-root','workspace','manifest']:parser.add_argument('--'+name,required=True)
    parser.add_argument('--prior-report');parser.add_argument('--proof');parser.add_argument('--writer-uid',type=int);parser.add_argument('--writer-gid',type=int)
    args=parser.parse_args();workspace=Path(args.workspace).absolute();manifest=Path(args.manifest).absolute()
    if not workspace.is_dir() or workspace.is_symlink() or not manifest.is_relative_to(workspace):raise ValueError('private_workspace_required')
    if args.operation=='prepare':
        prior=args.prior_report
        if prior=='latest':
            paths=sorted(Path('/prior-reports').glob('copy-review-*.json'))
            if not paths:raise ValueError('prior_review_missing')
            prior=str(paths[-1])
        operation=prepare(prior,args.database,args.library_root,args.copies_root,workspace)
        write_new(manifest,operation)
        write_new(manifest.with_suffix('.request.json'),operation['proof_request'])
        print(json.dumps({'cleanup_prepared':len(operation['items']),'held':operation['held'],'already_removed':operation['already_removed'],'hold_reasons':operation.get('hold_reasons',{})}))
    else:
        if args.writer_uid is None or args.writer_gid is None:raise ValueError('writer_identity_required')
        result=apply(read_private(manifest),read_private(Path(args.proof)),args.database,args.library_root,args.copies_root,workspace,args.writer_uid,args.writer_gid)
        write_new(manifest.with_suffix('.result.json'),result);print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as error:
        print(json.dumps({'operation':'cleanup','status':'stopped','error_type':type(error).__name__,
                          'sqlite_error':getattr(error,'sqlite_errorname',None),'phase':PHASE,
                          'reason':str(error) if isinstance(error,ValueError) and re.fullmatch('[a-z_]{1,80}',str(error)) else 'local_execution_error'}))
        raise SystemExit(1)
