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

## Deployment follow-up evidence (2026-10-16)

- Rechecked managed environment: running, current observations, enforced restricted HTTP policy, zero configured secret bindings. Alpine, cpanminus and target gallery hosts remain absent from the effective allow list. Bounded HEAD requests using inherited proxy/CA returned `Tunnel connection failed: 403 Forbidden` for `https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/APKINDEX.tar.gz` and `https://cpanmin.us/`. This is a policy block, not a certificate fix or permission to choose another mirror. Full fork build remains blocked before the dependency chain can be validated.
- Read existing NMLO README only for runtime/deployment evidence; it contains no live DSM/UID/path/access configuration. Did not execute its scanner or inspect its private configuration, Stash library or NAS files. Added `nas_preflight.sh` to gather only non-secret local version/UID/memory/path-candidate information on the NAS when the user runs it. Shell syntax and a cloud dry run pass; the cloud dry run is explicitly **not NAS evidence**.
- Found `studio/Dockerfile.worker` was excluded by upstream's broad `Dockerfile.*` ignore pattern. Added a narrow exception and tracked the existing non-secret recipe so a fresh checkout can build the documented worker. Built `lanraragi-studio:worker-reviewed` with the managed CA secret; non-default UID/GID 10001 can import worker/gallery adapter/dependencies. This does not verify any real site download.
- Extended `benchmark_catalog.py` to include 20,000 works, 20,000 sources and 40,000 user tags. Cloud medians: 120-item list 2.60 ms; user-tag substring search 34.66 ms; exact user-tag filter 15.81 ms; source-tag search 42.81 ms; title search 59.66 ms; eight searches/four threads 146.39 ms. These are synthetic cloud measurements, not DS718+ performance.
- DS718+ official specifications establish model CPU/architecture and factory RAM only; actual installed DSM, Docker/Compose, memory, runtime UID/GID, free disk, private access endpoint and new paths remain unverified. NAS_READINESS links the primary vendor sources and gives one read-only diagnostic instead of requesting many manual fields. No NAS deployment or existing-service change occurred.
- Actual E-Hentai/Hitomi downloads and comments are **not verified**. No suitable reachable nonsexual/legal site fixture was established under the current policy; no adult gallery was chosen/downloaded. E-Hentai/Hitomi comments remain JSON-import-only, nHentai connector remains synthetic-tested. Network permission, confirmed suitable test material and any required normal session are separate prerequisites; no passwords/cookies are requested in chat.

## NAS pilot packaging (2026-10-16)

The user supplied a NAS preflight report and confirmed the server version using sudo. Target facts are retained only in ignored local deployment records; they are not cloud measurements. No NAS access credentials or media were transferred. The normal account cannot inspect Docker directly, but sudo reports a healthy daemon, so Docker-group/socket permissions are not changed.

Added an explicit offline pilot package builder, installer, checksums/provenance, and Korean guide. It bundles only the tested Studio image and official-0.9.81 compatibility image, not container volumes, development env files or media. The full-fork build remains policy-blocked and is labeled unverified. Installer defaults to plan-only and refuses existing roots/projects/volumes, unsafe paths/IDs and unknown image identities. Actual installation requires explicit `install` mode and sudo. It prepares only new directories/volume tops, generates secrets on the NAS, pins local image SHA IDs, disables pulls/site workers and keeps loopback access for an SSH tunnel.

73 unit/HTTP tests pass, including four installer safety cases. With the target account UID/GID replicated in a new isolated cloud project, the browser upload/index/reader/original-download test passes. Official Compose 2.20.1 was downloaded from GitHub and verified against its published SHA-256; it accepts the NAS/import/pilot Compose configuration. Target DSM/Container Manager's exact vendor build and Docker 24 runtime behavior must still be verified on the NAS. This package is a reviewable pilot, not an assertion that NAS deployment has occurred.

## Download delivery correction (2026-10-16)

The executor-local package path was not a usable browser download link. The user explicitly approved private Google Drive upload of the NAS installer archive. The first approved upload failed before invoking Drive because the transfer path limits individual files to 100 MiB; the original low-compression archive was 111,800,320 bytes. Recompressed only the Docker save stream at gzip level 9, verified the decompressed image stream SHA-256 was identical, regenerated package checksums and rebuilt the outer tar below the transfer limit. Installer behavior/image IDs/source contents did not change. Updated the bundle builder to use level 9 for future exports. No NAS install or public sharing occurred during this correction.

## Synology CFS recovery (2026-10-17)

User-reported NAS install loaded both images, generated local secrets and created the dedicated project/network/five volumes. LANraragi creation then failed with `NanoCPUs can not be set` because CPU CFS quota support is unavailable. This is a partial installation, not NAS service readiness.

Removed `cpus` from NAS and optional NAS-worker Compose defaults; memory limits and application concurrency 1 remain. A zero-valued override was tested with official Compose 2.20.1 and left the old limits in the merged model, so that approach was discarded. The existing isolated cloud account-check project was recreated using unchanged volumes/env with the corrected base: Docker inspection confirms `NanoCPUs=0` for LANraragi/Studio while memory remains 1 GiB/256 MiB. The same project's actual browser upload/index/reader/download test is rerun as recovery validation. This tests the requested config semantics; actual NAS recovery still needs user output.

Added guarded `resume-pilot.sh`: plan-only default; apply is scoped to the existing approved pilot root/project, backs up its Compose file, removes exactly the expected two CPU entries and recreates only that project's containers. It does not re-run initial install, reset secrets, delete volumes, change cgroups/kernel/socket permissions or touch NMLO/Stash. Fresh bundles include the helper. Existing Drive bundles keep their original manifests and can use this small pinned recovery script rather than re-download images.

## User-reported NAS health and remaining browser access block (2026-10-17)

The user ran the pinned CFS recovery helper on the NAS. Reported results: dedicated volume initializer exited, LANraragi healthy, Studio started and subsequently healthy. Existing volume/env recovery is therefore evidenced on the NAS; the assistant did not directly administer the NAS. The PC's SSH authentication succeeded, but the forwarding channel returned `administratively prohibited`. Effective forwarding restrictions must be diagnosed before proposing any scoped SSH change; no SSH configuration, listener, firewall or other existing-service change has been authorized/applied in response to this error. Browser login and actual NAS media-flow validation remain pending.

## Scoped SSH forwarding proposal (2026-10-17)

The user supplied effective NAS policy: AllowTcpForwarding=no, DisableForwarding=no, PermitOpen=any. Prepared a review-only exact-user/exact-client Match proposal allowing local forwarding solely to 127.0.0.1:43120; global denial remains. Added a non-installing proposal generator/validator and real OpenSSH parser tests with temporary synthetic host keys. Verified target scope and unchanged unrelated user/address contexts; earlier matching denial and blanket DisableForwarding fail validation. Invalid/wildcard/duplicate inputs are rejected. No SSH daemon was started, no NAS key or private configuration was copied, and no NAS SSH config/reload was performed. The change plan includes NAS-local backup, staged syntax/effective-policy checks and confirmed main-daemon reload/rollback before closing the existing management session. Existing SSH service modification remains a separate explicit approval step.

## Approved scoped SSH application tooling (2026-10-17)

The user explicitly approved the presented exact-user/exact-client/local-Studio forwarding exception. Added `configure-tunnel.sh` with plan-only default and guarded apply/rollback. Before any live config change it requires root, an ordinary exact username, exact IPv4s/port, root-owned regular config/PidFile, verified SSH main executable/parent/start identity, unchanged original config, syntax validation, exact target forwarding, unchanged other target settings, and unchanged unrelated user/address contexts. Unrecognized daemon config/option flags stop before applying. NAS-local root-private backups are retained; only the verified main PID is reloaded. Error recovery restores the original config where possible and refuses unverified process signaling. No NAS SSH configuration was actually changed by the assistant; user-side execution is still required.

The proposal validator now accepts the actual NAS local address/SSH port for Match evaluation. Added local-address precedence and shell scope/root/path guard regressions. Real OpenSSH parser tests use temporary synthetic host keys and do not run a daemon. Existing denied PC tunnel connections must be replaced with a new connection after the approved reload; the original NAS management session stays open until verification.

Validation for the approved helper: 84 unit/HTTP/config tests passed; shell syntax and diff whitespace checks passed. No actual NAS SSH reload has been observed yet.

## NAS browser login and unpacked-folder continuation (2026-10-17)

The user confirmed that the Windows SSH tunnel opens Studio and that administrator login succeeds. These are user-observed NAS results; the cloud did not receive NAS keys, passwords, configuration files or private media. The exact post-apply SSH daemon report was not separately supplied. NAS upload/read/download/recovery validation is still pending.

The selected source contains unpacked image directories rather than only archives. Prepared a separate network-disabled, non-root, read-only-source one-shot folder worker with metadata-only plan default. The actual absolute NAS source path/ACL and the first selected small folder remain unconfirmed. This new worker has not been installed or run against NAS media. See deploy/NAS_FOLDERS.ko.md for storage cost, initial one-book bounds, rollback and the distinction between folder tags and a folder-tree UI.

Validation of this continuation:

- 105 unit/HTTP/config tests passed; JS syntax and diff whitespace checks passed. New regressions cover natural page order, original bytes/mtime/mode preservation, real synthetic WebP, unstable/invalid sources, symlink/DSM metadata exclusion, temporary `.part` visibility, interrupted publication deduplication, persistent bounded-scan progress, backup/receipt preservation, source-qualified number resolution, missing E-Hentai identifiers and admin-only HTTP submission.
- Built Studio candidate `sha256:f76377624b8e39cbf91316a685da4e472109ed6178a3a4e62529043d31d6ea68`. This is a Studio build, not a full fork build or a NAS rollout.
- `python -B studio/tests/download_reference_smoke.py` passed: missing E-Hentai identifier creates no job, saved original URL reused, PC target selects external worker, equal numbers on different sources remain separate, an existing catalog file avoids requeue, 1440/390 px layouts fit, page errors 0. No source website was contacted; live download success is **not** established. Existing NAS web image has not received this new UI.
- Created isolated project `library-studio-folder-check` at cloud loopback 43130, five fresh volumes, UID/GID 1026:100 and generated-only PNG/JPEG/WebP source folders. The source and reviewed Python module are mounted read-only; the worker has only loopback network and no external egress. A write probe fails with EROFS. Plan leaves uploads unchanged. Import generates one CBZ, actual LANraragi indexes it, all three formats render at 320 px in the browser reader, folder tag is applied, downloaded CBZ SHA-256 and page bytes match, source bytes/modes/mtimes are preserved, subsequent runs retain one upload, page errors 0.
- Repeated the folder integration using the **exact NAS-loaded Studio image** `sha256:e9362b455709b234c6b1cc57420307e1e2c475044788d01d23f8d9716ac2dfa0` with only the reviewed module mounted at `/app/folder_importer.py`. Simulated loss of the synthetic folder receipt after file publication: regeneration reuses the same archive hash, preserves the single existing upload and reopens its reader. Thus the optional one-shot folder worker can reuse the installed image; existing NAS web/LANraragi containers need not be recreated for this import path.
- Initial synthetic runtime attempts exposed inaccessible newly created fixture directories (restrictive umask) and a read-only code mount with mode 0600. Corrected only those newly generated cloud fixtures and the non-secret code file to the intended traversal/read modes, then reran integration. No existing NAS original permission change was made. Repeated browser testing also resets only the synthetic reader's progress before checking pages 1–3; the previous page-3 resume was expected persisted state.

Pending actual NAS actions: confirm the absolute user-selected source path and read access, prepare NAS-local module/Compose/selectors, review a one-folder plan, then run/import/read/download on that single approved NAS folder. No full-library scan/import, background watch, source move/delete or public exposure is enabled. External website downloads/comments and full-fork network build remain at their previously documented boundaries.

## NAS read-only plan failure and access diagnostics (2026-10-17)

The user confirmed the absolute NAS root in chat and ran a network-disabled read-only plan using the NAS-loaded image. Report: 2 directories / 2 errors / 0 pages / 0 imports. Host directory metadata confirms the selected root, manga and images exist, owned by the intended NAS account, with mode 0777 and a Synology ACL marker. The exact runtime error is not yet known; neither the mode nor the ACL marker proves its cause. No ACL, group, ownership, media or existing-service change was made.

Added `--operation diagnose`: runtime UID/GID/groups/UID map, selected root/collection metadata, opened/read-only state, direct-image/subdirectory counts, bounded name-case matching and sanitized errno/validation details. It never reads a media payload or opens the Studio database. Regular plan/import also includes up to 20 selected-collection issue summaries; OSError filenames are excluded. Regression tests distinguish denied access, missing paths and page-count limits, and check that diagnosis does not emit private descendant filenames or write destinations. 108 unit/HTTP/config tests passed. The exact NAS-loaded image plus read-only module was exercised in the existing isolated cloud synthetic project: UID1026/GID100, all selected mounts read-only, diagnose errors 0. Actual NAS diagnostic execution and a first successful NAS import remain pending.

The user subsequently supplied NAS diagnosis: runtime UID1026/GID100/groups[100], source owner UID1026/GID100, source mode000 and errno13. This establishes container-side access denial; it does not by itself identify the ACL entry or missing group responsible. Prepared `probe-folder-groups.sh` to capture only the ordinary NAS account's actual numeric group memberships before sudo and pass them to a one-off, no-network, read-only diagnostic container. It neither guesses/adds NAS account groups nor changes ACLs or existing services. Three shell guard regressions cover side-effect-free preview, wrong/root identity, malformed group/volume/mount arguments, nonexistent source and forbidden import mode. The supported NAS group retry is pending; no fix success or NAS import is claimed.

## User-confirmed NAS source access recovery (2026-10-17)

The group retry returned errors=0, UID1026/GID100/groups[100,101]. The selected root and both collections now report mode0777, opened=true and read_only_mount=true. Passing the NAS account's existing supplementary group101 restored read access without changing the host account, ACL, ownership or originals. manga reports two child directories and no direct images; images reports neither supported direct images nor child directories. This is source-access evidence, not a successful NAS import/reader/download result.

The optional folder-only Compose service now requires `STUDIO_FOLDER_READ_GROUP`; verified value101 is scoped to that worker, leaving primary1026:100 and all existing services unchanged. Official Compose2.20.1 configuration validation with the optional profile enabled confirms group101 only on that service, preserved source/code read-only mounts, network-none and a read-only container root. No new application code changed; the previous 111-test suite remains the application regression evidence. Prepare/ready/error counts from a read-only recursive plan and a first bounded one-folder import are the next NAS steps. No actual NAS writes or existing-container reconfiguration were performed by the assistant.

## User-confirmed NAS plan and pinned one-folder pilot (2026-10-17)

User's recursive read-only plan: directories417, pages16896, ready326, errors0, deferred0, imported0, bounded=false. These are candidate/image-extension metadata counts, not a claim that all images decode or all folders import successfully. Existing account groups100/101 and read-only source are maintained. A first NAS registration/reader/download result is still pending.

Implemented a separate `pilot` operation: local natural-order selection of one stable small folder (128 MiB generated archive cap), a private persisted selection that never advances to another book on repeat, exclusive pilot lock, source/mount/selection checks, and a verified SQLite backup before Store initialization/migration or archive publication. Changed sources/selections and backup errors stop. Selection/backup filenames are fixed/generated; private media names are not printed. The original remains read-only. Unit regressions verify first backup lacks the new receipt table, source preservation, retry staying on the same book, backup failure before any archive/migration, selection/symlink escape rejection, source-change stops and concurrent pilot exclusion.

Fresh isolated cloud project `library-studio-folder-pilot-check` on loopback43132, fresh five volumes, synthetic PNG/JPEG/WebP, exact NAS-loaded Studio image with the reviewed module mounted read-only, group101, no-network worker: pilot generated and indexed one archive, reader displayed all three formats, downloaded CBZ/page hashes matched, folder tag applied, two retries retained one upload and the same selected folder, source bytes/mode/mtime preserved, page errors0. A registration-before snapshot is retained in that isolated project's data volume. The final application/deployment regression suite passed118 tests, including the side-effect-free preview and wrong-identity/mode/path guards for the NAS wrapper; shell syntax and diff whitespace checks also passed. This is cloud synthetic evidence, not actual NAS import evidence.

## Personal-account reuse withdrawn (2026-10-17)

The user explicitly rejected using their NAS account for application execution. Prior diagnostic/pilot claims about no password transfer did not establish privilege separation: personal UID1026 was used by the installed app configuration and group101 was inherited by the temporary probe. Latest personal-account probe/import helpers now refuse every execution mode, the optional folder Compose no longer adds operator supplementary groups, and new NAS installation checks a named dedicated non-administrator account before any Docker/write action. Its read-only checker rejects personal UID1026, root, group101, privileged group names, malformed identities and mismatched caller-supplied IDs. New bundles include the checker and dedicated-account plan. Synthetic fixture code no longer requests group101. Historical test results with that group do not validate the new NAS account or actual migration.

Only cloud source/docs/tests changed. Existing NAS containers still require a reviewed migration; no account was created, no ACL/ownership changed and no NAS service was stopped or recreated. The plan preserves existing volumes and forbids changing only UID env values because volume identity markers intentionally reject that. Dedicated account IDs/access and a migration execution tool still require separate preparation and validation. Previously pinned/downloaded scripts remain obtainable and must not be run.

Validation of this correction:118 unit/HTTP/deployment tests passed. Read-only service-account tests cover named-account lookup, forbidden identities/groups, missing/mismatched identity and rejection of all legacy helper modes. Shell syntax and diff whitespace checks passed. Compose configuration validation confirms no supplementary group, network-none/read-only-root and source/code RO mounts on the optional folder service. No new containers were started and no actual dedicated NAS account/access/migration validation is claimed.

## User-approved root source reader (2026-10-17)

User-provided NAS Docker inventory identifies Stash as PTestManager (stashapp/stash:latest). Inspect showed its user empty and Studio user1026:100; a subsequent docker top with PID/UID/GID/comm confirmed the actual stash process UID0/GID0. The user approved root execution. This establishes a runtime-identity difference, not the exact Synology ACL rule. Root reading is now explicitly authorized; mandatory creation of another NAS account is not a prerequisite for this bounded trial. No Stash changes were made.

Implemented root-pilot in the disposable folder worker: only source directory access/stat/open uses effective root; all state/lock/SQLite backup/Store/archive publication runs with the verified existing app effective UID/GID, supplementary groups cleared. There is no output chown or original ACL/ownership edit. Dedicated volume markers/owners/DB identity are checked before writing; backup-first/pinned selection/128MiB/concurrency lock/source RO checks are retained. A separate opt-in Compose overlay and guarded pinned NAS script are provided. Existing web/LANraragi containers need no change or restart. Disabled group-inheriting scripts remain disabled.

The managed cloud runtime was fresh: prior checkout/images/volumes were absent. Restored the latest fork independently, retained enforced proxy/CA/network policy (VPN configured, no TCP grants, no secrets), and used only generated fixtures. Rebuilt Studio from the NAS initial packaging source checkpoint77a493a3 with the current folder module mounted RO, plus an official0.9.81-based compatibility LRR image with Config API override, initialized-volume guard and worker concurrency1. These freshly built images are not the exact prior NAS image binary IDs and do not establish a full-fork build. Initial cloud-only image setup failed on restrictive copied-file modes and an ignored scratch build context; corrected only new test code build context/modes and repeated validation.

Project library-studio-folder-root-check uses loopback43134 and fresh dedicated volumes. Generated PNG/JPEG/WebP sources are owned by cloud fixture UID1000 with directories0700/files0600. Ordinary app UID1026 is refused; root source access succeeds with DAC_OVERRIDE/SETUID/SETGID only. Wrong output UID is refused before upload. Actual LANraragi indexes the generated CBZ; legacy non-root web app renders all3 formats, saves reading state, applies folder tag, and serves original CBZ/page hashes correctly. All data/uploads files/directories retain UID1026/GID100. Source files and directories preserve bytes, mode, mtime and ownership. Two worker retries keep the same selected single archive; browser page errors0.122 unit/HTTP/deployment tests passed, shell syntax and diff checks passed. Actual NAS root import/reader/download remains pending user execution; no NAS account, ACL, source, Stash or existing service was changed from cloud.
