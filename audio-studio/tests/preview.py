"""Disposable browser fixture. No real media or default catalog is loaded."""
import sys
import argparse
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from catalog import Catalog
from server import make_server

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=43131)
    args = parser.parse_args()
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
        work = catalog.create_work('검증용 원작 · 달빛 편지', 'RJ01234567')
        for kind, title, language in [('comic', '달빛 편지 · 만화', 'ja'),
                                      ('translation', '달빛 편지 · 한국어 번역', 'ko'),
                                      ('voice_comic', '달빛 편지 · 보이스코믹', 'ja'),
                                      ('audio', '달빛 편지 · 음성판', 'ja')]:
            catalog.create_edition(work['id'], title, kind, language)
        translated = catalog.create_edition(work['id'], '달빛 편지 · 번역 자막 음성', 'audio', 'ko')
        catalog.set_profile(translated['id'], 'audio', 'subtitles')
        first = catalog.add_track(translated['id'], '01 · 자막 싱크 검증', 'sample.wav', 60)
        with wave.open(str(media / 'short.wav'), 'wb') as output:
            output.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            output.writeframes(b'\x00\x00' * 8000 * 2)
        catalog.add_track(translated['id'], '02 · 마지막 트랙', 'short.wav', 2)
        (media/'sample.ko.srt').write_text('1\n00:00:00,000 --> 00:00:30,000\n첫 번째 번역 자막입니다.\n위치와 크기를 조절해 보세요.\n\n2\n00:00:30,000 --> 00:01:00,000\n두 번째 번역 자막입니다.\n', encoding='utf-8')
        catalog.add_subtitle(first['id'], 'sample.ko.srt')
        ffmpeg = shutil.which('ffmpeg')
        if ffmpeg:
            subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=c=black:s=320x180:r=24:d=3','-f','lavfi','-i','anullsrc=r=8000:cl=mono','-t','3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(media/'video.mp4')], check=True)
            video = catalog.create_edition(work['id'], '달빛 편지 · 영상과 별도 자막', 'audio', 'ko')
            catalog.set_profile(video['id'], 'video', 'subtitles')
            video_track = catalog.add_track(video['id'], '03 · 합성 영상', 'video.mp4', 3)
            catalog.add_subtitle(video_track['id'], 'sample.ko.srt')
        server = make_server(catalog, media, port=args.port)
        print(f'Disposable synthetic preview: http://127.0.0.1:{args.port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
