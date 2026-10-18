"""NAS-local conversion: sibling CBZ, full verification, then explicit source removal.

Standalone standard-library tool. No database, network, recursive deletion, or
automatic execution through the Studio deployment channel. Plan is the default.
Run with other source writers paused; advisory locks cannot stop unrelated apps.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid
import zipfile

IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif', '.jxl'}
SYSTEM = {'@eaDir', '@tmp', '#recycle'}
FLAGS = os.O_RDONLY | os.O_NOFOLLOW


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


@contextlib.contextmanager
def directory(path):
    path = Path(path).absolute()
    fd = os.open('/', FLAGS | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, FLAGS | os.O_DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextlib.contextmanager
def child_directory(fd, relative):
    child = os.dup(fd)
    try:
        for part in Path(relative).parts:
            next_fd = os.open(part, FLAGS | os.O_DIRECTORY, dir_fd=child)
            os.close(child)
            child = next_fd
        yield child
    finally:
        os.close(child)


def inventory(fd, stable_seconds=30, max_entries=20000):
    entries = {}
    def walk(current, prefix='', depth=0):
        if depth > 16:
            raise ValueError('directory_depth_limit')
        for name in sorted(os.listdir(current)):
            if name in SYSTEM:
                raise ValueError('nas_system_directory_requires_review')
            if '\\' in name or any(ord(c) < 32 for c in name):
                raise ValueError('unsafe_archive_name')
            relative = prefix + name
            info = os.stat(name, dir_fd=current, follow_symlinks=False)
            if len(entries) >= max_entries:
                raise ValueError('entry_limit')
            if time.time() - info.st_mtime < stable_seconds:
                raise ValueError('source_not_stable')
            if stat.S_ISDIR(info.st_mode):
                entries[relative + '/'] = stamp(info)
                with child_directory(current, name) as sub:
                    walk(sub, relative + '/', depth + 1)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                entries[relative] = stamp(info)
            else:
                raise ValueError('link_or_special_file_requires_review')
    walk(fd)
    if not any(Path(name).suffix.lower() in IMAGES for name in entries if not name.endswith('/')):
        raise ValueError('no_images')
    return entries


@contextlib.contextmanager
def source_file(fd, name, expected):
    with child_directory(fd, str(Path(name).parent)) as parent:
        handle = os.open(Path(name).name, FLAGS, dir_fd=parent)
        with os.fdopen(handle, 'rb') as stream:
            if stamp(os.fstat(stream.fileno())) != expected:
                raise ValueError('source_changed')
            yield stream
            if stamp(os.fstat(stream.fileno())) != expected:
                raise ValueError('source_changed')


def digest(stream, output=None):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        result.update(chunk)
        if output is not None:
            output.write(chunk)
    return result.hexdigest()


def verify(fd, archive_file, expected):
    """Read ALL archive and source bytes independently; CRC alone is insufficient."""
    with zipfile.ZipFile(archive_file) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError('archive_file_list_mismatch')
        for name, info in expected.items():
            if name.endswith('/'):
                if not archive.getinfo(name).is_dir():
                    raise ValueError('archive_directory_mismatch')
                continue
            if archive.getinfo(name).file_size != info[3]:
                raise ValueError('archive_size_mismatch')
            with source_file(fd, name, info) as source, archive.open(name) as saved:
                if digest(source) != digest(saved):
                    raise ValueError('archive_content_mismatch')


def convert(book, *, apply=False, delete_source=False, stable_seconds=30):
    """One book only. Existing CBZs are NEVER overwritten or trusted for deletion."""
    book = Path(book).absolute()
    if book.name in SYSTEM or book.name.startswith('.') or book == book.parent:
        raise ValueError('unsafe_book_directory')
    with directory(book.parent) as parent:
        # Serializes our conversions within this parent without adding a lock file.
        if apply:
            fcntl.flock(parent, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with child_directory(parent, book.name) as source:
            identity = os.fstat(source)
            if time.time() - identity.st_mtime < stable_seconds:
                raise ValueError('source_not_stable')
            before = inventory(source, stable_seconds)
            total = sum(value[3] for name, value in before.items() if not name.endswith('/'))
            if total > 2 * 1024**3:
                raise ValueError('book_limit_2GiB')
            result = {'operation': 'apply' if apply else 'plan', 'files': sum(not n.endswith('/') for n in before),
                      'bytes': total, 'verified': False, 'source_removed': False}
            if not apply:
                return result
            target = book.name + '.cbz'
            try:
                os.stat(target, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError('existing_cbz_preserved')
            free = os.fstatvfs(parent)
            if free.f_bavail * free.f_frsize < total + len(before) * 1024 + 64 * 1024**2:
                raise ValueError('insufficient_free_space')
            temporary = '.studio-compress-' + uuid.uuid4().hex + '.part'
            handle = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            # A failed/interrupted .part remains unindexed for local inspection.
            with os.fdopen(handle, 'w+b') as output:
                with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                    for name, info in before.items():
                        if name.endswith('/'):
                            archive.writestr(name, b'')
                        else:
                            with source_file(source, name, info) as original, archive.open(name, 'w', force_zip64=True) as saved:
                                digest(original, saved)
                output.flush()
                os.fsync(output.fileno())
                output.seek(0)
                verify(source, output, before)
                if inventory(source, 0) != before:
                    raise ValueError('source_changed')
                if os.geteuid() == 0:
                    os.fchown(output.fileno(), identity.st_uid, identity.st_gid)
                os.fchmod(output.fileno(), 0o640)
                os.fsync(output.fileno())
                # Hard-link publication is atomic and never replaces another CBZ.
                os.link(temporary, target, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                os.fsync(parent)
                os.unlink(temporary, dir_fd=parent)
                os.fsync(parent)
                result['verified'] = True
                if not delete_source:
                    return result
                # Verify the published inode itself before touching any original.
                saved_fd = os.open(target, FLAGS, dir_fd=parent)
                with os.fdopen(saved_fd, 'rb') as saved:
                    if os.fstat(saved.fileno()).st_ino != os.fstat(output.fileno()).st_ino:
                        raise ValueError('published_archive_changed')
                    verify(source, saved, before)
                if inventory(source, 0) != before or os.stat(book.name, dir_fd=parent, follow_symlinks=False).st_ino != identity.st_ino:
                    raise ValueError('source_changed_before_removal')
                # No rmtree: remove only enumerated, individually unchanged files.
                # A crash leaves a valid durable CBZ and possibly a partial folder;
                # such a folder is NEVER automatically retried against that CBZ.
                for name, info in before.items():
                    if name.endswith('/'):
                        continue
                    with child_directory(source, str(Path(name).parent)) as folder:
                        if stamp(os.stat(Path(name).name, dir_fd=folder, follow_symlinks=False)) != info:
                            raise ValueError('source_changed_during_removal')
                        os.unlink(Path(name).name, dir_fd=folder)
                        os.fsync(folder)
                for name in sorted((n for n in before if n.endswith('/')), key=lambda n: n.count('/'), reverse=True):
                    with child_directory(source, str(Path(name.rstrip('/')).parent)) as folder:
                        current = os.stat(Path(name.rstrip('/')).name, dir_fd=folder, follow_symlinks=False)
                        if (current.st_dev, current.st_ino) != before[name][:2]:
                            raise ValueError('source_directory_changed_during_removal')
                        os.rmdir(Path(name.rstrip('/')).name, dir_fd=folder)
                        os.fsync(folder)
                os.fsync(source)
                os.rmdir(book.name, dir_fd=parent)
                os.fsync(parent)
                result['source_removed'] = True
                return result


def discover(root, collections):
    """Yield book boundaries, never a collection root or nested separate copies."""
    root = Path(root).absolute()
    examined = 0
    def walk(fd, relative, depth):
        nonlocal examined
        examined += 1
        if depth > 16 or examined > 10000:
            raise ValueError('scan_limit')
        names = sorted(os.listdir(fd))
        if any(Path(n).suffix.lower() in IMAGES and stat.S_ISREG(os.stat(n, dir_fd=fd, follow_symlinks=False).st_mode) for n in names):
            yield root / relative
            return
        for name in names:
            if name.startswith('.') or name in SYSTEM:
                continue
            if stat.S_ISDIR(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                with child_directory(fd, name) as sub:
                    yield from walk(sub, relative / name, depth + 1)
    with directory(root) as parent:
        for collection in collections:
            if collection not in {'manga', 'images'}:
                raise ValueError('unsupported_collection')
            with child_directory(parent, collection) as folder:
                # Never treat the collection itself as one giant book.
                for name in sorted(os.listdir(folder)):
                    if name.startswith('.') or name in SYSTEM:
                        continue
                    if stat.S_ISDIR(os.stat(name, dir_fd=folder, follow_symlinks=False).st_mode):
                        with child_directory(folder, name) as sub:
                            yield from walk(sub, Path(collection) / name, 1)


@contextlib.contextmanager
def import_lock(database):
    """Coordinate with the installed RO importer; never migrate or write its DB."""
    database = Path(database).absolute()
    info = database.stat()
    handle = os.open(database.parent / 'folder-pilot.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if os.geteuid() == 0:
            os.fchown(handle, info.st_uid, info.st_gid)
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
            if db.execute("SELECT count(*) FROM folder_jobs WHERE state IN ('queued','running')").fetchone()[0]:
                raise ValueError('finish_or_cancel_existing_folder_jobs_first')
        yield
    finally:
        os.close(handle)


def batch(root, collections, *, apply=False, delete_source=False, stable_seconds=30):
    summary = {'operation': 'apply' if apply else 'plan', 'candidates': 0, 'verified': 0,
               'source_removed': 0, 'bytes': 0, 'errors': 0, 'error_codes': {}}
    # Complete bounded discovery BEFORE any deletion changes directory iteration.
    books = list(discover(root, collections))
    for book in books:
        summary['candidates'] += 1
        try:
            result = convert(book, apply=apply, delete_source=delete_source, stable_seconds=stable_seconds)
            summary['verified'] += int(result['verified'])
            summary['source_removed'] += int(result['source_removed'])
            summary['bytes'] += result['bytes']
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            code = os.strerror(error.errno) if isinstance(error, OSError) and error.errno else str(error) if isinstance(error, ValueError) else 'archive_verification_failed'
            summary['errors'] += 1
            summary['error_codes'][code] = summary['error_codes'].get(code, 0) + 1
            # On any apply failure stop: no unattended continuation after a fault.
            if apply:
                break
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('book', nargs='?', help='one exact image-book directory, not a collection root')
    parser.add_argument('--root', help='NAS-local source root for bounded manga/images discovery')
    parser.add_argument('--collection', choices=['manga', 'images'], action='append')
    parser.add_argument('--database', help='existing Studio DB; required to serialize a batch apply')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--delete-source', action='store_true', help='remove only after full published-CBZ verification')
    args = parser.parse_args()
    if args.delete_source and not args.apply:
        parser.error('--delete-source requires --apply')
    if bool(args.root) == bool(args.book):
        parser.error('supply either one book or --root')
    if args.root and args.apply and not args.database:
        parser.error('batch apply requires --database for importer coordination')
    try:
        lock = import_lock(args.database) if args.apply and args.database else contextlib.nullcontext()
        with lock:
            if args.root:
                result = batch(args.root, args.collection or ['manga'], apply=args.apply, delete_source=args.delete_source)
            else:
                result = convert(args.book, apply=args.apply, delete_source=args.delete_source)
        print(json.dumps(result))
        if result.get('errors'):
            raise SystemExit(1)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        # No personal filenames in log output.
        print(json.dumps({'operation': 'apply' if args.apply else 'plan', 'error':
                          os.strerror(error.errno) if isinstance(error, OSError) and error.errno else str(error) if isinstance(error, ValueError) else 'archive_verification_failed'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
