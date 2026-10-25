# 제목과 자동 연결 후보 UI 수정 검토

2026-10-25 KST. 로컬 작업 파일만 수정했으며 NAS 배포는 하지 않았다.

## 결과

- 목록·상세·브라우저/리더 제목은 원래 제목을 보존하면서 작가 접두사와 확인된 출처 번호를 뺀 `display_title`을 사용한다.
- 외부 제목 검색과 제목 비교도 같은 정리 함수를 사용한다. 권·화·연도 및 확인되지 않은 숫자/제목 괄호는 보존한다.
- 후보에 검증된 HTTPS 원문 링크를 제공한다. 제목에는 출처 ID나 작가를 덧붙이지 않는다.
- 같은 언어 후보를 먼저 보여주고, 다른 언어/언어 미확인 후보는 접힌 그룹에 둔다. 그 그룹에서는 같은 판본에 연결하는 버튼을 비활성화한다.
- 제목·작가·언어·페이지·태그 비교 근거와 기준 언어를 표시한다. 페이지 불일치와 정보 부재를 구분한다.
- 상위 10개 후보 보존 시 언어 일치를 우선한다. 기존 엄격한 자동 확정 조건은 유지한다.
- 표시용 값은 원본 메타데이터 밖에 두어 기존 연결 API의 검증 및 원본 데이터 보존과 충돌하지 않는다.

## 수정 파일

`sources.py`, `metadata.py`, `store.py`, `auto_sources.py`, `web/app.js`, `web/style.css`,
`tests/test_title_candidates.py`, `tests/test_candidate_ui.js` 및 이 문서.
이전에 작성한 HTTP 상태 진단 수정 파일은 별도로 작업 트리에 남아 있다.

## 검증

- 새 Python 회귀 4개 통과: 제목/권수/연도 보존, 저장 원본 보존, 정리된 검색어, 동일 언어 후보의 상위 10개 보존 및 수동 연결 입력 호환성.
- JS 검사 통과: 안전한 외부 링크, 언어별 그룹, 다른 언어/미확인 언어 연결 방지, 후보 인덱스 보존, 제목 HTML 이스케이프.
- 관련 Python 검사 총 50개 중 44개 통과. 기존 Windows 환경 오류 6개는 이 변경 전에도 재현된 항목으로, 최종 집중 실행에서는 제외했다.
  - `test_metadata.MetadataTests.test_store_originals_alias_filter_hidden_internal_tags_and_backup`
  - `test_auto_sources.AutoSourceTests.test_restore_disables_replay_and_session_change_wakes_blocked_jobs`
  - `test_auto_sources.DocumentRPCTests`의 4개 검사: POSIX `os.getuid` 부재.
  - 앞의 두 백업 검사는 Windows `os.fsync` bad file descriptor 오류다.
- 실제 Chromium의 격리된 loopback 합성 Studio에서 제목 표시, 원문 링크, 언어 그룹, 버튼 비활성화 및 가로 넘침 없는 모바일 레이아웃 확인.
- 합성 한국어 후보를 실제 UI에서 선택해 저장 API까지 확인. 출처는 2개가 됐고 원래 제목은 보존됐다. 외부 사이트나 개인 자료는 이 UI 검사에 사용하지 않았다.
- JS 구문과 `git diff --check` 통과.
- 디자인 검출기는 기존 Inter 폰트와 동적으로 src를 설정하는 숨김 voice-page 이미지에 경고 2개를 냈다. 이번 범위 밖의 기존 디자인/재생 동작은 변경하지 않았다.

## 권한과 실제 적용 경계

현재 가드는 `active=false`, `reason=non-Orca shell`이다. 내장 채팅의 공식 런타임 매핑과 정책에서
이 작업 공간의 worker 역할·배정 브랜치를 읽기 검증했다. 사용자 지시의 Git 쓰기 금지를
파일 편집 전부의 금지로 확장해 중단했던 해석은 정정했다. 배정 작업 트리의 일반 파일만
편집했으며 Git ref·인덱스·브랜치·훅·가드 정책·식별 환경변수는 변경하지 않았다.

- 브랜치: `Yuris99/ehentai-connection-fix`
- HEAD: `d034eb12523c6f75a3f4600edc8018392f7f39d8`
- 커밋·push·병합·NAS 배포 없음. 운영 release manifest와 배포 번호는 아직 갱신하지 않았다.
- NAS의 기존 원본·파일명·다운로드 엔진·ExHentai 엔진 설정 변경 없음.
- 운영 화면 반영은 메인 검토와 별도 배포 승인 단계다.

## 배포 요청 후 준비 상태

사용자의 배포 승인은 받았다. 공개 배포 요청과 원격 HEAD를 다시 읽었으며 앱 요청은 20,
feature/library-studio HEAD는 기준 HEAD와 동일했다. 운영 health도 앱 20으로 확인했다.

- 로컬 `STUDIO_UPDATE=21`, runtime manifest 22개 파일 해시 및 Python 구문 검증 완료.
- manifest SHA-256: `5e4a762d70b20afd33cc873ffa51c69eabc9bbe6c7c4507a2cfe4893c5fe2a62`.
- 비밀/DB/미디어/환경 파일을 제외한 검토용 소스 묶음을 Orca scratch에 생성하고 아카이브 내부 해시도 대조했다.
- 배포 manifest 검사를 추가 통과했다. 공개 `nas-release.json`은 아직 20을 유지하며 존재하지 않는 코드 커밋을 가리키도록 변경하지 않았다.
- 기존 배포기는 공개 고정 소스 커밋을 요구한다. 가드가 inactive인 상태에서 커밋·푸시하거나, 다른 브랜치를 작업자가 갱신하거나, NAS 코드를 직접 덮어써 이 경로를 우회하지 않았다.
- 실제 배포는 아직 미수행. 등록된 프로젝트 메인의 불변 코드 커밋 공개 및 generation 21 배포 요청 게시가 남았다.

## 2026-10-25 가드 호환 복구 후 상태

사용자가 공용 가드 호환 문제 해결을 추가 승인했다. 공식 로컬 런타임의 살아 있는 세션과
고유 작업공간 매핑을 대조하는 어댑터를 적용해, 설치된 가드에서 `active=true`,
`role=worker`, 배정 경로와 현재/배정 브랜치 일치를 확인했다. 이전 inactive 기록은 복구 전 이력이다.

- 공용 도구의 `branch_guard.py`, 공용 신원 함수를 재사용하는 `manage_guard.py`, 신규 회귀 검사만 적용했다.
- 정책/역할 등록과 Git 훅 30개의 해시는 변경 전후 동일하다. 실제 세션 식별 환경변수와 프로젝트 ref는 복구 과정에서 변경하지 않았다.
- 격리된 scratch 합성 저장소의 실제 Git 훅 검사 9개 및 새 신원 검증 검사 10개 통과.
- 세션 누락·충돌·종료·다중 매핑·타 런타임·불완전 목록·런타임 장애는 허용하지 않는다. 기존 작업자 브랜치/푸시 제한을 유지한다.
- 원본 도구 백업과 적용 영수증은 Orca scratch의 `guard-native-fix`에 보존했다.
- 이 작업 브랜치에서 커밋을 준비하며, 메인에서 자기 역할을 별도로 확인한 후 독립 검토·통합·배포한다.
- NAS 업데이트 21 적용 및 실제 UI 검증은 여전히 미완료다. 다운로드 성공으로 확대 보고하지 않는다.
