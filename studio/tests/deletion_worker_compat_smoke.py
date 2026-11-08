"""Generated-only proof of the deployed non-root capability and deletion path."""
import hashlib
import importlib.util
import os
from pathlib import Path
import resource
import sys
import tempfile
import time

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from store import Store
from file_deletion import WorkerIdentity,FileDeletion,CpuThrottle
from test_file_deletion import archive_bytes,FixtureLRR


def main():
    assert os.getuid()==0,'Generated root Docker fixture only'
    uid=61044;gid=61044
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
        root=Path(temporary);root.chmod(0o711)
        data=root/'data';data.mkdir(mode=0o777);data.chmod(0o777)
        originals=root/'originals';(originals/'manga').mkdir(parents=True);(originals/'images').mkdir();originals.chmod(0o700)
        uploads=root/'uploads';uploads.mkdir()
        code=root/'private-code';code.mkdir(mode=0o700)
        source=Path(__file__).resolve().parents[1]/'file_deletion.py';private=code/source.name
        private.write_bytes(source.read_bytes());private.chmod(0o400)
        spec=importlib.util.spec_from_file_location('compat_private_worker',private);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        payload=archive_bytes();lrr=FixtureLRR(payload)
        target=originals/'manga'/lrr.name;target.write_bytes(payload);target.chmod(0)
        other=originals/'manga/Keep.cbz';other.write_bytes(b'Preserve generated other work')
        identity=WorkerIdentity(uid,gid)
        with identity.database_mode():
            store=Store(data/'studio.db')
            work=store.create_work('Generated retained title',lrr_id=lrr.arcid,pages=1)
            api=FileDeletion(store,lrr)
            for path in (target,private):
                try:path.read_bytes()
                except PermissionError:pass
                else:raise AssertionError('File access privilege leaked into database phase')
        worker=module.DeletionWorker(store.path,originals,uploads,uid,gid,identity)
        worker.tick()
        with identity.database_mode():
            assert api.ready()
            request=api.preview(work['id'])['request']
            api.confirm(work['id'],request['id'],request['filename'])
        worker.tick()
        assert not target.exists() and other.read_bytes()==b'Preserve generated other work'
        with identity.database_mode():
            assert store.get_work(work['id'])['lrr_id'] is None
            assert api.status(work['id'])['request']['state']=='complete'
        for name in ('studio.db','studio.db-wal','studio.db-shm'):
            if (data/name).exists():assert (data/name).stat().st_uid==uid
        assert os.getresuid()==(uid,uid,uid) and resource.getrlimit(resource.RLIMIT_NPROC)==(32,32)
        try:resource.setrlimit(resource.RLIMIT_NPROC,(33,33))
        except (ValueError,PermissionError):pass
        else:raise AssertionError('Hard nproc limit could be raised')
        try:os.setpriority(os.PRIO_PROCESS,0,0)
        except PermissionError:pass
        else:raise AssertionError('Background priority could be raised')
        cpu_start=time.process_time();wall_start=time.monotonic();throttle=CpuThrottle();block=b'Generated hash input'*65536
        while time.process_time()-cpu_start<0.15:
            hashlib.sha256(block).digest();throttle.pause()
        ratio=(time.process_time()-cpu_start)/(time.monotonic()-wall_start)
        assert ratio<0.60,ratio
        assert os.sched_getaffinity(0)=={0}
        assert identity.snapshot()['permitted_caps']==2
        print('DELETE_COMPAT=PASS permanent nonroot DAC, DB DAC disabled, frozen root0400 code, real generated unlink, other file+metadata preserved, nproc hard limit immutable, CPU0/nice19, measured hash CPU ratio='+str(round(ratio,3)))


if __name__=='__main__':main()
