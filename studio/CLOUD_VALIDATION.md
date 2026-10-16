# 클라우드 검증 기록 (2026-10-16, 한국 시간)

이전 검증 기록이다. 후속 작업의 최신 상태와 50개 테스트, 실제 Studio 이미지 기동, 배포 후보/남은 차단은 [NAS_READINESS.md](NAS_READINESS.md)를 먼저 확인한다.

`feature/library-studio`의 체크포인트 `79f7dd7007e68521002021f6c3e61ac248ccea1e`에서 독립 체크아웃으로 이어서 작업했다. NMLO 저장소와 Stash는 수정하거나 조회하지 않았다. 개인 자료는 사용하지 않았다.

## 런타임과 접근 범위

- environment_status: running / connected, observations_current=true. HTTP 정책 상태는 unknown이므로 enforced라고 단정하지 않았다.
- 비밀 없는 정책 파일: version=1, vpn_configured=true, HTTP 프록시 8080, TCP CONNECT 8088. TCP 허용 목록은 비어 있다. VPN 설정은 확인했지만 NAS 대상 서비스의 연결 정상 여부는 별도 검증하지 않았다.
- 일반 실행 경로에서 프록시/소켓 연결이 제한되어 동일 명령을 정상 승인 실행 경로에서 재시도했다. 상속 프록시와 CA 설정을 유지했다. Tailscale 실행, 키 조회, 프록시 우회를 하지 않았다.
- 개발 비밀은 새로 생성한 무시되는 `studio/.env`에만 저장했다. `.dockerignore`에서도 비밀·DB·테스트 결과·작업 디렉터리를 제외했다.

## 구현과 검증

- 작업자 토큰은 POST claim/report 전용. 일반 화면·내보내기·작품 수정 권한은 없다. 작업 생성의 중복 응답에서도 임대 정보가 노출되지 않는다.
- 재시도마다 고유 출력 폴더를 사용한다. 먼저 폴더를 보고하며, 빈 파일·잘못된 완료 요약은 거부한다. 하트비트 실패/시간 초과 시 직접 실행한 엔진 프로세스를 종료한다. 별도 분리된 자식 프로세스까지 모두 종료한다는 보장은 없다.
- 재시작 후 만료 작업은 목록 조회에서도 확인 필요로 바뀐다. 원격 작업/출력 위치는 보존한다. 원격 ID가 있으면 재시도 전에 상태 조회: 완료는 그대로 반영하고 실패가 확인된 경우만 재제출한다. 접수 응답 유실로 ID가 없는 모호한 제출은 자동 재시도하지 않는다.
- Unix Minion 동시 실행 설정 `LRR_WORKER_CONCURRENCY`는 1–32 정수만 허용하며 Studio Compose 기본값은 1이다. DS718+ 실측은 아직 없다.
- 실제 `/api/archives` 객체 배열 응답과 `size` 필드를 처리하도록 수정했다. 이전 문자열 ID 목록도 지원한다. 리더를 다시 열 때 서버의 최신 진행률을 가져오고, 이미지 로드 시 해당 페이지 번호를 캡처해 기록한다.
- 출처별 메타데이터 플러그인을 이름 부분 일치 대신 확인한 namespace로 선택한다. Hitomi의 전체 원본 상세 URL을 보존한다.
- nHentai 공개 JSON 댓글 커넥터: 합성 응답으로만 검증. 1MiB/100개 한도, 출처별 60초 간격, 출처 URL·수집기·시각 보존, 같은 출처의 댓글 ID로 갱신하고 응답에 없는 기존 댓글은 보존한다. E-Hentai/Hitomi 댓글은 미지원 응답을 반환한다. 리다이렉트·로그인·차단을 우회하지 않는다.
- `python -B -m unittest discover -s studio/tests -q`: 32개 통과. 실제 루프백 인증/작업자 HTTP→엔진→완료 보고, 재시도 파일 보존, 임대 만료, 하트비트 실패, 원격 재제출 방지, 댓글 보존을 포함한다.
- `node --check studio/web/app.js`: 통과.
- `python -B studio/tests/browser_smoke.py`: 실제 LANraragi 0.9.81 + 합성 CBZ 한 권, 3쪽 리더·2쪽 진행률·이어 읽기·썸네일·PC 다운로드 SHA-256 일치, Chromium 1440×1000 / 390×844에서 가로 넘침 없음, pageerror 없음. 두 화면 캡처도 직접 검토했다.

## 빌드와 통합 검증의 한계

Studio Docker 이미지는 빌드했다. 전체 포크 Dockerfile은 `dl-cdn.alpinelinux.org`의 HTTP 403에서 막혔다. 허용 정책 변경이 필요하며 우회하지 않았다. 뒤의 Perl 설치에는 `cpanmin.us`도 필요하지만 아직 그 단계까지 실행되지 않았다. 추가 차단은 실제 오류를 보고 확인해야 한다. 허용된 후 각 HTTPS 설치 단계에 스킬의 CA secret mount 지침을 적용해야 한다.

실제 API 검증에는 공식 이미지 `difegue/lanraragi@sha256:6376a3de75c8a4045aadeb252eee9661ee9baf27965cec7a405a2b246d2937b3`(응답 버전 0.9.81)을 사용했다. 이 이미지에 포크의 Config.pm과 동시 실행 설정 변경만 적용했다. 전체 포크 코드를 올리면 공식 이미지에 Crypt::Passphrase 등 새 의존성이 없어 실행되지 않았다. 따라서 전체 포크 이미지 빌드/실행 성공으로 간주하면 안 된다.

새 합성 컨테이너에서 자동 권한 조정 비활성화 시 썸네일 볼륨 소유권 때문에 최초 인식이 실패했다. 실패 시 파일맵만 남아 재시작해도 재인식되지 않았다. 기존 사용자 자료를 건드리지 않고 새 빈 테스트 볼륨으로 다시 검증했다. NAS 배포 전 전용 볼륨 소유권 준비와 이 실패 복구 절차가 필요하다.

## 합성 검증 재현

1. 독립 개발 환경에서 `python studio/setup.py`로 새 비밀을 생성한다. 기존 파일은 덮어쓰지 않는다.
2. `python studio/tests/make_synthetic.py`로 전용 `studio/data/library`에 합성 3쪽 CBZ를 만든다. 기존 합성 파일도 덮어쓰지 않는다.
3. 빈 전용 볼륨의 LANraragi를 127.0.0.1:43121에 실행한다. API 키는 위 `.env`의 개발용 키만 사용한다. 콘텐츠는 합성 디렉터리만 연결한다. 전용 볼륨의 UID/GID를 준비한다.
4. Playwright와 Chromium이 있는 환경에서 `python -B studio/tests/browser_smoke.py`를 실행한다. Chromium 경로는 `CHROMIUM_PATH`로 지정할 수 있다. 이 스크립트는 합성 한 권만 있는지 확인하며 개인 라이브러리에 사용하지 않는다. Studio DB는 임시 디렉터리를 사용하고 캡처는 무시되는 `studio/test-results/browser-smoke`에 둔다.

## 남은 순서

1. HTTP 정책 보완 → CA mount를 적용한 전체 포크 이미지 빌드/실행 → 동일 합성 검증 재실행. 새 볼륨 소유권 준비와 파일맵 실패 복구 보완.
2. 원격 ID 없는 모호한 제출의 운영자 확인/연결 화면, 분리된 엔진 프로세스 관리, 장시간 해시 검증·네트워크 장애 테스트.
3. 실제 허용된 사이트 접근으로 플러그인/댓글 응답 검증. 현재 사이트 호스트는 HTTP 허용 목록에 없다. 사이트 권한·정책 및 정상 로그인 필요 여부를 먼저 확인한다. E-Hentai 댓글 커넥터는 허용된 응답 샘플과 DOM 검증 후 구현한다.
4. 설치 확인: 메타데이터 `ehplugin`, `hitomiplugin`, `nhplugin`; 다운로드 `chaikadl`, `ehdl`, `pixivdl`. 설치는 실사이트 성공 증거가 아니다. Hitomi 다운로드 플러그인이나 특정 외부 다운로더의 실제 동작은 검증하지 않았다. 초기 레지스트리 갱신 성공도 보장하지 않는다.
5. 대량 합성 라이브러리 성능 측정, DB 백업/복구 검증, DS718+ 전용 경로·UID/GID·메모리 확인을 포함한 배포안 준비.
6. 실제 NAS 배포, 기존 서비스 변경, 개인 파일 이동/삭제, 공개 노출은 사용자 승인 전에는 실행하지 않는다.

## Browser upload/download continuation (2026-10-16)

- Added authenticated, streamed CBZ/ZIP/PDF uploads with one concurrent transfer, configurable 512 MiB default, bounded archive checks and full-file SHA-256 deduplication. New shared upload volume is read-only to LANraragi; existing library files are not overwritten. Original-filename downloads support byte ranges before indexing completes.
- 59 Python unit/HTTP tests pass; JavaScript syntax and diff whitespace checks pass. Tests cover interrupted/unsafe input, scoped worker rejection, cross-origin rejection, duplicate/same-name behavior, original bytes/ranges, exact upstream linking and partial-ID collision refusal.
- Built Studio image and ran a new isolated Compose project `library-studio-file-transfer` on loopback 43126, UID/GID 10001, with five fresh named volumes and an empty synthetic-only host library. Corrected this new test directory's mode from 0700 to 0755 so the configured service UID can traverse it. No existing NAS permissions were changed.
- Chromium `studio/tests/upload_smoke.py` passed: UI upload, immediate original download/hash and filename, duplicate preservation, actual LANraragi watcher/indexing, masked reader, mobile/desktop layout, no JavaScript errors. Integration uses the previously documented official-0.9.81 compatibility image, **not** a newly built full fork image. PDF storage accepts basic structural markers; actual PDF rendering remains unverified.
- Upload bytes require a separate coordinated volume backup; SQLite backups now count upload records as well. Actual NAS deployment, site downloads/comments, full-fork build and external access blockers remain as previously documented.

## User tagging and two import paths (2026-10-16)

- Added indexed user tags independent of upstream/source tags, atomic batch add/remove (120 works), exact tag filtering, search/autocomplete, global rename/merge with an in-app review, metadata export and DB backup preservation. Upload-time common tags apply once when linked so later manual removals survive synchronization. List queries batch-load user tags.
- Browser upload now accepts file drag/drop and directory picker (archives/PDF only, max 20 per batch). It does not package loose page images or retain folders as collections.
- Added opt-in read-only inbox overlay and copy-only importer: 30-second stability window, change detection before publishing, descriptor-anchored no-symlink reads, persisted receipts, ten-second polling, bounded scan batches, no source moves/deletes. Pending upload indexing advances through batches beyond the recent-100 UI list.
- 69 unit/HTTP tests pass, including tags surviving sync, batch rollback, literal autocomplete, rename/merge, backup/reopen, upload-tag application/removal, inbox idempotence/restart, source-change rejection and pending-index batch progression. JavaScript syntax/diff checks pass. Synthetic Chromium tag checks pass for bulk edit, autocomplete, single add/remove, exact filtering, merge review, source preservation, folder upload/common tags, duplicate drag upload and mobile/desktop layouts.
- Built Studio image and enabled inbox only in the existing isolated cloud test project on loopback 43126, with a new generated synthetic inbox. Actual LANraragi automatically indexed the copy; source bytes remained unchanged and authenticated downloaded bytes matched SHA-256. Recreated the test Studio container to check persisted state. Uses the documented official-0.9.81 compatibility image for LANraragi; no new full-fork build claim. No NAS deployment or existing service/file permission changes.
- External site support/access blockers remain unchanged. Real NAS inbox path and service permissions still require a reviewed deployment plan.
