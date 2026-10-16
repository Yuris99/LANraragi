# DS718+ 실사용 준비와 배포 검토안

2026-10-16 한국 시간. 이 문서는 배포 후보이며 실제 NAS 배포 승인을 받았다는 뜻이 아니다.

## 현재 판정

- 개발/합성 통합 검증: 통과. 실제 비루트 Studio 이미지 기동, 새 전용 볼륨 초기화/재기동, 읽기/다운로드/설정 보존과 SQLite 백업/복원을 확인했다.
- 전체 LANraragi 포크 이미지: 아직 차단. 관리형 CA secret 전달을 준비했지만 Alpine 호스트가 프록시 CONNECT 403을 반환한다. 공식 0.9.81 의존성 기반 호환성 이미지로 테스트한 결과를 전체 포크 빌드 성공으로 표시하지 않는다.
- 실제 사이트 다운로드/댓글: 미실행. 정상 접근 권한이 확인된 테스트 URL을 요청했으며 아직 받지 않았다. E-Hentai/Hitomi/nHentai 호스트도 현재 HTTP 허용 목록에 없다.
- 실제 DS718+ 시험 배포: 사용자 실행 결과로 LANraragi/Studio 모두 healthy, Windows SSH 터널과 Studio 관리자 로그인까지 확인했다(2026-10-17). CFS quota 오류는 전용 프로젝트 설정 수정으로 복구됐다. NAS 실제 자료 읽기/다운로드와 복원 리허설은 아직 미검증이다. NMLO/Stash와 개인 원본을 변경하지 않았다. 압축 해제 이미지 폴더의 별도 연결안은 [NAS_FOLDERS.ko.md](deploy/NAS_FOLDERS.ko.md)를 참조한다.

## 사이트별 지원 상태와 필요한 접근

| 출처 | 다운로드 구현 | 댓글 구현 | 실제 사이트 결과 | 필요한 입력/조건 |
|---|---|---|---|---|
| E-Hentai | 상류 ehdl 설치 확인. gallery-dl 어댑터의 gallery 추출기 매칭 확인 | 미지원, JSON 가져오기만 가능 | 미실행 | 사용자가 정상 접근 가능한 적법한 테스트 URL. 필요 시 해당 계정의 정상 세션. ehdl 아카이버는 GP를 쓸 수 있으므로 비용/잔액 동의 없이 시험하지 않는다 |
| Hitomi | 상류 다운로드 플러그인 없음. gallery-dl 1.32.16 추출기 매칭/이미지 검증/CBZ 포장 후보 | 미지원, JSON 가져오기만 가능 | 미실행 | 테스트 URL, 정상 사이트/CDN 호스트에 대한 최소 HTTP 허용. 설치 추출기는 ltn.gold-usergeneratedcontent.net 및 이미지 하위 호스트를 사용하나 실제 필요한 호스트는 정상 응답으로 확인 후 요청 |
| nHentai | gallery-dl 추출기 매칭 확인 | 공개 JSON 커넥터, 합성 응답 검증 | 미실행 | 테스트 URL, nhentai.net 허용. 로그인/제한 응답이면 중지. API 경로/형식이 실제와 맞는지 확인 전 지원 완료로 표시하지 않음 |
| ExHentai | 새 gallery-dl 어댑터에서 명시적 비활성화 | 미지원 | 미실행 | 엔진의 인증 부재 시 E-Hentai 자동 대체를 허용하지 않음. 같은 출처 인증/동작을 별도 검증해야 함 |

성적 콘텐츠의 테스트 항목은 모든 등장인물이 성인인 적법한 자료로 한정한다. 개인 라이브러리 전체를 클라우드로 보내지 않는다. 제한·차단 시 다른 출처로 대체하거나 인증서 검증 해제/프록시 우회/브라우저 자동 쿠키 추출을 하지 않는다. 비밀번호/쿠키를 채팅·Git·이미지에 넣지 않는다.

쿠키가 필요한 경우 사용자가 허용한 정상 세션만 대상 장치의 보호 파일에 준비한다. 작업자에는 `STUDIO_ENGINE_COOKIES` 경로를 전달하고, nHentai 댓글에는 `STUDIO_NHENTAI_COOKIES` 경로를 전달할 수 있다. Netscape cookie 파일의 도메인/유효기간은 표준 쿠키 저장소가 처리한다. 파일은 읽기 전용으로 마운트하고 내용을 출력하지 않는다. 쿠키 제공으로 차단 우회 성공을 약속하지 않는다.

## 관리형 빌드의 최소 네트워크 변경

직접 재확인한 두 호스트는 모두 CONNECT 403이다:

- `dl-cdn.alpinelinux.org`: Dockerfile의 Alpine 3.24 패키지 인덱스/패키지.
- `cpanmin.us`: 기존 Perl 의존성 설치 스크립트의 cpanminus 부트스트랩. HTTP 오류를 실행하지 않도록 curl 실패 검사를 추가했다.

기존 허용 목록을 유지한 채 이 두 호스트만 먼저 추가해야 한다. 후속 실패가 나오면 실제 오류를 근거로 추가 호스트를 확인한다. 현재 정책 파일을 편집하거나 다른 미러로 돌아가 차단을 피하지 않는다.

Docker 빌드는 세션 CA를 각 HTTPS 설치 단계에 임시 secret으로 전달한다:

```sh
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -f tools/build/docker/Dockerfile -t lanraragi-studio:lrr-candidate .
docker build -f studio/Dockerfile -t lanraragi-studio:web-candidate .
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -f studio/Dockerfile.worker -t lanraragi-studio:worker-candidate .
```

관리형 데몬을 지정할 때는 런타임 스킬의 `--host=unix:///var/run/docker.sock` 및 endpoint/context/TLS 선택자 제거 지침을 따른다. 프록시와 CA 검증은 유지한다. CA는 이미지 레이어에 복사하지 않는다. `compose.cloud-build.yaml`, `compose.cloud-runtime.yaml`, `compose.worker.cloud.yaml`은 클라우드 검증 전용이다. 내부 `lanraragi`/`studio` 이름만 대소문자 NO_PROXY에 추가하며 외부 사이트/VPN 대상은 제외하지 않는다.

## NAS에 제안하는 구성

- `compose.nas.yaml`: 별도 프로젝트 `library-studio-nas`, Linux amd64 이미지, LANraragi Minion 동시 실행 1, Studio/상류 분리.
- `volume-init`: root로 새 빈 전용 Docker 볼륨 5개만 최상위 소유권을 준비한다. 기존 파일이 있는 무표식 볼륨은 거부하고, 표식과 UID/GID가 달라져도 거부한다. 재귀 chown과 기존 미디어 볼륨 채택은 하지 않는다. 상류 시작 스크립트도 권한 자동 변경 비활성화 시 DB 볼륨을 재귀 chown하지 않고 쓰기 가능 여부만 확인한다.
- 라이브러리 bind 경로는 존재해야 한다. Compose가 오타 경로를 자동 생성하지 않는다. 새 다운로드 하위 디렉터리도 확인된 UID/GID로 미리 준비해야 한다.
- `compose.worker.yaml`: 선택적으로 NAS 작업자 1개. 출력은 새 라이브러리 안의 전용 다운로드 폴더에 둔다. 각 시도별 폴더의 CBZ를 상류가 읽으며, 원본 다운로드 이미지는 삭제하지 않는다. CBZ에 원래 GalleryDL 정보를 별도 gallery-dl-original.json으로 보존하고, 상류 플러그인용 info.json에는 확인한 source URL을 넣는다. GalleryDL 메타데이터 플러그인 설정/수집은 배포 검증에서 확인한다.
- 기본 바인딩은 `127.0.0.1:43120`. PC/다른 장치 접근을 위한 NAS의 사설 HTTPS 경로와 VPN 주소는 아직 미확인이다. 임의 공개/인터페이스 확장을 하지 않는다.
- 현재 자원 상한은 상류 1GiB, Studio 256MiB, 선택 작업자 384MiB다. 설치 메모리와 DSM 여유량 확인 전 동시 기동 용량을 보장하지 않는다. 작업자 병렬 수는 1부터 시작한다. 일부 Synology 커널은 CFS quota가 없어 NAS 구성에서 `cpus` 강제 상한을 요청하지 않는다.

`prepare_nas.py`는 확인된 경로·UID/GID·불변 이미지 digest로 로컬 `.env.nas`를 생성한다. 새 비밀을 별도로 만들며 파일 모드는 0600이다. 기존 파일을 덮어쓰거나 NAS에 연결하지 않는다. 다운로드 경로는 새 라이브러리의 하위여야 한다.

```sh
python studio/prepare_nas.py --output studio/.env.nas \
  --library <확인된-새-절대경로> --downloads <그-경로의-다운로드-하위경로> \
  --uid <확인된-UID> --gid <확인된-GID> \
  --lrr-image <검증된-불변-digest> --web-image <검증된-불변-digest> \
  --worker-image <검증된-불변-digest>
docker compose --env-file studio/.env.nas -f studio/compose.nas.yaml config --quiet
```

꺾쇠 항목은 미확인 값이며 실행 가능한 최종 배포 명령으로 취급하지 않는다. 전체 포크 이미지와 실제 환경 정보를 확보한 뒤 정확한 값·변경 대상·접속 방식을 넣은 최종안을 제시하고, 그때 실제 NAS 배포 승인을 요청한다.

## 승인 후의 배포·업그레이드·중단 복구 순서

1. 확인한 DSM/Compose에서 `name`, `service_completed_successfully`, `bind.create_host_path` 등 사용 기능을 검증한다. 미지원 버전이면 별도 초기화 명령을 포함한 호환 구성을 먼저 검토한다.
2. 기존 서비스와 겹치지 않는 새 프로젝트/새 전용 디렉터리/포트를 확인한다. 대상 디렉터리에만 새 계정 권한을 준비한다. 기존 개인 원본을 이동/삭제/재귀 권한 변경하지 않는다.
3. 불변 이미지와 Compose/env의 로컬 보관본을 남긴다. 새 볼륨 초기화 → LANraragi 건강 상태 → Studio 건강 상태 → 합성 한 권 읽기/다운로드 순으로 확인한다. 실제 사이트 작업자는 승인된 작은 테스트 항목 성공 후에만 사용한다.
4. 업그레이드는 작업자 정지 → 실행/모호한 원격 작업 확인 → Studio SQLite 백업 → LANraragi 정지 후 전용 Redis/설정/플러그인 볼륨의 일관된 NAS 로컬 스냅샷 → 새 불변 이미지 적용 순서다. 비밀을 재생성하지 않는다. 프로젝트 이름을 바꾸지 않는다.
5. 실패 시 작업자를 먼저 멈춘다. 이전 이미지와 백업을 보존한다. DB를 원래 파일에 덮어쓰지 않고 새 경로로 복원해 `STUDIO_DATABASE`를 그 경로로 바꾼다. 이전 schema와 이미지의 호환성을 확인한 뒤 기동한다.
6. 재기동 후 만료/복원된 실행 작업은 확인 필요 상태다. 알려진 원격 ID는 상태 조회 후 완료를 반영하거나 실패가 확인된 경우만 재시도한다. 원격 ID 없는 모호한 접수는 자동 재제출하지 않는다. 작업자 출력은 시도별로 보존한다. 같은 출처/provider+ID의 활성 작업은 URL 형태가 달라도 중복 생성하지 않으며 다른 사이트의 같은 번호와 혼동하지 않는다.
7. POSIX 작업자의 하트비트 실패·SIGTERM은 직접 엔진과 같은 프로세스 그룹을 종료한다. 새 세션으로 완전히 분리된 엔진까지 추적한다는 보장은 없으므로 지원 어댑터는 분리 실행하지 않는다. Windows는 직접 프로세스 종료 범위이며 실장치 검증이 필요하다.

## SQLite 백업·복원

`backup.py`는 SQLite backup API로 WAL 상태도 일관되게 복사하며 integrity/foreign-key 검사를 수행한다. 새 목적지에만 원자적으로 게시하고, 0600 권한과 SHA-256/개수를 반환한다. 원본은 수정하지 않는다. Studio DB에는 출처/댓글/읽기 기록과 작업 임대가 들어 있으므로 보호해야 한다.

```sh
python studio/backup.py backup <Studio-DB> <새-백업-DB>
python studio/backup.py restore <백업-DB> <새-복원-DB>
```

복원은 이전 임대를 모두 무효화하고 당시 실행 중이던 작업을 확인 필요로 만든다. 운영 복원 전에 모든 작업자를 중지해야 한다. 이 도구는 LANraragi Redis·플러그인·원본 아카이브·비밀 파일을 백업하지 않는다. 이들은 NAS의 전용 볼륨/설정 백업에 별도로 포함한다. 실제 NAS 백업을 클라우드나 GitHub로 올리지 않는다.

## 이번 작업의 검증 근거

- 표준 라이브러리 테스트 69개: WAL 백업/복원, 복원 임대 폐기, 기존 파일 덮어쓰기 거부, 기존/UID 변경 볼륨 거부, 대상 토큰 분리, 임대/재시작/모호한 원격 접수, URL 변형 중복 방지, 하트비트 실패 시 자식 프로세스 정리, 댓글 실패 시 60초 간격 보존 포함.
- JS 구문 및 shell 구문 검사 통과.
- 실제 Studio 이미지: 비루트 기동, 내부 API 연결, 합성 CBZ 리더/진행률/다운로드 해시/설정 저장, 데스크톱·모바일 pageerror 0. 초기 검증은 볼륨 초기화 4개, 재기동 초기화 0개였으며 업로드 추가 후 새 프로젝트에서 5개를 검증했다. 실제 컨테이너에서도 별도 경로 백업/복원을 확인했다. 비기본 UID/GID 10001에서도 새 전용 볼륨, 권한 자동 변경 비활성화, 리더/다운로드/설정 검증을 통과했다. 10001은 합성 테스트 값이며 실제 NAS 계정 값이 아니다.
- 합성 20,000 작품 + 20,000 출처: 목록 120개 중앙값 2.87ms, 출처 태그 검색 28.98ms, 제목 검색 43.03ms, 검색 8건/4스레드 약 104ms. 목록은 작품별 DB 접속 대신 출처를 한 번에 조회한다.
- 서로 다른 합성 아카이브 48개, 썸네일 동시 요청 4개: 첫 pass 총 230.65ms/p95 53.53ms, 반복 pass 총 165.02ms/p95 32.19ms. 실제 JPEG 응답이 application/x-download인 경우 시그니처를 확인해 image/jpeg로 전달하도록 수정했다.
- 위 성능은 관리형 클라우드와 공식 0.9.81 호환성 런타임에서의 결과다. DS718+ 실측이나 실제 2만 권의 썸네일 생성 비용을 의미하지 않는다.

## 실사용 완료 기준과 현재 남은 조건

- [완료] 합성 DB/읽기/썸네일/다운로드/복구/권한 테스트와 실제 Studio 이미지 기동.
- [대기] 최소 빌드 호스트 허용 → 전체 포크 이미지 빌드·기동 및 동일 통합 테스트 재실행.
- [대기] 사이트별 적법한 테스트 URL과 정상 접근 권한 확인 → 실제 다운로드 파일/페이지/해시/출처 메타데이터 검증. 댓글은 원문/작성자/시각/URL 비교와 재수집 보존 검증. 실패/제한은 미지원 또는 차단으로 기록.
- [미완성] E-Hentai 댓글 커넥터. 정상 접근 가능한 응답/DOM을 확인한 뒤 구현해야 한다. Hitomi 댓글 API의 존재/지원도 단정하지 않는다.
- [진행] DS718+ 환경 정보·전용 시험 배포·SSH 터널·Studio 로그인은 사용자 실행 결과로 확인했다. 기존 이미지 폴더의 전체 경로/읽기 권한 확인 → 한 폴더 시험 연결 → NAS 읽기/다운로드 실측·백업 복원 리허설은 남아 있다.

현재 상태를 실사용 완료 또는 실제 사이트 지원 완료로 표시하면 안 된다.

## 사용자 파일 업로드·다운로드

웹 상단 **↑ 업로드**에서 CBZ/ZIP/PDF를 선택한다. 기본 파일당 512 MiB, 순차 전송 1개이며 진행률과 색인 상태를 표시한다. 저장 직후 **↓ 받기**로 원본을 내려받을 수 있고, 색인 후 **열기**가 나타난다. 전체 파일 해시로 중복을 확인하고 기존 원본은 덮어쓰지 않는다. 자세한 검증 범위와 제한은 README의 Browser file transfer를 참조한다.

배포 구성에 새 `studio-uploads` 전용 볼륨이 추가되어 총 다섯 볼륨을 초기화한다. Studio만 쓰고 LANraragi에는 `content/StudioUploads`로 읽기 전용 연결한다. 두 서비스는 확인된 같은 UID/GID를 사용해야 한다. 업그레이드 시 볼륨을 유지하고, 백업·복구 시 서비스 쓰기를 중단한 뒤 Studio DB/업로드 볼륨/LANraragi 데이터를 함께 보존한다. SQLite 백업만으로 업로드 원본이 보존되지는 않는다. 이 구성은 클라우드의 합성 자료로 검증했으며 실제 NAS 배포는 승인 전이다.

## 선택적 전용 가져오기 폴더

`compose.import.yaml`을 기본 NAS Compose에 추가하고 확인된 신규 전용 `STUDIO_INBOX` 경로를 설정하면 Studio에 읽기 전용으로 연결한다. 기존 라이브러리·Stash 폴더를 지정하지 않는다. 서비스 UID에 읽기/디렉터리 탐색 권한만 준비하며 기존 원본의 소유권을 재귀 변경하지 않는다. 30초 안정화 후 업로드 볼륨으로 복사하므로 원본과 복사본 공간이 모두 필요하다. 원본은 삭제·이동하지 않는다. `.part`로 복사를 마친 뒤 완성 확장자로 이름을 바꾸는 사용 절차를 권장한다. 실제 NAS 경로·권한은 아직 확인하지 않았으며 배포하지 않았다. 상세 동작과 한도는 README의 Two import paths를 참조한다.

## 현재 조사한 NAS 정보와 최소 추가 확인

모델은 사용자가 밝힌 DS718+다. [Synology 공식 사양](https://global.download.synology.com/download/Document/Hardware/ProductSpec/DiskStation/18-year/DS718%2B/enu/Product_Spec_DS718%2B_enu.pdf)은 Celeron J3455, 64비트, 출하 메모리 2 GB를 명시한다. 따라서 amd64 후보를 선택했지만 **현재 설치 RAM/DSM/Docker 버전은 이 사양에서 알 수 없다**. [공식 백업 문서](https://kb.synology.com/en-global/DSM/tutorial/How_do_I_back_up_Docker_containers)는 DSM 7.2 이상을 Container Manager, 7.1 이하를 Docker로 구분한다. 사용자의 설치 버전을 추정하지 않는다.

기존 LANraragi/NMLO 배포 문서를 읽었지만 실제 DSM/Compose/UID/GID/전용 경로 정보나 관리 접속 정보는 없었다. NMLO README는 비밀·실시간 설정이 없는 소스 번들이라고 명시한다. 현재 환경의 구성된 관리 비밀 바인딩도 0개이며 TCP 허용 목록은 비어 있다. 허용된 Stash 버전 조회를 수행하더라도 DSM/컨테이너 버전이나 호스트 UID를 증명하지 못하므로 개인 라이브러리 조회·포트 탐색으로 확대하지 않았다.

`sh studio/nas_preflight.sh`는 **NAS에서 직접** 읽기 전용으로 실행할 진단 도구다. DSM 공개 버전 필드, 패키지 버전, 현재 계정 숫자 ID, 명시적 로컬 Docker/Compose 버전, 메모리, 표준 볼륨 루트에 대한 신규 전용 경로 후보만 확인한다. 미디어 목록·비밀·컨테이너 환경·Stash를 읽지 않고 디렉터리를 만들거나 서비스를 바꾸지 않는다. 현재 계정 ID는 관찰값이며 운영 계정 선택 승인이 아니다. 클라우드에서 실행한 결과는 NAS 정보로 취급하지 않는다. 사용자는 개별 기술 항목을 수동으로 찾는 대신 이 진단 결과만 제공할 수 있다.

경로 후보는 확인된 볼륨 아래 `docker/library-studio`이며 기존 경로가 있으면 채택하지 않는다. 하위 `library`, `library/downloads`, `inbox`를 제안하지만 실제 볼륨/공유 폴더/ACL이 확인되기 전에는 모두 **미확인 제안**이다. 실제 NAS 경로는 아직 생성하지 않았다.

## 최신 대량 검색 재검증

`python -B studio/tests/benchmark_catalog.py 20000`은 사용자 태그 40,000개도 포함한다. 이번 클라우드 측정 중앙값은 120개 목록 2.60ms, 사용자 태그 부분 검색 34.66ms, 정확 태그 필터 15.81ms, 출처 태그 검색 42.81ms, 제목 검색 59.66ms였다. 8건/4스레드는 146.39ms였다. NAS 실측으로 환산하지 않는다.

## 승인 가능한 첫 시험 배포 패키지

`studio/deploy/`는 정식 포크 빌드를 대체한 완료 선언이 아니라 **검증한 공식 0.9.81 호환 런타임을 사용하는 명시적 시험 구성**이다. `build_bundle.py`는 코드 이미지 2개와 Compose/설치 스크립트만 내보낸다. 컨테이너 볼륨·실제 미디어·개발 비밀은 포함하지 않는다. 이미지 ID·체크섬·원본 기반 이미지를 기록하고 NAS에서 추가 빌드/다운로드하지 않는다.

`install-pilot.sh plan`은 아무것도 변경하지 않는다. `install`은 sudo와 검토된 신규 루트/UID/GID를 요구하고, 기존 루트/프로젝트/볼륨을 거부한다. 새 경로·볼륨 5개·프로젝트만 만들며 비밀은 NAS에서 생성한다. 외부 사이트 작업자는 비활성, 접속은 loopback/SSH 터널이다. 정확한 대상 계정은 사용자 제공 진단과 클라우드의 동일 숫자 계정 시험을 바탕으로 선택하되 NAS ACL/실제 동작은 별도 확인한다. 먼저 `PILOT_GUIDE.ko.md`의 변경 대상을 검토하고 실제 설치 승인을 받는다.

테스트 73개와 대상 계정 조건의 실제 브라우저 통합 검증을 통과했다. 순정 Compose 2.20.1의 공개 체크섬을 검증해 구성 호환성을 확인했다. Synology의 정확한 2.20.1 벤더 빌드와 Docker 24의 실제 기동은 아직 NAS 검증 대상이다.

## 실제 NAS에서 확인된 기동 차단 (2026-10-17)

사용자 설치 출력으로 이미지 2개 로드, NAS 내부 비밀 생성, 새 네트워크/볼륨 5개 생성을 확인했다. LANraragi 컨테이너 생성은 Docker의 `NanoCPUs can not be set` 오류로 중단됐다. 따라서 실제 NAS 서비스 기동/접속은 아직 성공으로 기록하지 않는다.

NAS/선택 작업자 Compose의 `cpus`를 제거했다. 메모리 제한/작업 병렬 수 1/loopback 접속/전용 볼륨 정책은 유지한다. 기존 설치는 새 `resume-pilot.sh`로 자체 Compose만 백업·수정해 같은 프로젝트를 재개한다. 커널/cgroup/Docker socket 권한이나 기존 Stash/NMLO를 변경하지 않는다. 전체 이미지 패키지를 다시 로드하거나 `.env.nas`를 새로 만들 필요가 없다.

## 실제 NAS 기동 후 PC 접속 상태 (2026-10-17)

사용자가 복구 스크립트 실행 후 LANraragi healthy, Studio healthy 결과를 제공했다. 이로써 실제 시험 서비스 기동은 확인됐으나 브라우저/읽기/태그/백업의 NAS 실사용 검증은 별도다. PC SSH 로그인은 되지만 로컬 포워딩 채널이 `administratively prohibited`로 거부됐다. 이는 앱 건강 상태와 구분되는 SSH 포워딩 정책 문제다. 유효한 AllowTcpForwarding/DisableForwarding/PermitOpen 설정을 읽기 전용으로 먼저 확인한다. 기존 SSH 설정/서비스 변경이나 새 네트워크 바인딩은 구체적인 범위·복구 절차 검토 없이 자동 적용하지 않는다.

NAS의 유효 `AllowTcpForwarding no`가 사용자 출력으로 확인됐다. 전역 허용 대신 계정·PC 주소·Studio 목적지 하나로 제한한 [SSH 변경 검토안](deploy/SSH_TUNNEL_CHANGE.ko.md)을 준비했다. 합성 OpenSSH 검사만 통과한 제안이며 실제 NAS SSH 서비스 변경은 승인 전이다.
