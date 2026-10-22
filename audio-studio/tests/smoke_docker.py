"""Host-side smoke test; writes synthetic fixtures only to the named test volumes."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'audio-studio-test'
CONTAINER = 'audio-studio-test-audio-1'
MEDIA_VOLUME = PROJECT + '_audio-test-media'
DATA_VOLUME = PROJECT + '_audio-test-data'
BASE = 'http://127.0.0.1:43132'
DEMO_TITLE = '합성 테스트 전용 · 음성·자막·영상'


def docker(*args, **kwargs):
    return subprocess.run(['docker', *args], check=True, capture_output=True, text=True, encoding='utf-8', **kwargs).stdout


def request(path, data=None, headers=None, method=None):
    auth = {}
    password = os.environ.get('AUDIO_STUDIO_PASSWORD', '')
    if password:
        auth['Authorization'] = 'Basic ' + base64.b64encode(('admin:' + password).encode()).decode()
    raw = None if data is None else json.dumps(data, ensure_ascii=False).encode()
    if data is not None:
        auth['Content-Type'] = 'application/json'
    req = urllib.request.Request(BASE + path, data=raw, headers={**auth, **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as response:
        return response.code, response.headers, response.read()


def api(path, data=None):
    code, _, raw = request(path, data)
    if code not in (200, 201):
        raise RuntimeError(f'API failed: {path}, HTTP {code}')
    return json.loads(raw)


def main():
    inspected = json.loads(docker('inspect', CONTAINER))[0]
    assert inspected['Config']['Labels']['com.docker.compose.project'] == PROJECT
    assert inspected['Config']['User'] == '10001:10001'
    assert inspected['HostConfig']['ReadonlyRootfs']
    mounts = {m['Destination']: m for m in inspected['Mounts']}
    assert mounts['/app/data']['Name'] == DATA_VOLUME
    assert mounts['/app/data']['RW']
    assert mounts['/app/media']['Name'] == MEDIA_VOLUME
    assert not mounts['/app/media']['RW']
    bindings = inspected['HostConfig']['PortBindings']['43130/tcp']
    assert bindings == [{'HostIp': '127.0.0.1', 'HostPort': '43132'}]
    for volume in (MEDIA_VOLUME, DATA_VOLUME):
        metadata = json.loads(docker('volume', 'inspect', volume))[0]
        assert metadata['Labels']['com.docker.compose.project'] == PROJECT

    health = api('/api/health')
    assert health['status'] == 'ok' and not health['upstream_access']
    video_b64 = ''
    ffmpeg = shutil.which('ffmpeg')
    results = ROOT / 'test-results'
    results.mkdir(exist_ok=True)
    if ffmpeg:
        with tempfile.TemporaryDirectory(prefix='docker-synthetic-', dir=results) as temp:
            video = Path(temp) / 'sample.mp4'
            subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i',
                            'color=c=black:s=320x180:r=24:d=12', '-f', 'lavfi', '-i',
                            'anullsrc=r=8000:cl=mono', '-t', '12', '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(video)], check=True)
            video_b64 = base64.b64encode(video.read_bytes()).decode()

    # The helper has no network or host mounts. Only this disposable test media
    # volume is writable; the actual audio container retains a read-only mount.
    helper = r'''
import base64, hashlib, json, math, struct, wave
from pathlib import Path
root=Path('/fixtures/synthetic-demo-v1')
marker=root/'.audio-studio-synthetic-v1'
if root.exists() and (not marker.is_file() or marker.read_text() != 'synthetic-only-v1'):
    raise RuntimeError('Unexpected existing fixture directory; refusing to overwrite')
root.mkdir(exist_ok=True)
marker.write_text('synthetic-only-v1')
for name,duration,frequency in [('01-tone.wav',60,440),('02-end.wav',3,660)]:
    samples=b''.join(struct.pack('<h',int(180*math.sin(2*math.pi*frequency*i/8000))) for i in range(8000))
    with wave.open(str(root/name),'wb') as output:
        output.setparams((1,2,8000,0,'NONE','not compressed'))
        output.writeframes(samples*duration)
(root/'sample.ko.srt').write_text('1\n00:00:00,000 --> 00:00:30,000\n\ud569\uc131 \ud14c\uc2a4\ud2b8 \uc790\ub9c9\uc785\ub2c8\ub2e4.\n\uc704\uce58\u00b7\ud06c\uae30\u00b7\uc2f1\ud06c\ub97c \uc870\uc808\ud574 \ubcf4\uc138\uc694.\n\n2\n00:00:30,000 --> 00:01:00,000\n\ub450 \ubc88\uc9f8 \uc790\ub9c9\uc785\ub2c8\ub2e4.\n',encoding='utf-8')
VIDEO = __VIDEO__
if VIDEO:
    (root/'sample.mp4').write_bytes(base64.b64decode(VIDEO))
print(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.suffix in ('.wav','.mp4')}))
'''.replace('__VIDEO__', repr(video_b64))
    hashes = json.loads(docker('run', '--rm', '-i', '--network', 'none', '--user', '0:0', '--read-only',
           '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
           '--mount', f'type=volume,source={MEDIA_VOLUME},target=/fixtures',
           '--entrypoint', 'python', 'lanraragi-audio-studio:local-test', '-B', '-', input=helper))

    works = api('/api/works')['works']
    work = next((w for w in works if w['title'] == DEMO_TITLE), None)
    if work is None:
        work = api('/api/works', {'title': DEMO_TITLE, 'rj_code': 'RJ00000000'})
        for title, translation in [('원본 음성 · 번역 없음', 'none'), ('음성 · 번역 자막', 'subtitles')]:
            edition = api('/api/editions', {'work_id': work['id'], 'title': title, 'kind': 'audio', 'language': 'ko'})
            api(f"/api/editions/{edition['id']}/profile", {'media_type': 'audio', 'translation': translation})
            api(f"/api/editions/{edition['id']}/sources", {'provider': 'local-test', 'external_id': 'synthetic-' + translation,
                'url': 'https://example.invalid/audio-studio/synthetic/' + translation,
                'raw_metadata': {'synthetic': True, 'description': 'Generated tones only; no purchased or personal media'}})
            for title, name, duration in [('01 · 합성 테스트 음', '01-tone.wav', 60), ('02 · 마지막 트랙', '02-end.wav', 3)]:
                track = api(f"/api/editions/{edition['id']}/tracks", {'title': title, 'relative_path': 'synthetic-demo-v1/' + name, 'duration': duration})
                if translation == 'subtitles':
                    api(f"/api/tracks/{track['id']}/subtitles", {'relative_path': 'synthetic-demo-v1/sample.ko.srt', 'language': 'ko', 'label': '합성 한국어 자막'})
        if video_b64:
            edition = api('/api/editions', {'work_id': work['id'], 'title': '검은 영상 · 별도 번역 자막', 'kind': 'audio', 'language': 'ko'})
            api(f"/api/editions/{edition['id']}/profile", {'media_type': 'video', 'translation': 'subtitles'})
            track = api(f"/api/editions/{edition['id']}/tracks", {'title': '12초 합성 검은 영상', 'relative_path': 'synthetic-demo-v1/sample.mp4', 'duration': 12})
            api(f"/api/tracks/{track['id']}/subtitles", {'relative_path': 'synthetic-demo-v1/sample.ko.srt', 'language': 'ko', 'label': '합성 한국어 자막'})

    work = next(w for w in api('/api/works')['works'] if w['id'] == work['id'])
    checked_media = checked_subtitles = 0
    for edition in work['editions']:
        ids = [t['id'] for t in edition['tracks']]
        api(f"/api/editions/{edition['id']}/order", {'track_ids': list(reversed(ids))})
        assert [t['id'] for t in api(f"/api/editions/{edition['id']}")['tracks']] == list(reversed(ids))
        api(f"/api/editions/{edition['id']}/order", {'track_ids': ids})
        for track in edition['tracks']:
            path = f"/api/tracks/{track['id']}/media"
            code, headers, raw = request(path, headers={'Range': 'bytes=0-43'})
            assert code == 206 and len(raw) == 44
            assert headers['Content-Range'].startswith('bytes 0-43/')
            assert request(path, method='HEAD')[0] == 200
            full_code, _, full_raw = request(path)
            assert full_code == 200
            assert hashlib.sha256(full_raw).hexdigest() == hashes[Path(track['relative_path']).name]
            assert request(path, headers={'Range': 'bytes=999999999-'})[0] == 416
            assert api(f"/api/tracks/{track['id']}/progress", {'seconds': 1.25})['resume'] == 1.25
            api(f"/api/tracks/{track['id']}/progress", {'seconds': 0})
            checked_media += 1
            for sub in track['subtitles']:
                cues = api(f"/api/subtitles/{sub['id']}")['cues']
                assert cues[0]['start'] == 0 and '합성' in cues[0]['text']
                checked_subtitles += 1
    for asset in ('/', '/player.js', '/player-core.js', '/player.css'):
        assert request(asset)[0] == 200
    export = api('/api/export')
    assert any(w['id'] == work['id'] for w in export['works'])
    print(json.dumps({'status': 'passed', 'url': BASE, 'editions': len(work['editions']),
                      'media_checks': checked_media, 'subtitle_checks': checked_subtitles,
                      'isolated_volumes': True, 'media_mount_read_only': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
