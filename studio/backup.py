"""Consistent SQLite backup / restore to NEW destinations only (stdlib).

Never copies archives, credentials or LANraragi Redis; those need separate backups.
"""
from contextlib import closing
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

TABLES={'works','sources','jobs','settings'}


def inspect_database(connection):
    if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity check failed')
    if connection.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Broken foreign keys')
    tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not TABLES<=tables:raise ValueError('Not a Studio database')
    return {table:connection.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in sorted(TABLES|(tables&{'uploads','user_tags','upload_tags','imports','folder_imports'}))}


def copy_database(source,destination,restore=False):
    source=Path(source).resolve(strict=True);destination=Path(destination).absolute()
    if destination.exists() or destination.is_symlink():raise FileExistsError('Destination must be new; existing files are never overwritten')
    if not destination.parent.is_dir():raise ValueError('Create the dedicated destination directory first')
    fd,name=tempfile.mkstemp(prefix='.studio-backup-',dir=destination.parent)
    os.close(fd);temporary=Path(name)
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original:
            inspect_database(original)
            with closing(sqlite3.connect(temporary)) as copied:
                original.backup(copied)
                if restore:
                    copied.execute("UPDATE jobs SET state='blocked',message='복원된 실행 작업: 원격 작업과 이전 출력을 확인하세요.',updated=? WHERE state='running'",(time.time(),))
                    copied.execute('UPDATE jobs SET lease=NULL,lease_until=NULL')
                    copied.commit()
                counts=inspect_database(copied)
                copied.execute('PRAGMA journal_mode=DELETE')
        with temporary.open('rb') as stream:
            digest=hashlib.file_digest(stream,'sha256').hexdigest()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        # Atomic publish, unlike rename this refuses even a concurrent destination.
        os.link(temporary,destination)
        if os.name=='posix':
            directory_fd=os.open(destination.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
            try:os.fsync(directory_fd)
            finally:os.close(directory_fd)
        return {'sha256':digest,'counts':counts,'mode':'0600'}
    finally:
        temporary.unlink(missing_ok=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['backup','restore'])
    parser.add_argument('source');parser.add_argument('destination')
    args=parser.parse_args()
    print(json.dumps(copy_database(args.source,args.destination,restore=args.operation=='restore'),sort_keys=True))
