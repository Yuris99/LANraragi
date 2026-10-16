# LANraragi Studio NAS 시험 배포

이 패키지는 **공식 LANraragi 0.9.81 기반 호환 이미지 + Studio**의 시험 배포용이다. 전체 포크 이미지 빌드는 클라우드 네트워크 정책에 막혀 검증하지 못했다. 외부 사이트 다운로드·자동 댓글 수집의 지원 완료를 의미하지 않는다.

이미지는 코드와 의존성만 포함한다. 개인 미디어, 테스트 DB, 클라우드 개발용 `.env`, VPN 키는 포함하지 않는다. NAS 로그인 비밀은 설치 시 NAS 안에서 새로 생성하며 외부로 전송하지 않는다. 패키지의 `provenance.json`, `images.ids`, `bundle.sha256`에서 이미지와 출처를 확인할 수 있다.

## 검토할 변경

- 새 프로젝트 `library-studio-nas-pilot`, 새 전용 볼륨 5개와 전용 Docker 네트워크.
- 새 루트 `/volumeN/docker/library-studio`, 그 안의 `library`, `library/downloads`, `inbox`, Compose 파일, 비밀 파일 `.env.nas`.
- 확인된 일반 계정의 숫자 UID/GID로 Studio를 실행하고, LANraragi 앱도 같은 계정을 사용한다. 초기화 서비스만 root로 새 볼륨 최상위 권한을 준비한다.
- Studio는 `127.0.0.1:43120`으로만 연결한다. LANraragi 포트는 NAS 외부로 열지 않는다. 기존 NMLO/Stash·개인 원본·기존 권한은 변경하지 않는다.
- `inbox`는 Studio에 읽기 전용 연결한다. 원본을 복사해 등록하며 삭제·이동하지 않는다. 작업 동시 실행 1. 외부 다운로드 작업자는 시작하지 않는다.
- 루트/프로젝트/프로젝트 볼륨이 이미 있으면 설치를 거부한다. 기존 데이터를 채택하거나 재귀 chown하지 않는다.

## 승인 전 확인

NAS 기존 SSH 터미널에서 실행한다. 먼저 패키지를 **설치 루트 이외의** 개인 다운로드 위치에 업로드하고 압축을 푼다. 설치 루트에 먼저 압축을 풀면 신규 경로 보호 검사로 설치가 거부된다.

압축 푼 폴더에서 실제 확인된 UID/GID와 루트를 넣어 다음 **계획만** 출력한다. 예시 계정 값은 자신의 진단 결과로 대체한다.

```sh
sh install-pilot.sh plan /volume1/docker/library-studio 1026 100
sha256sum -c bundle.sha256
```

계획과 실제 NAS 변경 대상이 검토·승인되기 전에는 다음 설치 명령을 실행하지 않는다. sudo 비밀번호는 NAS 터미널에만 입력한다.

## 승인 후 설치

```sh
sudo sh install-pilot.sh install /volume1/docker/library-studio 1026 100
```

이미지 2개를 로드하고 새 경로/볼륨을 준비한 뒤 서비스를 시작한다. 이미지 다운로드·빌드는 NAS에서 수행하지 않는다. 임의 프록시·호스트 네트워크·외부 포트 개방을 사용하지 않는다.

상태 확인:

```sh
cd /volume1/docker/library-studio
sudo docker --host=unix:///var/run/docker.sock compose --env-file .env.nas -p library-studio-nas-pilot -f compose.nas.yaml -f compose.import.yaml -f compose.pilot.yaml ps
```

## PC에서 접속

PC의 새 터미널에서 평소 NAS에 접속하는 대상 주소/사용자를 그대로 사용해 SSH 터널을 연다. 아래 `NAS에_접속할_때_쓰는_대상`은 실제 SSH 대상 문자열로 대체한다. PC 포트가 이미 사용 중이면 앞쪽 포트를 43121 등으로 바꾼다.

```sh
ssh -N -L 43120:127.0.0.1:43120 NAS에_접속할_때_쓰는_대상
```

PC 브라우저에서 `http://127.0.0.1:43120`을 연다. 아이디는 `admin`. 비밀번호는 NAS 안의 `.env.nas`에 있는 `STUDIO_PASSWORD` 값이다. NAS 터미널에서만 확인하고 채팅이나 GitHub로 보내지 않는다. 터널을 유지하는 동안 통신은 기존 SSH 경로로 암호화된다. DSM 리버스 프록시/사설 HTTPS 상시 접속은 별도 검토 대상으로 남긴다.

## 첫 사용 확인

작은 합성/비개인 CBZ 한 권으로 업로드 → 색인 완료 → 읽기 → 이어 읽기 → 태그 편집 → 원본 다운로드를 확인한다. 그 다음 새 inbox에 같은 시험 파일을 넣고 원본 보존과 중복 저장 방지를 확인한다. 개인 라이브러리 전체를 바로 연결하지 않는다. PDF 저장은 지원하나 실제 PDF 렌더링은 별도 확인한다.

## 중단·실패·업그레이드

- 설치 중 실패하면 새 루트·볼륨을 보존한다. 설치 스크립트 재실행은 기존 루트 보호로 거부된다. 원인을 확인한 뒤 기존 프로젝트의 `compose up -d`로 재개하며 `down -v`나 볼륨 삭제로 우회하지 않는다.
- 중단은 위 Compose 명령의 마지막 `ps`를 `stop`으로 바꾼다. 기존 NMLO/Stash는 중단하지 않는다.
- `.env.nas`와 이미지 ID/Compose 보관본을 NAS 안에 보호한다. 업그레이드 전 Studio 쓰기와 LANraragi를 정지하고 새 전용 볼륨 5개, 라이브러리/inbox, 설정을 함께 백업한다. SQLite 백업만으로 업로드 파일이나 Redis가 보존되지 않는다.
- DB 복원은 원본을 덮어쓰지 않고 새 파일로 복원한다. 이전 이미지와 스키마의 호환성 확인 없이 되돌리지 않는다. 파일/볼륨 복원은 NAS 로컬의 별도 신규 대상으로 먼저 검증한다.
- 이 문서는 계획과 안전한 시험 절차다. 실제 NAS 배포/성능/복원 성공은 NAS에서 결과를 확인한 뒤에만 완료로 기록한다.

## Synology NanoCPUs/CFS 오류에서 재개

`NanoCPUs can not be set` 오류는 커널의 CFS quota 미지원으로 Docker가 CPU 사용률 강제 상한을 거부한 것이다. DSM/커널/cgroup 설정을 바꾸지 않는다. 최신 NAS Compose는 CPU quota를 요청하지 않으며 메모리 제한과 다운로드/색인 작업 병렬 수 1을 유지한다. 구형 패키지의 기존 설치에서는 최초 설치 스크립트를 다시 실행하지 않는다.

검토된 `resume-pilot.sh apply /volume1/docker/library-studio`를 sudo로 실행하면 기존 NAS Compose를 `compose.nas.before-cfs.yaml`로 보존하고 CPU 두 줄만 제거한 뒤 같은 프로젝트를 `up -d --force-recreate`로 재개한다. 기존 `.env.nas`와 볼륨을 사용하고 비밀을 재생성하지 않는다. 변경된 디렉터리/백업/CPU 항목 수가 예상과 다르면 중지한다. 구형 Compose에서는 `cpus: 0` overlay가 기존 값을 지우지 못하므로 그 방법은 사용하지 않는다. 복구 후 `ps`에서 LANraragi와 Studio 상태를 확인하고 업로드/읽기/원본 다운로드를 재검증한다.
