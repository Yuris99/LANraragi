# NAS 폴더10권 가져오기 화면과 최초 작업자 연결

Studio의 **NAS 폴더** 버튼에서 manga/images 선택 → **다음10권 가져오기**를 누른다. 대기·진행·완료, 추가한 권수, 검사 폴더/기존 사본/문제 수를 표시한다. 요청이 남아 있으면 다음 요청은 막으며 대기 요청은 취소할 수 있다. 창 닫기/새로고침으로 실행 작업이 사라지지 않는다.10권 뒤에는 사용자가 다시 요청해야 한다. 전체 라이브러리를 자동으로 가져오는 반복 작업은 없다.

코드 자동 배포 권한은 원본 폴더를 읽는 권한을 포함하지 않는다. 기존 root-pilot은 일회 실행이었으므로 **이 작업자를 NAS에서 최초 한 번 연결**해야 한다. 웹 코드만 갱신됐고 작업자가 없으면 연결 필요 상태를 표시하고 가져오기를 비활성화한다. 사용자에게 별도 설정이 전혀 필요 없다고 약속하지 않는다. 실제 NAS 설치/배포와 합성 검증을 구분한다.

## 고정 권한

- 대상은 기존 `library-studio-nas-pilot`의 Studio 이미지/비루트 출력 UID:GID와 전용 data/uploads 볼륨뿐이다. 기존에 확인한 NAS 설치는 UID1026:GID100이다. 비밀번호/개인 계정 그룹/SSH 키를 가져오거나 Docker 소켓을 웹 앱에 주지 않는다.
- 별도 NAS-local root 실행기 `/volume1/docker/library-studio-folders`를0700으로 생성한다. 원본 경로는 사용자가 NAS 설치 명령에만 입력하고 NAS 안의0600 파일에 저장한다. GitHub/클라우드로 보내지 않는다. 웹 요청은 경로/명령/이미지/마운트/UID/권한을 지정할 수 없다.
- 원본은 `/nas-library`로 **읽기 전용**, worker는 **network-none/rootfs-RO/메모리256MiB/동시1**이다. root의 DAC_OVERRIDE/SETUID/SETGID만 명시적으로 허용하고 기존 RootSourceIdentity로 원본 open/stat 때만 올린다. DB/CBZ/임시 파일은 앱 UID/GID, 추가 그룹 없이 쓴다. 원본 ACL/chmod/chown/파일 이동·삭제는 하지 않는다.
- 작업자 Python 모듈은 설치기의 불변 커밋/manifest에 고정해 전용 code 디렉터리에 받는다. 이후 앱 자동 배포로 root 실행기를 교체하지 않는다. 실행기·설정·전체 코드 해시는 매번 확인한다. Studio 자신의 `/app` 코드나 웹 DB에서 root 명령을 읽어 실행하지 않는다.
- 기존 LANraragi/Stash/NMLO/Compose/네트워크 설정은 변경하지 않는다. 일회용 새 작업자만 실행한다. source/stat/이미지/권한/볼륨 식별자가 다르면 중단한다. 기존 root-pilot/batch와 같은 파일 잠금으로 동시에 가져오지 않는다.

## 최초 연결 두 단계

먼저 자동 배포로 새 Studio 화면이 적용돼야 한다. 이후 NAS에서 고정 커밋의 [install-folder-queue.sh](install-folder-queue.sh)를 받아 `sudo sh <받은 설치기> install '<승인한 NAS 원본 루트>'`를 실행한다. 기본 preview는 네트워크/Docker/파일 변경이 없다. install은 자신의 고정 커밋에서 검증한 실행기/코드만 받고 원본을 읽기 전용으로 연결해 준비 상태를 기록한다. 아직 요청이 없으면 작품은 가져오지 않는다. 기존 설치 디렉터리는 덮어쓰지 않는다.

DSM의 기존5분 간격 **Studio 업데이트** 작업에서 아래 두 줄을 순서대로 실행하도록 편집한다. 새 NAS 계정/포트/접속 비밀은 필요 없다.

```sh
/bin/sh /volume1/docker/library-studio-deploy/poll.sh tick
/bin/sh /volume1/docker/library-studio-folders/tick.sh
```

그 작업을 한 번 실행하고 Studio → NAS 폴더에 **작업자 연결됨**이 보이면 manga를 선택해10권을 요청한다. 작업자는 다음 예약 실행 때 최대 한 요청만 처리한다. 작업자가 시작하면 권수가 갱신되며 원본 폴더명/이미지는 외부로 보내지 않는다. 연결 표시는 마지막 확인 후11분까지 유효하다. 스케줄러를 끄거나 위 두 번째 줄을 빼면 새 가져오기가 중단된다. 이미 실행 중인10권 작업은 마무리될 수 있다. 웹 앱 코드 배포도 중단하려는 경우에만 첫 번째 줄/전체 작업을 비활성화한다.

## 저장·복구·제한

- CBZ 사본을 Studio uploads 볼륨에 만들고 LANraragi가 색인한다. **사본 저장 완료와 썸네일/읽기 색인 완료는 별개**다. UI의 상태 새로고침은 사본 색인도 다시 확인한다. PNG/JPEG/WebP의 실제 썸네일/3쪽 읽기/파일 다운로드는 합성 자료로 검증한다. 다른 이미지 형식의 업스트림 지원은 별도 확인 대상이다.
- 1개 CBZ 최대512MiB, 폴더당2000페이지, 이미지당64MiB, 검사1000디렉터리 한도다. 생성 사본+검증용 복사본+64MiB의 여유 공간을 요구한다. 원본 복사가 진행 중이면 최소30초 안정화 후 다음 요청에서 다시 검사한다. 변한 원본/심볼릭 링크/너무 큰 항목은 덮어쓰거나 제한을 풀지 않는다.
- 매 배치 전에 SQLite 전체 백업을 data 볼륨 `folder-import-backups`에 남긴다. 생성 CBZ/중복 방지 receipt/검사 cursor는 앱 전용 볼륨에만 기록한다. 백업은 원본/CBZ 자체의 별도 백업을 대신하지 않는다.
- receipt와 해당 요청의 추가 권수를 같은 SQLite 트랜잭션으로 확정한다.3권 뒤 강제 종료되어도 같은 요청은 남은7권까지만 이어간다. 전역 flock을 실제로 획득한 작업자만 실행 중 요청을 복구한다. 살아 있는 이전 작업은 다른 tick이 훔치지 않는다. CBZ 게시 후 receipt 전의 중단은 같은 deterministic SHA로 회복하며 물리 사본을 늘리지 않는다.
- NAS 전원 장애 뒤 Docker가 전용 작업자 컨테이너를 남겼다면 이름/이미지/라벨을 로컬에서 확인해야 한다. 자동으로 알 수 없는 컨테이너를 지우지 않는다. 자체 라벨/이미지가 맞는 실행 중 작업자는 busy로 두며 다른 서비스를 멈추지 않는다.
- SQLite 복원은 과거 queued/running 폴더 작업을 failed로 바꿔 원본 확인 없이 재실행하지 않는다. 백업/상태에는 토큰 임대가 외부로 노출되지 않는다. 작업자 장애/오프라인 때 새로운10권 요청은 막고 기존 요청 기록은 유지한다.

## 재현 검증

`python -B -m unittest discover -s studio/tests -p test_folder_queue.py -v`는 실제 HTTP의 관리자/worker/cross-origin 경계, 경로·한도 조작, idempotency/중복 요청,10+2권/원본 보존,3권 후 중단 회복, receipt+권수 원자성, 큐 취소/연결 만료, 백업·복원 재실행 방지를 검사한다.

`python -B studio/tests/folder_queue_smoke.py`는 별도 `library-studio-folder-queue-check`/loopback43136 스택과 생성한12폴더/36PNG·JPEG·WebP만 사용한다. NAS 경로·신원·이미지·프로젝트 상수만 fixture로 바꾸며 Docker/RO 원본/실제 root worker/SQLite/실제 LANraragi/브라우저는 실행한다. 개인 자료를 사용하거나 NAS에 접속하지 않는다. 실제 NAS 작업자 연결은 사용자 실행 후 별도로 확인해야 한다.
