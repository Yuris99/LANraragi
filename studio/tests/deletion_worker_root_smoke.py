"""Linux-only root/capability rehearsal; creates and deletes generated temp files."""
import ctypes
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from store import Store
from file_deletion import FileDeletion
from test_file_deletion import archive_bytes,FixtureLRR


def main():
    assert os.name=='posix' and os.geteuid()==0,'Generated root Docker fixture only'
    uid=9001;gid=9001
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);root.chmod(0o711)
        data=root/'data';data.mkdir();os.chown(data,uid,gid)
        originals=root/'originals';(originals/'manga').mkdir(parents=True);(originals/'images').mkdir()
        originals.chmod(0o700)
        uploads=root/'uploads';uploads.mkdir();os.chown(uploads,uid,gid)
        code=root/'private-code';code.mkdir(mode=0o700)
        source=Path(__file__).resolve().parents[1]/'file_deletion.py';private=code/source.name;private.write_bytes(source.read_bytes());private.chmod(0o400)
        spec=importlib.util.spec_from_file_location('private_deletion_worker',private);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        payload=archive_bytes();lrr=FixtureLRR(payload);target=originals/'manga'/lrr.name;target.write_bytes(payload);target.chmod(0)
        other=originals/'manga/Keep.cbz';other.write_bytes(b'Keep unrelated generated work')
        def as_writer(action):
            os.setegid(gid);os.seteuid(uid)
            try:return action()
            finally:os.seteuid(0);os.setegid(0)
        store=as_writer(lambda:Store(data/'studio.db'))
        work=as_writer(lambda:store.create_work('Generated root-only original',lrr_id=lrr.arcid,pages=1))
        api=FileDeletion(store,lrr)
        def cannot_read():
            try:target.read_bytes()
            except PermissionError:return True
            return False
        assert as_writer(cannot_read)
        class Header(ctypes.Structure):_fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
        class Caps(ctypes.Structure):_fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
        libc=ctypes.CDLL(None,use_errno=True);caps=(Caps*2)();caps[0].effective=caps[0].permitted=(1<<1)|(1<<6)|(1<<7)
        assert libc.capset(ctypes.byref(Header(0x20080522,0)),ctypes.byref(caps))==0
        assert libc.prctl(38,1,0,0,0)==0
        worker=module.DeletionWorker(store.path,originals,uploads,uid,gid);worker.tick()
        assert as_writer(api.ready)
        request=as_writer(lambda:api.preview(work['id']))['request']
        as_writer(lambda:api.confirm(work['id'],request['id'],request['filename']))
        worker.tick()
        assert not target.exists() and other.read_bytes()==b'Keep unrelated generated work',as_writer(lambda:api.status(work['id']))
        assert as_writer(lambda:store.get_work(work['id']))['lrr_id'] is None
        assert (data/'studio.db').stat().st_uid==uid
        for name in ('studio.db-wal','studio.db-shm'):
            if (data/name).exists():assert (data/name).stat().st_uid==uid
        assert hashlib.sha256(private.read_bytes()).hexdigest()==worker.code_sha256
        status=Path('/proc/self/status').read_text();assert 'CapEff:\t00000000000000c2' in status and 'NoNewPrivs:\t1' in status
        print('DELETE_ROOT=PASS root-only original, root0400 frozen code, nonroot SQLite owner, exact DAC_OVERRIDE/SETUID/SETGID caps, no-new-privileges, other file preserved')


if __name__=='__main__':main()
