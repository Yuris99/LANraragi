# Studio 코드 배포 전용 통로

매번 SSH 명령을 붙여 넣는 대신 NAS가 이 포크의 명시적인 배포 요청을 주기적으로 확인한다. 클라우드에 NAS 비밀번호·SSH 키·Docker 소켓을 제공하지 않는다. 새로운 NAS 수신 포트나 공개 서비스, NMLO 원격 실행기 재사용도 필요 없다. NAS에서 `raw.githubusercontent.com:443`으로 나가는 정상 HTTPS 접근만 사용한다.

**구현 준비와 실제 NAS 설치/배포 성공은 별개다.** 최초 설치는 NAS 사용자가 범위를 검토한 뒤 실행한다. 기본 [nas-release.json](nas-release.json)은 비활성이며 작업 등록만으로 현재 서비스를 갱신하지 않는다. 준비 뒤 클라우드가 이 브랜치에 활성 배포 요청을 게시한다. GitHub 게시 성공만으로 NAS 적용 성공을 보고하지 않는다. 결과는 NAS에만 보관하며 개인 자료/DB/로그를 클라우드에 보내지 않는다.

## 권한 범위

- 고정 대상: `/volumeN/docker/library-studio`, 프로젝트 `library-studio-nas-pilot`, 기존 Studio 이미지, 비루트 앱 UID/GID, 전용 data/uploads 볼륨, 읽기 전용 inbox/code, NAS loopback43120.
- NAS에 한 번 설치한 고정 컨트롤러가 SQLite 백업, 코드 해시 검증, 새 코드/overlay 준비, **Studio 하나의** `up -d --no-deps studio`, 건강 확인을 한다. 기존 LANraragi는 재시작하지 않는다.
- 요청에는 schema/enabled/generation/revision/manifest_sha256만 허용한다. 명령·파일 경로·Compose·이미지·포트·마운트·저장소 URL을 지정할 수 없다. 실행 스크립트를 새 배포에서 받아 root로 실행하거나 자동 교체하지 않는다. 실행기 기능 확대는 새 NAS 설치 검토가 필요하다.
- 컨트롤러는 형제 디렉터리 `/volumeN/docker/library-studio-deploy`에 root 소유0700으로 둔다. DSM 작업 자체는 컨테이너 재생성을 위해 root로 실행하지만, 원격으로 쓰는 일반 root 셸/SSH 계정/sudo/Docker API는 제공하지 않는다. Studio에도 Docker 소켓/컨트롤러 디렉터리를 마운트하지 않는다.
- 새 Python은 기존 Studio 권한으로 실행하므로 **Studio DB·업로드 사본과 기존 LANraragi API에 접근할 수 있다.** 원본 NAS 폴더 관리, 임의 NAS 파일/계정/ACL/네트워크 변경, Stash/NMLO 관리, 이미지 변경은 허용하지 않는다. 원본 폴더 일괄 가져오기도 이 통로로 실행하지 않는다.
- 설치 때 Compose3개와 `.env.nas`의 SHA256을 NAS 안에 기록한다. 이후 설정이 바뀌면 멈추며 자동으로 새 범위를 채택하지 않는다. 실제 설정 값·비밀번호는 출력/전송하지 않는다.

## 최초 설정: 설치 한 번과 DSM 작업 하나

1. 이 브랜치의 **검증된 불변 커밋**에서 [install-release-poller.sh](install-release-poller.sh)를 NAS로 받아 `sudo sh <받은 파일> install /volume1/docker/library-studio`로 실행한다. 사용자 안내에는 고정 커밋 URL을 제공한다. 설치기는 고정 커밋/해시로 실행기 두 파일을 검증한다. 기본 `preview`는 네트워크/Docker/NAS 변경 없이 계획만 보여준다.
2. DSM **제어판 → 작업 스케줄러 → 생성 → 예약된 작업 → 사용자 정의 스크립트**에 이름 `Library Studio code update`, 사용자 `root`, 주기 약5분으로 등록한다. 명령은 아래 한 줄이다. 등록 뒤 한 번 **실행**한다.

```sh
/bin/sh /volume1/docker/library-studio-deploy/poll.sh tick
```

사용자가 확인한 DSM7.4/Container Manager24.0.2와 설치 정보를 기준으로 준비했다. DSM 작업 등록 화면 자체는 클라우드에서 검증하지 않았다. 설치기는 계정/SSH/sudoers/방화벽을 바꾸거나 DSM 작업을 자동 생성하지 않는다. 기존 컨트롤러는 덮어쓰지 않는다. 통신 실패로 부분 설치가 남으면 보존하고 검토한다.

이후 클라우드가 테스트한 소스 커밋/manifest SHA와 증가하는 generation을 배포 요청에 게시한다. 모든 브랜치 커밋을 자동 적용하는 방식은 아니다. 배포 요청 파일의 쓰기 권한은 앱 코드 배포 권한이므로 브랜치 쓰기 권한도 보호해야 한다. SHA256은 무결성 검사이며 별도 서명 권한을 대신하지 않는다.

## 중단·상태·실패·복구

권한 철회는 DSM에서 이 작업만 비활성화하면 된다. 실행 중인 갱신은 마무리될 수 있다. NAS 로컬 스위치는 원격 요청으로 다시 켤 수 없다.

```sh
sudo sh /volume1/docker/library-studio-deploy/poll.sh disable
sudo sh /volume1/docker/library-studio-deploy/poll.sh status
```

상태는 generation/revision/적용 결과만 보여준다. 마지막 로그는 전용 비공개 디렉터리의 `last.log`, DB 백업은 Studio data 볼륨 `before-ui-…db`, 코드/Compose 백업은 앱 루트 `ui-update-backup.…`에 남는다. 결과/로그를 외부로 보내지 않는다. 클라우드의 직접 성공 확인에는 추후 별도로 범위를 정한 읽기 전용 상태 연결이 필요하다.

- 같은/오래된 generation은 재실행하지 않는다. 요청 다운로드 전 HTTPS 실패는 다음 주기에 재시도한다. 적용을 시도한 실패/중단 버전은 격리해 반복 백업/재시작을 막는다. 수정 후 더 높은 generation으로 재시도한다.
- 체크섬/import/설정 검증 실패는 재생성 전에 멈춘다. 시작/건강 실패는 이전 코드 복구를 시도하고 자료/DB를 보존한다. DB를 과거로 덮어쓰지 않는다.
- 수동/예약 갱신은 같은 앱 잠금을 쓴다. INT/TERM은 잠금을 정리한다. 강제 종료/전원 장애의 남은 잠금은 자동으로 훔치지 않는다. 작업 종료를 확인한 뒤 NAS 로컬 `poll.sh recover-locks`로 죽은 PID의 전용 잠금만 정리한다. 살아 있는/알 수 없는 PID는 거부한다. 필요하면 로컬 `poll.sh rollback`으로 직전 코드를 복구하고 건강 확인 후 새 generation을 요청한다. 전원 장애 후 완전 자동 복구가 검증됐다고 표시하지 않는다.
- `rollback`은 직전 overlay 또는 최초 이미지 코드로 돌아간다. 원본/DB/업로드/번호 표는 삭제하거나 되감지 않는다. 향후 schema 비호환 변경은 별도 복구 계획이 필요하다.

## 검증 경계

`python -B -m unittest discover -s studio/tests -q`와 `python -B studio/tests/release_poller_smoke.py`를 사용한다. smoke는 기존 합성 자료 전용 `library-studio-folder-root-check`만 다루고 NAS 경로/신원/이미지/포트와 HTTPS 자료를 fixture로 치환한다. JSON parser는 실제 비루트/network-none/RO 컨테이너에서 실행한다. 백업·코드 RO 연결·재생성·건강 확인·실패 격리·중복 억제·철회·되돌리기·LRR 시작 시각/합성 원본/다운로드 SHA 보존은 실제 Docker로 확인한다. 실제 NAS 예약 작업과 사이트 다운로드/댓글 성공은 별도 검증 대상이다.
