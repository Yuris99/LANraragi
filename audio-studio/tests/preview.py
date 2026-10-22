"""Disposable browser fixture. No real media or default catalog is loaded."""
import sys
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from catalog import Catalog
from server import make_server

if __name__ == '__main__':
    results = HERE / 'test-results'
    results.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='browser-', dir=results) as temp:
        root = Path(temp)
        media = root / 'media'
        media.mkdir()
        with wave.open(str(media / 'sample.wav'), 'wb') as output:
            output.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            output.writeframes(b'\x00\x00' * 8000 * 60)
        catalog = Catalog(root / 'preview.db')
        work = catalog.create_work('검증용 원작 · 달빛 편지')
        for kind, title, language in [('comic', '달빛 편지 · 만화', 'ja'),
                                      ('translation', '달빛 편지 · 한국어 번역', 'ko'),
                                      ('voice_comic', '달빛 편지 · 보이스코믹', 'ja'),
                                      ('audio', '달빛 편지 · 음성판', 'ja')]:
            catalog.create_edition(work['id'], title, kind, language)
        server = make_server(catalog, media)
        print('Disposable synthetic preview: http://127.0.0.1:43130', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
