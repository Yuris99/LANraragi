"""Initialize only the two new login-service volumes, never existing app data."""
import json
import os
from pathlib import Path
import secrets
import stat


def initialize(root, uid, gid, data=None):
    if not 1<=uid<=2147483647 or not 1<=gid<=2147483647: raise ValueError('Numeric dedicated UID/GID required')
    root=Path(root)
    for name in ('key','sessions'):
        path=root/name; info=path.lstat()
        if not stat.S_ISDIR(info.st_mode) or path.is_symlink(): raise ValueError('Dedicated volume required')
        marker=path/'.studio-login-volume.json'
        expected={'schema':1,'purpose':name,'uid':uid,'gid':gid}
        if marker.exists():
            if marker.is_symlink() or json.loads(marker.read_text())!=expected: raise ValueError('Volume identity mismatch')
            if (info.st_uid,info.st_gid,info.st_mode&0o777)!=(uid,gid,0o700): raise ValueError('Existing volume permissions differ')
            continue
        if list(path.iterdir()): raise ValueError('Refusing existing unmarked data')
    # Validate both before the first change.
    for name in ('key','sessions'):
        path=root/name;marker=path/'.studio-login-volume.json'
        if marker.exists(): continue
        path.chmod(0o700);os.chown(path,uid,gid)
        if name=='key':
            fd=os.open(path/'token',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as stream:stream.write(secrets.token_urlsafe(48)+'\n')
            os.chown(path/'token',uid,gid)
        fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as stream:json.dump({'schema':1,'purpose':name,'uid':uid,'gid':gid},stream)
        os.chown(marker,uid,gid)
    key=root/'key'/'token';info=key.lstat()
    if not stat.S_ISREG(info.st_mode) or (info.st_uid,info.st_gid,info.st_mode&0o777)!=(uid,gid,0o600):
        raise ValueError('Invalid existing service key')
    if data is not None:
        # Exact new files only. Never scan/read/chown existing DB or other files.
        data=Path(data);info=data.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=uid or data.is_symlink():
            raise ValueError('Verify existing dedicated Studio data volume owner')
        values={'.site-login-token':key.read_text(),'.site-login.json':json.dumps({'schema':1,'url':'http://site-login:8091'})+'\n'}
        for name,value in values.items():
            path=data/name
            if path.exists() or path.is_symlink():
                info=path.lstat()
                if not stat.S_ISREG(info.st_mode) or (info.st_uid,info.st_gid,info.st_mode&0o777)!=(uid,gid,0o600) or path.read_text()!=value:
                    raise ValueError('Existing login connection file differs; no overwrite')
            else:
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'w') as output:output.write(value);output.flush();os.fsync(output.fileno())
                os.chown(path,uid,gid)


if __name__=='__main__':
    os.umask(0o077)
    initialize('/volumes',int(os.environ['STUDIO_UID']),int(os.environ['STUDIO_GID']),'/studio-data')
    print('Dedicated login volumes initialized; existing media and catalog untouched.')
