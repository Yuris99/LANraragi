"""Initialize ONLY empty dedicated Docker volumes; never recurse or adopt media."""
import json
import os
from pathlib import Path
import stat

MARKER='.studio-volume.json'
NAMES=('database','thumbnails','plugins','studio','uploads')


def initialize(root,uid,gid):
    if type(uid) is not int or type(gid) is not int or not 1<=uid<=2147483647 or not 1<=gid<=2147483647:
        raise ValueError('UID/GID must be positive integers')
    root=Path(root)
    # Validate all mounts before changing any directory.
    pending=[]
    for name in NAMES:
        directory=root/name
        if directory.is_symlink() or not directory.is_dir():raise ValueError('Expected a dedicated volume: '+name)
        marker=directory/MARKER
        if marker.exists() or marker.is_symlink():
            if marker.is_symlink() or not stat.S_ISREG(marker.stat().st_mode):raise ValueError('Invalid volume marker')
            if json.loads(marker.read_text())!={'format':1,'name':name,'uid':uid,'gid':gid}:
                raise ValueError('Volume identity/UID/GID changed; explicit migration required')
            info=directory.stat()
            if (info.st_uid,info.st_gid)!=(uid,gid):raise ValueError('Volume ownership changed; inspect before startup')
        elif any(directory.iterdir()):
            raise ValueError('Refusing nonempty unmarked volume: '+name)
        else:pending.append((name,directory,marker))
    for name,directory,marker in pending:
        os.chown(directory,uid,gid)
        directory.chmod(0o750)
        with marker.open('x') as output:json.dump({'format':1,'name':name,'uid':uid,'gid':gid},output)
        marker.chmod(0o600);os.chown(marker,uid,gid)
    return len(pending)


if __name__=='__main__':
    count=initialize('/volumes',int(os.environ['STUDIO_UID']),int(os.environ['STUDIO_GID']))
    print('Dedicated volumes ready; initialized:',count)
