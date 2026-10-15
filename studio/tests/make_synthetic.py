"""Create a tiny original three-page CBZ; never reads personal media."""
from pathlib import Path
import struct
import zlib
import zipfile


def create_fixture(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/'Synthetic Studio Book.cbz'
    if path.exists():raise FileExistsError('Synthetic fixture already exists; kept unchanged')
    def png(color):
        def chunk(kind,data):
            return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
        return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',320,480,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes(color)*320)*480))+chunk(b'IEND',b'')
    with zipfile.ZipFile(path,'x') as archive:
        for number,color in enumerate([(60,100,180),(100,180,80),(180,80,100)],1):
            archive.writestr(f'{number:02}.png',png(color))
    directory.chmod(0o755);path.chmod(0o644)
    return path


if __name__=='__main__':
    create_fixture(Path(__file__).resolve().parents[1]/'data/library')
    print('Created synthetic three-page CBZ.')
