"""Generate a local reviewable NAS env file. Does not connect to or modify a NAS."""
import argparse
import os
from pathlib import Path,PurePosixPath
import re
import secrets


def prepare(destination,library,downloads,uid,gid,lrr_image,web_image,worker_image=None):
    library_path=PurePosixPath(library);download_path=PurePosixPath(downloads)
    if not library_path.is_absolute() or str(library_path)=='/' or '..' in library_path.parts:
        raise ValueError('A dedicated absolute NAS library path is required')
    if not download_path.is_absolute() or library_path not in download_path.parents or '..' in download_path.parts:
        raise ValueError('Downloads must be a dedicated subdirectory of the new library')
    if not 1<=uid<=2147483647 or not 1<=gid<=2147483647:raise ValueError('Verified positive UID/GID required')
    for value in (library,downloads):
        if any(c in value for c in '\r\n$#\"\'\\') or value.strip()!=value:
            raise ValueError('Path contains env-file control characters')
    for image in (lrr_image,web_image,worker_image):
        if image is not None and not re.fullmatch(r'(?:[a-zA-Z0-9./:_-]+@)?sha256:[0-9a-f]{64}',image):
            raise ValueError('Use a tested immutable image digest, not a mutable tag')
    values={'STUDIO_LIBRARY':library,'STUDIO_DOWNLOADS':downloads,'STUDIO_UID':str(uid),'STUDIO_GID':str(gid),
            'STUDIO_PORT':'43120','STUDIO_LRR_IMAGE':lrr_image,'STUDIO_WEB_IMAGE':web_image}
    if worker_image:values['STUDIO_WORKER_IMAGE']=worker_image
    for key in ('LRR_API_KEY','STUDIO_PASSWORD','STUDIO_PC_WORKER_TOKEN','STUDIO_NAS_WORKER_TOKEN'):
        values[key]=secrets.token_urlsafe(32)
    destination=Path(destination)
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as output:
        output.write('\n'.join(key+'='+value for key,value in values.items())+'\n')
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('output','library','downloads','uid','gid','lrr-image','web-image'):
        parser.add_argument('--'+name,required=True,type=int if name in ('uid','gid') else str)
    parser.add_argument('--worker-image')
    args=vars(parser.parse_args());args['destination']=args.pop('output')
    prepare(**args)
    print('Created local NAS configuration with new secrets; no NAS access or deployment performed.')
