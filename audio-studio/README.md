# Audio Studio — 동인음성용 파생 서비스

LANraragi Studio에서 분리한 로컬 서비스. 원작·판본 관리, RJ 코드 분류, 출처별 원본 JSON 이력, 음성·영상 재생, 번역 자막과 모바일 감상 화면을 제공한다. [현재 모델 검토](MODEL_REVIEW.md).

## 실행

독립 컨테이너 테스트 구성은 [DOCKER_TEST.md](DOCKER_TEST.md)를 참고한다. Docker 테스트 포트는 43132이며 기존 개발 DB와 별개의 새 볼륨을 사용한다.

Python 3.10 이상, 외부 Python 패키지 불필요. 이 worktree의 루트에서:

```powershell
python -B audio-studio/server.py
```

`http://127.0.0.1:43130`을 연다. 기존 만화 서비스의 실행/설정은 필요하지 않다. DB는 이 서비스의 `data/audio.sqlite3`에만 생성된다. `AUDIO_STUDIO_PASSWORD` 환경변수를 지정하면 사용자 `admin`의 Basic 인증을 적용한다. 기본은 loopback 전용 개인 개발 모드다. 네트워크 공개·NAS 배포용 구성은 제공하지 않는다.

1. 첫 화면에서 작품 카드를 고르고, 원본 음성·번역 자막·영상 중 감상 버전을 선택한 뒤 전체 재생 또는 개별 트랙을 누른다. 등록 화면을 거치지 않고 감상할 수 있다.
2. 새 자료 등록은 상단 작품 추가에서 시작한다. 작품을 등록한 뒤 연결할 원작을 명시 선택해 감상 버전을 추가한다. 같은 제목이나 번호로 자동 병합하지 않는다. 만화·번역본·보이스코믹 등 기존 모델/API도 유지하지만 음성 UI의 기본 등록은 음성/영상 버전이다.
3. 출처 이름, 원본 ID, HTTPS URL과 원본 JSON은 작품 관리 → 파일·출처 관리 → 출처와 원본 기록에서 선택적으로 입력한다. 예: `dlsite`, `RJ01234567`. URL은 저장만 하며 사이트에 접속하지 않는다. 다른 출처의 같은 번호는 별개다. 다시 입력하면 이전 JSON을 덮어쓰지 않고 기록을 추가한다.
4. 사용 권한이 있는 로컬 음성을 `audio-studio/media/` 아래 준비한 뒤 작품 관리의 파일 목록에서 선택해 연결한다. 자막도 트랙별 자막 관리의 목록에서 고른다. 직접 상대 경로를 입력하는 고급 옵션도 남아 있다. 서비스는 파일을 수정·이동·삭제하지 않는다. 폴더 밖 경로와 외부를 가리키는 심볼릭 링크는 거부한다. Docker 테스트는 별도의 읽기 전용 미디어 볼륨을 사용한다.
5. 트랙을 선택하거나 전체 트랙 재생을 누른다. 플레이어의 재생 순서 편집에서 ↑ ↓로 순서를 저장할 수 있다. 알려진 길이를 초 단위로 입력하거나 모르면 `0`으로 둔다. 재생 중 약 5초마다, 일시정지 시 위치를 저장한다. 갑작스러운 탭 종료에서는 마지막 몇 초가 유실될 수 있다.

## RJ 분류와 모바일 감상

화면은 기존 `studio/web`의 Library Studio와 같은 남색/파란 강조색·사이드바·표지 카드·목록 전환 구조를 사용한다. 만화용 동기화·읽기 방향·다운로드 작업 화면은 넣지 않았다. 전체/이어듣기/원본 음성/번역 자막/영상 분류, 제목/RJ/제작진 검색, 제목·RJ·추가순 정렬을 제공한다. 작품별 마지막 버전 선택과 카드/목록 보기 설정은 이 브라우저에 저장한다. 표지를 연결하지 않은 작품은 음표 자리표시자를 보여주며 가짜 표지 이미지를 만들지 않는다.

감상 화면은 버전 선택·전체/이어듣기·트랙 재생·순서 편집만 표시하고 등록/출처/JSON을 숨긴다. 관리는 별도 대화상자에서 연다. 원본 출처 메타데이터와 연결 관계는 UI 개편으로 바뀌지 않는다. Python 개발 서버 43130의 빈 보관함에는 샘플이 있는 Docker 테스트 보관함(43132)으로 가는 명시적 링크가 있으며 자동 이동은 하지 않는다.

- 원작 생성 시 또는 판본 상세의 RJ 코드 연결에서 코드를 직접 지정한다. 다른 원작의 같은 코드는 병합하지 않고 거부한다. 원작 분류용 RJ는 출처별 ID·원본 기록과 분리해 보존한다. 같은 원작에 연결한 원본·번역·영상 판본이 이 분류를 공유한다.
- 판본 상태는 음성/영상과 번역 없음/번역 자막/자막 합성 영상으로 지정한다. 이는 직접 확인한 보유 상태이며 번역 자동 생성 기능이 아니다. 자막 합성 영상은 영상 자체에 자막이 들어간 판본의 분류다.
- SRT/WebVTT 자막은 UTF-8 파일을 `media/` 아래 준비한 뒤 각 트랙의 자막 추가에서 연결한다. 여러 언어·자막 파일을 등록하고 플레이어에서 선택할 수 있다. 자막이 없는 트랙에서는 이전 트랙 자막을 지운다.
- 재생하면 검은 감상 화면이 페이지를 채운다. **브라우저/모니터 전체 화면으로 자동 전환하지 않는다.** 필요한 경우 사용자가 전체 화면 버튼을 직접 누른다. 미지원 브라우저는 페이지 채우기 모드를 유지한다. 조작부 숨기기로 자막과 영상만 남길 수 있다.
- 재생/일시정지, 시간 탐색, ±10초, 배속, 현재 트랙만/전체 연속 재생을 지원한다. 전체 모드의 다음 트랙은 처음부터 재생하며 마지막 트랙에서 멈춘다. 자동 반복은 없다. 수동 선택은 저장된 위치로 이어듣기를 시도한다.
- 자막 표시, 크기, 상하·좌우 위치, 싱크(±120초)를 조절할 수 있다. 양수 시간차는 자막을 늦춘다. 설정은 브라우저에 저장된다. **영상에 박힌 자막은 분리된 텍스트가 아니므로 위치·크기·싱크를 바꿀 수 없다.** 별도 자막을 연결한 경우에만 조절된다.
- 재생 중 Screen Wake Lock을 요청하고 일시정지·종료·창 비활성화 시 해제한다. 다시 화면으로 돌아와 재생 중이면 재요청한다. 실제 승인/거부/해제 상태를 표시하며 수동 재시도할 수 있다. HTTPS(또는 신뢰할 수 있는 localhost), 지원 브라우저와 OS 허용이 필요하고 절전 상태에서 거부될 수 있다. [W3C Screen Wake Lock](https://www.w3.org/TR/screen-wake-lock/).
- 현재 서비스는 PC의 `127.0.0.1`에만 연결된다. **휴대폰에서 접속할 네트워크·HTTPS 배포는 아직 하지 않았다.** 모바일 레이아웃과 실제 휴대폰 접속/OS 동작 검증은 별개의 단계다.

지원 등록 확장자: MP3, M4A, AAC, OGG, OPUS, WAV, FLAC, MP4, WEBM. 실제 디코딩은 브라우저 코덱 지원에 따른다. HTTP 단일 byte-range 및 HEAD를 지원한다. 보이스코믹의 페이지 타임라인 동기화는 없다. 만화·번역본은 현재 연결/출처 관리용으로, 별도 만화 리더는 포함하지 않는다.

## API

- `GET /api/health`, `/api/works?q=…`, `/api/editions/{id}`, `/api/export`
- `GET /api/local-files`: 연결된 미디어 폴더 내 음성·영상·SRT/VTT 파일 선택 목록. 최대 2000개, 읽기 전용, 폴더 밖 링크·설정·DB 파일 제외
- `POST /api/works`: `{title,rj_code?}`
- `POST /api/works/{id}/codes`: `{code}`
- `POST /api/editions`: `{work_id,title,kind,language?,credits?}`
- `POST /api/editions/{id}/sources`: `{provider,external_id,url,raw_metadata}`
- `POST /api/editions/{id}/tracks`: `{title,relative_path,duration?}`
- `POST /api/editions/{id}/profile`: `{media_type,translation}`
- `POST /api/editions/{id}/order`: `{track_ids:[모든 트랙 ID를 원하는 순서로]}`
- `POST /api/tracks/{id}/subtitles`: `{relative_path,language?,label?}`
- `GET /api/subtitles/{id}`: 안전한 일반 텍스트 cue JSON
- `POST /api/tracks/{id}/progress`: `{seconds}`
- `GET|HEAD /api/tracks/{id}/media`

출처 원본 메타데이터는 JSON 객체의 중첩 값·문자열·배열을 보존한다. JSON 공백·키 순서·원래 HTTP 응답 바이트를 증명하는 포렌식 보관은 아니다. 내보내기는 원작·판본·모든 출처 이력·트랙·재생 위치를 포함한 JSON이며 음성 파일을 포함하지 않는다. 복원 가져오기는 아직 없다.

## 검증

```powershell
python -B -m unittest discover -s audio-studio/tests -v
node --check audio-studio/web/app.js
node --check audio-studio/web/player.js
node audio-studio/tests/test_player_core.cjs
node audio-studio/tests/test_player_runtime.cjs
node audio-studio/tests/test_library_core.cjs
node audio-studio/tests/test_library_runtime.cjs
```

테스트는 임시 전용 DB와 합성 WAV만 사용한다. 기존 만화 테스트도 별도 worktree 안에서 실행할 수 있다:

```powershell
python -B -m unittest discover -s studio/tests -v
```

## 완료 범위

로컬 구현이다. 외부 사이트 메타데이터 자동 취득, 구매·다운로드, DRM 처리, 자동 번역/자막 생성, ASS 스타일 자막·영상 내장 자막 추출, NAS 접근·배포, 만화 DB 마이그레이션, 다중 사용자, 대규모 목록 페이지 처리, 원작 간 판본 이동·삭제는 포함하지 않는다. 음성 서비스 전용 DB에만 추가 테이블을 만들며 만화 DB는 참조하지 않는다. 원작 연결을 잘못 선택한 경우 자동 재연결하지 않는다. 내보내기와 스키마를 바탕으로 이동/수정 절차를 별도로 설계해야 한다. 원본 미디어 폴더는 신뢰할 수 있는 로컬 사용자가 관리해야 한다.

상위 프로젝트의 MIT `COPYING`을 따른다.
