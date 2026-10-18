"""NAS-local same-directory CBZ renaming, full-byte proof and reversible journal.

No DB access, content rewriting, directory relocation, overwrites or recursive
removal. Network access belongs only to the existing Studio verifier. All private
inputs/journals stay local. Run with unrelated library writers paused.
"""
import argparse
import contextlib
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sources import canonical_archive_name,filename_hints


@contextlib.contextmanager
def directory(path):
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in Path(path).absolute().parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        yield fd
    finally:os.close(fd)


def relative(value):
    if not isinstance(value,str) or not value or '\\' in value or any(ord(c)<32 for c in value):raise ValueError('unsafe_relative_path')
    if value.startswith('/') or any(p in ('','.','..') for p in value.split('/')):raise ValueError('unsafe_relative_path')
    return Path(value)


def read_json(path):
    path=Path(path)
    with directory(path.parent) as parent:fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>16*1024**2:raise ValueError('document_limit')
        return json.load(stream)


def save(path,value,new=False):
    path=Path(path)
    with directory(path.parent) as parent:
        name='.'+uuid.uuid4().hex+'.tmp'
        fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        try:
            with os.fdopen(fd,'w') as stream:
                json.dump(value,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
            if new:os.link(name,path.name,src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False)
            else:os.replace(name,path.name,src_dir_fd=parent,dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:os.unlink(name,dir_fd=parent)
            except FileNotFoundError:pass


def inspect(root,value):
    path=relative(value)
    with directory(Path(root)/path.parent) as parent:
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 0<before.st_size<=2*1024**3:raise ValueError('archive_type_or_limit')
            arcid=hashlib.sha1(stream.read(512000)).hexdigest();stream.seek(0)
            sha=hashlib.file_digest(stream,'sha256').hexdigest()
            after=os.fstat(stream.fileno())
            stamp=lambda i:(i.st_dev,i.st_ino,i.st_size,i.st_mtime_ns,i.st_ctime_ns,i.st_nlink)
            if stamp(before)!=stamp(after):raise ValueError('archive_changed')
            return {'lrr_id':arcid,'sha256':sha,'bytes':before.st_size,'inode':before.st_ino,'device':before.st_dev,'mtime':before.st_mtime_ns}


def destination(work):
    hint=filename_hints(work['archive_filename'])
    title=hint['title'] if work['title'] in (hint['filename'],work['archive_filename']) else work['title']
    # Only registered artists are asserted; an unconfirmed bracket remains a hint.
    source=next((s for p in ('hitomi','ehentai','nhentai') for s in work['sources'] if s['provider']==p),{})
    number=source.get('external_id') or (hint['numbers'][0]['number'] if not hint['ambiguous'] else None)
    name=canonical_archive_name(title,work['artist'],source.get('provider'),number)
    return name[:-4]+f" [L{work['local_number']}].cbz"


def prepare(root,catalog):
    works={};items=[];held={};unchanged=0;seen={};files=[];entries=0
    def hold(reason):held[reason]=held.get(reason,0)+1
    if not isinstance(catalog,list) or len(catalog)>10000:raise ValueError('catalog_limit')
    for work in catalog:
        arcid=work.get('lrr_id')
        if not arcid:continue
        if not re.fullmatch('[0-9a-f]{40}',arcid) or arcid in works:raise ValueError('catalog_identity_conflict')
        if type(work['local_number']) is not int or work['local_number']<1:raise ValueError('catalog_local_number')
        works[arcid]=work
    def walk(path,depth=0):
        nonlocal entries
        if depth>16:raise ValueError('directory_depth_limit')
        with directory(path) as fd:
            for name in sorted(os.listdir(fd)):
                entries+=1
                if entries>20000:raise ValueError('entry_limit')
                if name in ('@eaDir','@tmp','#recycle') or name.startswith('.'):continue
                info=os.stat(name,dir_fd=fd,follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):hold('symlink_preserved');continue
                if stat.S_ISDIR(info.st_mode):walk(path/name,depth+1)
                elif name.lower().endswith('.cbz'):
                    if len(files)>=5000:raise ValueError('archive_limit')
                    files.append((path/name).relative_to(root).as_posix())
    root=Path(root).absolute()
    # Preserve collection boundaries and every existing subfolder.
    for collection in ('manga','images'):
        if (root/collection).exists():walk(root/collection)
    for value in files:
        info=inspect(root,value);arcid=info['lrr_id'];seen.setdefault(arcid,[]).append(value)
        work=works.get(arcid)
        if not work:hold('not_in_catalog');continue
        if not work['artist'].strip():hold('artist_confirmation_required');continue
        basename=Path(value).name
        if work['archive_filename'] not in (basename,Path(basename).stem):hold('catalog_filename_mismatch');continue
        new=(Path(value).parent/destination(work)).as_posix()
        if value==new:unchanged+=1;continue
        if (root/new).exists() or (root/new).is_symlink():hold('destination_exists');continue
        items.append({'old':value,'new':new,'work_id':work['id'],**info})
    # A partial upstream hash alone can never identify a file to rename.
    conflicts={key for key,values in seen.items() if len(values)>1}
    candidates=[item for item in items if item['lrr_id'] not in conflicts]
    for item in items:
        if item['lrr_id'] in conflicts:hold('duplicate_partial_id')
    targets=[i['new'].casefold() for i in candidates]
    if len(targets)!=len(set(targets)):raise ValueError('destination_collision')
    return {'schema':1,'operation_id':uuid.uuid4().hex,'items':candidates,'held':held,'unchanged':unchanged}


def prepare_workspace(root,workspace):
    workspace=Path(workspace);path=workspace/'plan.json'
    if path.exists():plan=read_json(path)
    else:
        plan=prepare(root,read_json(workspace/'catalog.json'));save(path,plan,new=True)
    request={'operation_id':plan['operation_id'],'items':[{k:i[k] for k in ('lrr_id','sha256','bytes')} for i in plan['items']]}
    request_path=workspace/'request.json'
    if request_path.exists():
        if read_json(request_path)!=request:raise ValueError('request_plan_conflict')
    else:save(request_path,request,new=True)
    return plan


def rename_noreplace(fd,old,new):
    libc=ctypes.CDLL(None,use_errno=True)
    fn=getattr(libc,'renameat2',None)
    if fn is not None:result=fn(fd,os.fsencode(old),fd,os.fsencode(new),1)
    elif platform.machine()=='x86_64':result=libc.syscall(316,fd,os.fsencode(old),fd,os.fsencode(new),1)
    else:raise ValueError('atomic_noreplace_unsupported')
    if result!=0:raise OSError(ctypes.get_errno(),'atomic_rename_failed')


def apply(root,plan,proof,journal_path,rollback=False,hook=lambda stage,item:None):
    if plan.get('schema')!=1 or not re.fullmatch('[0-9a-f]{32}',plan.get('operation_id','')) or len(plan['items'])>5000:raise ValueError('plan_format')
    if proof.get('operation_id')!=plan['operation_id']:raise ValueError('backend_proof_required')
    expected={i['lrr_id']:i['sha256'] for i in plan['items']}
    if proof.get('verified')!=expected:raise ValueError('backend_proof_required')
    digest=hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
    journal_path=Path(journal_path)
    with directory(journal_path.parent) as parent:
        lock=os.open('.normalize.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=parent)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        journal=read_json(journal_path) if journal_path.exists() else {'plan_sha256':digest,'states':{}}
        if journal['plan_sha256']!=digest:raise ValueError('journal_plan_conflict')
        save(journal_path,journal)
        changed=0
        # Preflight every entry before the first change; a resumed operation may
        # already have either pathname, but never silently accept two/missing ones.
        for item in plan['items']:
            old,new=relative(item['old']),relative(item['new'])
            if old.parent!=new.parent or old.suffix.lower()!='.cbz' or new.suffix!='.cbz':raise ValueError('same_directory_cbz_only')
            paths=[name for name in (old,new) if os.path.lexists(Path(root)/name)]
            if len(paths)!=1:raise ValueError('ambiguous_or_missing_file')
            actual=inspect(root,paths[0].as_posix())
            if any(actual[k]!=item[k] for k in ('lrr_id','sha256','bytes','inode','device','mtime')):raise ValueError('archive_changed_since_prepare')
            if paths[0]==new and journal['states'].get(item['old']) not in ('pending','renamed','rollback_pending'):raise ValueError('unrecorded_rename')
        for item in plan['items']:
            origin,target=(item['new'],item['old']) if rollback else (item['old'],item['new'])
            a,b=relative(origin),relative(target)
            if not os.path.lexists(Path(root)/a):
                journal['states'][item['old']]='rolled_back' if rollback else 'renamed';save(journal_path,journal);continue
            journal['states'][item['old']]='rollback_pending' if rollback else 'pending';save(journal_path,journal)
            with directory(Path(root)/a.parent) as parent:
                actual=inspect(root,origin)
                if any(actual[k]!=item[k] for k in ('sha256','inode','device','mtime','bytes')):raise ValueError('archive_changed_before_rename')
                hook('before_rename',item)
                rename_noreplace(parent,a.name,b.name);os.fsync(parent)
                hook('after_rename',item)
                if inspect(root,target)['sha256']!=item['sha256']:raise ValueError('archive_changed_after_rename')
            journal['states'][item['old']]='rolled_back' if rollback else 'renamed';save(journal_path,journal);changed+=1
        return {'operation':'rollback' if rollback else 'normalize','renamed':changed,'total':len(plan['items']),'held':plan['held'],'content_rewritten':0}
    finally:os.close(lock)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['prepare','apply','rollback'])
    for key in ('root','workspace'):parser.add_argument('--'+key,required=True)
    args=parser.parse_args();workspace=Path(args.workspace).absolute();root=Path(args.root).absolute()
    if workspace.is_relative_to(root) or root.is_relative_to(workspace):raise ValueError('disjoint_workspace_required')
    if args.operation=='prepare':
        plan=prepare_workspace(root,workspace)
        print(json.dumps({'operation':'prepare','ready':len(plan['items']),'held':plan['held'],'unchanged':plan['unchanged']}))
    else:print(json.dumps(apply(root,read_json(workspace/'plan.json'),read_json(workspace/'proof.json'),workspace/'journal.json',args.operation=='rollback')))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'operation':'failed','error_type':type(error).__name__,'errno':getattr(error,'errno',None)}));sys.exit(1)
