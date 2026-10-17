# 기존 NAS pilot의 Studio 화면 업데이트

현재 설치된 Studio 이미지를 그대로 사용하면서 검토한 Python/Web 소스만 전용 새 디렉터리에 받고 `/app`에 읽기 전용으로 연결한다. 전체 LANraragi 이미지를 다시 빌드하거나 약107MiB 설치 묶음을 다시 옮길 필요가 없다. 새 화면은 부드러운 목록 썸네일 블러와 원본 비율을 보존하는 전체 표지, 작품 열기 시 원본, 상세·리더 쪽별 주소/뒤로가기, 브라우저별 저장 설정, 파일 관리 설명, 실제 사이트 미검증 안내를 포함한다. 이 문서의 준비 완료는 실제 NAS 적용 성공을 뜻하지 않는다.

## 적용 범위

- 대상은 `library-studio-nas-pilot` 프로젝트의 기존 Studio 하나, 앱 루트는 `/volumeN/docker/library-studio`뿐이다. 정해진 기존 이미지·숫자 UID/GID·전용 data/uploads 볼륨·loopback 포트를 확인한다. 다른 설치는 자동으로 추정하지 않고 중단한다.
- 비밀 없는 소스와 SHA256 manifest는 불변 커밋에 고정한다. 새 코드만0755/0644로 준비한다. 원본 미디어·기존 계정·ACL·소유권·Stash·NMLO는 수정하지 않는다.
- SQLite를 먼저 전용 data 볼륨의 `before-ui-…db`로 일관되게 백업한다. 기존 Compose 세 파일은 앱 루트의 비공개 `ui-update-backup.…` 디렉터리에 복사한다. `.env.nas`는 재생성/출력/전송하지 않는다.
- `compose.ui.yaml`을 추가한 뒤 **Studio만** `up -d --no-deps studio`로 재생성한다. 잠깐 접속이 끊긴다. LANraragi는 재시작하지 않는다. 이미지·DB·업로드 볼륨·비밀번호·NAS127.0.0.1:43120 연결은 유지한다.
- 상태 확인 실패 시 직전 코드로 Studio만 되돌린다. DB/업로드를 과거 상태로 덮어쓰지 않으며 생성한 코드·백업을 보존한다. 재해복구용 전체 백업을 대신하지 않는다.

## 실행

공개된 고정 커밋의 `update-studio-ui.sh`를 NAS 임시 파일로 내려받은 뒤 다음 순서로 사용한다. 실제 사용자 명령에는 검증 후 공개한 정확한 커밋 URL을 제공한다.

```sh
sh update-studio-ui.sh plan /volume1/docker/library-studio
sudo sh update-studio-ui.sh apply /volume1/docker/library-studio
```

완료 JSON의 `studio_update=complete`, `folder_archives`, `thumbnail_blur=10px, cover_fit=contain`를 확인하고 기존 PC 브라우저를 새로고침한다. 로그인은 기존 값이다. 목록은 기본 블러이며 작품을 열면 상세/리더 원본이 보인다. 설정의 **목록 썸네일 블러**를 끄고 새로고침해 유지되는지 확인한다. 설정은 브라우저별이다. 새 리더는 쪽마다 주소가 바뀐다. 6→7쪽 이동 후 브라우저 뒤로가기로6쪽, 앞으로가기로7쪽을 확인한다. 리더 새로고침은 같은 쪽을 복원하며 **← 상세**로 작품 상세 주소에 돌아간다. URL fragment를 사용하므로 NAS 포트/프록시 경로를 추가할 필요가 없다.

이미 등록된 NAS 한 권만 보이는 것은 고정 한 권 시험의 결과다. **파일 관리**는 PC 자료 업로드용으로도 쓸 수 있지만, 기존 NAS 폴더는 [별도 계획/이어 등록](ROOT_FOLDER_PILOT.ko.md)으로 가져온다. 번호/URL 입력과 작업 등록은 실제 사이트 다운로드 성공을 뜻하지 않는다. 다운로드 엔진·정상 사이트 접근은 별도 검증이 필요하다.

## 재시작과 되돌리기

Docker 컨테이너 재시작은 코드 연결을 유지한다. 향후 수동 Compose 재생성 시 기존 세 `-f` 뒤에 **`-f compose.ui.yaml`**도 포함해야 새 코드가 유지된다. 실수로 전체 프로젝트를 `down`하거나 볼륨을 지우지 않는다.

```sh
sudo sh update-studio-ui.sh rollback /volume1/docker/library-studio
```

이 명령은 직전 코드로 Studio만 재생성한다. 이전 reviewed overlay가 있으면 이를 복원하고, 최초 적용이었다면 원래 이미지 내부 코드로 되돌린다. 현재 overlay는 보존용 이름으로 옮긴다. DB·업로드·코드·백업은 지우지 않는다. 기존 reviewed overlay의 안전한 읽기 전용 코드 연결이 확인되면 새 apply로 바로 갱신할 수 있다. 알 수 없는 overlay나 다른 mount는 거부한다. 이전 overlay는 비공개 업데이트 백업 디렉터리에 함께 보관한다.

## 검증 경계

격리된 클라우드 Docker 프로젝트와 합성 PNG/JPEG/WebP만 사용해 실제 apply/SQLite 백업/새 코드 import/블러·표지 전체 표시/원본 상세·3쪽 리더/설정 저장/파일 SHA256 보존/rollback을 검증한다. 테스트용 경로·프로젝트·이미지 식별자와 코드 다운로드만 fixture로 치환하고 Docker/Compose/브라우저 동작은 실제로 수행한다. LANraragi 시작 시각이 변하지 않는지도 확인한다. 테스트 이미지는 초기 NAS 소스 체크포인트로 재빌드한 것이므로 NAS의 정확한 기존 바이너리와 동일하다고 주장하지 않는다. 실제 NAS 적용 여부는 사용자 실행 결과로 별도 기록한다.
