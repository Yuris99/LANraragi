# Audio Studio — 동인음성용 파생 서비스

LANraragi Studio에서 분리한 로컬 초기 구현. 원작·판본 관리, 출처별 원본 JSON 이력, 트랙 등록, 브라우저 재생·이어듣기·배속·이전/다음 트랙을 제공한다. [현재 모델 검토](MODEL_REVIEW.md).

## 실행

Python 3.10 이상, 외부 Python 패키지 불필요. 이 worktree의 루트에서:

```powershell
python -B audio-studio/server.py
```

`http://127.0.0.1:43130`을 연다. 기존 만화 서비스의 실행/설정은 필요하지 않다. DB는 이 서비스의 `data/audio.sqlite3`에만 생성된다. `AUDIO_STUDIO_PASSWORD` 환경변수를 지정하면 사용자 `admin`의 Basic 인증을 적용한다. 기본은 loopback 전용 개인 개발 모드다. 네트워크 공개·NAS 배포용 구성은 제공하지 않는다.

1. 원작을 등록한다. 같은 제목으로 새 원작을 만들어도 병합하지 않는다.
2. 원작을 명시 선택한 뒤 만화·번역본·보이스코믹·음성판을 별도 판본으로 등록한다.
3. 판본에서 출처 이름, 원본 ID, HTTPS URL과 원본 메타데이터 JSON을 입력한다. 예: `dlsite`, `RJ01234567`. URL은 저장만 하며 사이트에 접속하지 않는다. 다른 출처의 같은 번호는 별개다. 기존 출처를 다시 입력하면 이전 JSON을 덮어쓰지 않고 기록을 추가한다.
4. 사용 권한이 있는 로컬 음성을 `audio-studio/media/` 아래 직접 준비한 뒤 음성판에 상대 경로로 등록한다. 예: `sample/01.wav`. 서비스는 파일을 수정·이동·삭제하지 않는다. 폴더 밖 경로와 외부를 가리키는 심볼릭 링크는 거부한다.
5. 트랙을 선택해 재생한다. 순서는 등록 순서다. 알려진 길이를 초 단위로 입력하거나 모르면 `0`으로 둔다. 재생 중 약 5초마다, 일시정지 시 위치를 저장한다. 갑작스러운 탭 종료에서는 마지막 몇 초가 유실될 수 있다. 재생 속도는 세션 중 유지된다.

지원 등록 확장자: MP3, M4A, AAC, OGG, OPUS, WAV, FLAC, MP4, WEBM. 실제 디코딩은 브라우저 코덱 지원에 따른다. HTTP 단일 byte-range 및 HEAD를 지원한다. 보이스코믹은 음성 트랙만 재생하며 페이지·영상 타임라인 동기화는 없다. 만화·번역본은 현재 연결/출처 관리용으로, 별도 만화 리더는 포함하지 않는다.

## API

- `GET /api/health`, `/api/works?q=…`, `/api/editions/{id}`, `/api/export`
- `POST /api/works`: `{title}`
- `POST /api/editions`: `{work_id,title,kind,language?,credits?}`
- `POST /api/editions/{id}/sources`: `{provider,external_id,url,raw_metadata}`
- `POST /api/editions/{id}/tracks`: `{title,relative_path,duration?}`
- `POST /api/tracks/{id}/progress`: `{seconds}`
- `GET|HEAD /api/tracks/{id}/media`

출처 원본 메타데이터는 JSON 객체의 중첩 값·문자열·배열을 보존한다. JSON 공백·키 순서·원래 HTTP 응답 바이트를 증명하는 포렌식 보관은 아니다. 내보내기는 원작·판본·모든 출처 이력·트랙·재생 위치를 포함한 JSON이며 음성 파일을 포함하지 않는다. 복원 가져오기는 아직 없다.

## 검증

```powershell
python -B -m unittest discover -s audio-studio/tests -v
node --check audio-studio/web/app.js
```

테스트는 임시 전용 DB와 합성 WAV만 사용한다. 기존 만화 테스트도 별도 worktree 안에서 실행할 수 있다:

```powershell
python -B -m unittest discover -s studio/tests -v
```

## 완료 범위

로컬 초기 구현이다. 외부 사이트 메타데이터 자동 취득, 구매·다운로드, DRM 처리, NAS 접근·배포, 기존 DB 마이그레이션, 다중 사용자, 대규모 목록 페이지 처리, 원작 간 판본 이동·삭제·편집은 포함하지 않는다. 원작 연결을 잘못 선택한 경우 자동 재연결하지 않는다. 내보내기와 스키마를 바탕으로 이동/수정 절차를 별도로 설계해야 한다. 원본 미디어 폴더는 신뢰할 수 있는 로컬 사용자가 관리해야 한다.

상위 프로젝트의 MIT `COPYING`을 따른다.
