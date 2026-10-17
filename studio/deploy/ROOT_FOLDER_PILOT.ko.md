# NAS 원본 폴더 root 읽기 시험

2026-10-17 사용자가 기존 Stash의 실행 상태를 확인한 뒤 root 실행 방식을 승인했다. Stash의 실제 컨테이너 이름은 `PTestManager`이며, 제공된 `docker top` 결과에서 stash 본체 PID30316/UID0/GID0을 확인했다. Studio 컨테이너 설정은 UID1026/GID100이다. Docker 폴더 연결 자체가 읽기 권한을 추가하는 것은 아니다. 특정 Synology ACL 항목까지 확인한 것은 아니며, Stash와 실행 신원이 다른 점은 실제로 확인됐다. Stash와 NMLO는 이 작업에서 수정하지 않는다.

## 적용 범위

새 전용 NAS 계정 생성 없이, 설치된 pilot의 별도 일회성 폴더 작업자만 UID0/GID0으로 시작한다. 상시 Studio/LANraragi의 사용자·이미지·설정·컨테이너는 바꾸거나 재시작하지 않는다. 실제 NAS 실행은 사용자의 SSH 터미널에서 수행한다. 클라우드에는 NAS SSH 자격 증명/TCP grant가 없다.

- 원본 루트 한 개를 `/nas-library`에 읽기 전용으로 연결한다. 읽기 전용 컨테이너 루트, network-none, memory256MiB, no-new-privileges를 유지한다. 호스트/원본 ACL, 소유자, 그룹, 파일은 변경하지 않는다.
- `--cap-drop ALL` 후 DAC_OVERRIDE/SETUID/SETGID만 허용한다. 사용자 계정의 보조 그룹을 전달하지 않고 관리자 그룹101을 추가하지 않는다. Docker 소켓이나 다른 NAS 디렉터리를 컨테이너에 연결하지 않는다.
- 원본 디렉터리 열기/탐색/stat와 이미지 열기만 잠시 effective UID/GID0으로 수행한다. 나머지 선택 기록·잠금·SQLite 사전 백업·DB 작업·임시 파일·CBZ 생성/게시는 현재 앱의 확인된 effective UID/GID로 수행한다. 이미 열린 원본 FD를 사용해 페이지를 복사한다. 임시 권한 문맥을 원본 디렉터리 FD의 yield 이후로 유지하지 않는다.
- 출력 ID는 설치된 Studio의 숫자 `Config.User`에서 가져오고 LANraragi의 LRR_UID/LRR_GID가 일치하는지 선택 키만 확인한다. 비밀 환경 전체를 읽거나 출력하지 않는다. 현재 pilot 출력 ID는1026:100이며 원본 읽기에 그 개인 계정 그룹을 사용하지 않는다. 이는 기존 상시 앱 신원을 전용 계정으로 이전하는 작업은 아니다.
- 기존 Studio data/uploads 볼륨에만 쓴다. root 모듈은 볼륨 최상위 소유자, 기존 DB의 형식/소유자, `.studio-volume.json`의 이름/UID/GID를 확인하고 불일치 시 쓰기 전에 중단한다. 출력 파일을 root 소유로 만든 뒤 chown하는 방식이나 원본에 대한 chmod/chown은 사용하지 않는다.

## 한 폴더만 고정해서 등록

`root-pilot`은 기존 pilot과 동일한128MiB 한도를 사용한다. `manga`에서 자연 정렬상 첫 안정된 작은 폴더를 고른 뒤 NAS-local 선택 기록에 고정한다. 재실행은 같은 폴더만 검사한다. 원본이 바뀌거나 다른 컬렉션을 지정하면 중단하며, 자동으로 다음 작품을 고르지 않는다. 파일 잠금으로 동시 실행을 막는다.

등록 전에 SQLite를 전용 data 볼륨의 `folder-pilot-backups/before-…db`에 일관되게 복사하고 무결성을 확인한다. 백업 실패 시 DB 마이그레이션/CBZ 게시도 중단한다. 이 같은 볼륨의 SQLite 사전 스냅샷은 원본·Redis·업로드·비밀을 포함한 별도 재해복구 백업을 대신하지 않는다. 원본은 NAS 안에서만 처리되며 클라우드/GitHub로 전송하지 않는다. CBZ 사본을 저장하므로 원본 외의 저장 공간이 필요하다.

## 실행 도구

`import-one-folder-root.sh`는 기본 preview이며 명시적 `run`에서만 실행한다. 지정 pilot의 두 기존 컨테이너가 예상 이미지·프로젝트/서비스 라벨·healthy 상태인지, 두 출력 볼륨의 라벨과 실제 mount가 맞는지, LANraragi가 동일 uploads를 RO로 쓰는지 확인한다. 불일치하면 중단한다. 모듈은 검증한 불변 커밋과 SHA256에 고정한다. 이미지 pull, 기존 컨테이너 재생성, `.env.nas` 전송/비밀 재생성은 없다.

```sh
sh import-one-folder-root.sh preview /volumeN/SELECTED_SHARE/ROOT
sh import-one-folder-root.sh run /volumeN/SELECTED_SHARE/ROOT
```

실제 원본 절대 경로는 NAS/사용자 채팅에만 보관한다. 위는 경로 형식 예시다. 일반 계정에서 스크립트를 실행하면 로컬 Docker 명령에서만 sudo 비밀번호를 요청한다. 비밀번호는 NAS 터미널에만 입력한다. 기존 개인 계정 그룹 상속 도구 두 개는 계속 비활성이다. 이전 고정 커밋 명령은 새 root 도구로 대체한다.

Compose로 직접 호출하는 별도 운영 경로는 기존 `compose.folders.yaml` 뒤에 `compose.folders-root.yaml`을 명시적으로 추가하고 일회성 `run --rm --no-deps folder-import`를 사용한다. 루트 overlay만으로 기존 웹/앱 서비스를 root로 바꾸지 않는다. 기존 NAS 파일을 무작정 덮어쓰거나 전체 프로젝트를 up/down하지 않는다.

## 확인 기준과 현재 경계

성공 JSON은 `root_source_reader=true`, `output_uid/gid`, `errors=0`, `imported=1` 또는 재시도 `unchanged=1`과 백업 상대 이름/SHA256을 반환한다. 개인 작품명/페이지 파일명을 출력하지 않는다. Studio의 업로드 목록 → 색인/열기 → 동기화 → 썸네일/리더/폴더 태그/PC 다운로드를 확인한다. 전체326개 등록이나 백그라운드 감시는 켜지 않는다.

클라우드 검증은 실제 NAS 결과와 구분한다. 일반 앱 UID가 거부되는 mode0700/0600 합성 원본을 root 읽기 작업자로 처리하고, 기존 비루트 앱에서 실제 LANraragi 색인/리더/다운로드/태그/DB 쓰기를 확인했다. 생성된 모든 data/uploads 파일·폴더의 UID/GID는1026:100이고 원본 파일/폴더의 바이트·소유자·그룹·권한·수정 시각은 보존됐다. 잘못된 출력 UID는 등록 전에 거부됐다. 두 재시도에도 같은 한 권만 유지됐다. 실제 NAS 결과는 아래 사용자 보고의 범위까지 확인됐다.

## 사용자 보고: NAS 첫 등록 성공

2026-10-17 사용자가 고정 root 도구를 NAS에서 실행했고, 최종 JSON은 operation=root-pilot, errors0, imported1, pages88, fixed_selection=true, root_source_reader=true, output_uid1026/output_gid100, unchanged0이었다. 등록 전 SQLite 백업 상대 이름과 SHA256도 반환됐다. 실제 개인 DB·백업·미디어·작품명은 클라우드/GitHub에 옮기지 않고 이 문서에는 반환 수치만 기록한다.

이 결과는 NAS에서 root 원본 읽기, 고정한 한 폴더의 CBZ 사본 생성, Studio 업로드 기록 저장 및 DB 사전 백업 성공의 증거다. LANraragi 색인 완료, NAS 브라우저 썸네일·88쪽 리더·이어 읽기·PC 다운로드 및 NAS 재시도 결과는 별도로 확인해야 한다. 서비스 이미지/실행 계정/원본 ACL·소유권을 바꾸거나 Stash/NMLO를 변경하는 절차는 실행하지 않았다. 전체 자동 등록은 시작하지 않는다.
