# Studio 화면 가독성·위계 개선 검토

2026-10-25 KST. 브랜치 `Yuris99/studio-design-polish`, 기준 `1ec062a5`. 로컬 작업만 했고 NAS·운영(library.yuris.io)에는 적용하지 않았다. 버전 번호와 배포 manifest는 바꾸지 않았다.

## 방향

표지가 주인공인 조용한 어두운 서재. 글자는 14–15px 기준·높은 대비의 중립 잉크로 올리고, 크롬은 줄여 첫 화면에 표지가 보이게 한다.

taste-skill 앱 화면 절차: `draw.mjs --app` 결과 `true-black-flat`(seed 1275681602)을 골랐다. 그 위에 집 서재에 맞게 따뜻한 near-black 바탕(#0e0d0c)을 쓰고, 색은 읽기 데이터에만 쓰는 호박색 하나(별점·즐겨찾기·선택 체크)로 정했다. 기본 강조색이던 하늘색·남색 계열은 걷어냈다.

## 바꾼 것

- **가독성**: 8–12px 글자 약 74개 → 최소 12px(보조 정보만), 본문·버튼 14px, 댓글 15px, 제목 26/24px. 한국어 단어 중간 줄바꿈을 막도록 `word-break: keep-all`. 회색 글자는 모두 4.5:1 이상.
- **정보 위계**: "MY LIBRARY"·"COLLECTION ENTRY" 같은 작은 영문 대문자 라벨과 홍보 문구를 지웠다. 제목 옆에 작품 수를 두고, 상태 문장과 블러 토글을 한 줄로 합쳤다. 1440px에서 첫 표지 위치는 518px → 297px, 390px에서는 690px → 360px.
- **조작 일관성**: 채운 주 버튼은 `작품 추가`와 상세의 `읽기`만 남겼다(반전 흰색). 나머지는 같은 높이의 외곽선 버튼이다. 필터 칩은 알약 모양, 선택하면 반전 색. 배치 선택 체크박스가 라벨 위에 따로 놓이던 버그를 고쳤다. 표지마다 보이던 흰 체크박스는 마우스를 올리거나 포커스하거나 선택했을 때만 보인다(터치 기기에서는 늘 보임).
- **태그 바로 필터**: 메인 목록에 태그 필터가 없어 사이드바 대화상자를 거쳐야 했다. 정렬 줄 아래에 자주 쓰는 태그 줄을 두었다. 사용자 태그를 먼저, 출처 태그는 작품 수 순으로 최대 14개 보여주고, 네임스페이스는 흐리게 표시한다. 누르면 기존 `all_tag` 경로 필터를 쓰고, 다시 누르면 해제된다. `모든 태그`는 기존 대화상자를 연다. 기존 `[data-filter-tag]` 선택자와 겹치지 않게 `data-strip-tag`를 쓴다. 폰에서는 줄 안에서만 가로로 스크롤된다.
- **태그 검색**: 태그 줄 앞에 `태그 찾기` 입력란이 있다. 기존 `/api/library/tags?q=`로 일치하는 태그만 보여준다. Enter를 누르면 첫 결과로 거르고, Esc를 누르면 검색어만 지운다. 목록을 다시 그려도 입력값과 포커스는 유지된다.
- **아이콘**: ☆⚙☷▦ 같은 글리프 대신 한 가지 SVG 외곽선 아이콘 세트를 썼다(`index.html` 안의 sprite). 별점은 SVG 별에 호박색 채움.
- **모바일·태블릿(≤900px)**: 글자 없는 아이콘 레일이 사이트 연결·이미지 찾기·정리를 빈 버튼으로 숨기던 문제가 있었다. 이를 메뉴 버튼 + 시트로 바꿨다. Esc를 누르면 닫히고 포커스는 메뉴 버튼으로 돌아간다. 닫힌 시트는 Tab으로 가지 않는다. 상단 동작과 필터 칩은 자기 줄 안에서만 가로로 스크롤되고 페이지 전체는 가로로 넘치지 않는다. 터치 기기의 대상은 44px 이상이다.
- **정직한 상태**: 검색 결과가 0건일 때 "보관함을 채워 보세요 + 동기화" 대신 "조건에 맞는 작품이 없습니다"를 보여준다. 사이트 연결에서 최근 요청이 실패한 행(예: EH `connection_reset`)은 경고색으로 표시해 저장 상태가 성공처럼 읽히지 않게 했다. 리더 상단 바에 작품 제목을 표시한다.
- **유지한 것**: 목록 썸네일 기본 블러(10px, 모자이크 아님), `object-fit: contain`, 상세/리더 원본 표시, 설정 저장, `display_title`과 원본 제목 분리, 같은 언어 우선과 다른 언어·미확인 언어 후보의 연결 버튼 비활성, 경로·뒤로/앞으로·스크롤 복원·읽기 위치, API helper·오류·취소 로직. 요소 ID는 바꾸지 않았다.

수정 파일: `web/index.html`, `web/style.css`(같은 규칙을 읽을 수 있는 형태로 다시 정리), `web/app.js`(표현용 템플릿, 빈 상태 문구, 리더 제목, 모바일 시트 6줄), `tests/navigation_smoke.py`(1줄), 이 문서.

## 검증 (격리된 합성 fixture)

`work/design-polish/fixture/fixture_server.py`를 사용했다. 임시 DB, PIL로 만든 합성 표지 12개, loopback 전용이며 루프백이 아닌 소켓 연결은 차단했다. 로그인 서비스 상태는 EH `connection_reset` 실패를 흉내 낸 고정값이다. 실제 사이트·쿠키·NAS·개인 미디어는 쓰지 않았다.

| 검사 | 결과 |
| --- | --- |
| taste-skill inspect `--app` (1440/768/390) | 전 4 FAIL·5 WARN → 후 1 FAIL·1 WARN. 남은 FAIL은 의도한 것이다: 스킬이 고른 Inter를 Google Fonts로 불러오지 않았다. Inter에는 한글 글리프가 없고, 개인 NAS 앱이 외부에 글꼴을 요청하지 않게 하려고 로컬 한국어 시스템 글꼴 스택(Pretendard → Apple SD Gothic Neo → Malgun Gothic)을 쓴다. WARN은 파일 없는 작품의 표지 자리(정보만 등록)다. |
| taste-skill lint `--app` | 0 FAIL. WARN은 떠 있는 요소의 그림자(대화상자·토스트·시트), 세션 JSON 입력란의 고정폭 글꼴 |
| 가로 넘침 | 390/768/1440 모두 0 (목록·상세·긴 제목) |
| 키보드 | Tab으로 카드에 도달, 카드 포커스 시 선택 체크 표시, Enter로 상세, Esc로 닫고 스크롤 복원, 모바일 메뉴 Esc·포커스 복귀 |
| `tests/mosaic_smoke.py` | 통과: 블러 기본값, 세 비율 네 가장자리 보존, 그리드·목록 데스크톱·모바일, 원본 상세·리더, 설정 저장, `/unsen` |
| `tests/navigation_smoke.py` | 통과: 6·7쪽 뒤로/앞으로, 딥링크·새로고침, 목록 쿼리·페이지·스크롤 복원, Esc, 지난 응답 취소, 추출 대기 재시도 |
| 태그 줄 (1440/390) | 태그 렌더, 누르면 필터·`aria-pressed`, 다시 누르면 해제, `모든 태그` 대화상자, 대화상자 필터와 `#clear-tag` 해제 시 태그 줄 상태 동기화, 가로 넘침 0. `short_ids_smoke.py`는 기준 HEAD에서도 40행(상세 제목 비교)에서 먼저 실패해 태그 구간까지 가지 못하므로 같은 단계를 직접 실행했다. |
| `node tests/test_candidate_ui.js`, `test_api_errors.js`, `node --check web/app.js`, `git diff --check` | 통과 |
| pytest(test_studio·title_candidates·deployment·tags·short_ids) | 기준 HEAD와 실패 목록이 같다(Windows `fsync`·셸 인자 관련 기존 실패 6개). 새로 생긴 실패는 하나다: `test_runtime_manifest_covers_and_matches_all_deployed_source_files`. web 파일이 바뀌어 `deploy/runtime-manifest.sha256` 해시가 맞지 않는 것으로, 릴리스할 때 메인이 다시 만들어야 한다. 배포 manifest는 작업 범위 밖이라 손대지 않았다. |

브라우저 smoke는 Linux 경로 `/usr/bin/chromium`이 하드코딩되어 있다. 그래서 `fixture/run_smoke.py`로 로컬 Chrome 채널과 Playwright `bypass_csp`(테스트의 `wait_for_function` 문자열 평가용)를 써서 실행했다. 앱 CSP는 그대로다.

`navigation_smoke.py`는 한 줄 바꿨다. 이 검사는 스크롤 400으로 옮긴 뒤 첫 카드를 `click()`한다. 머리 영역이 낮아지자 첫 카드가 화면 위로 나가 Playwright가 클릭 전에 자동 스크롤(400→292)했고, 앱은 292를 정확히 복원했다. 그래서 검사 전제가 레이아웃 높이에 기대고 있었다. `dispatch_event('click')`로 바꿔 선택한 스크롤을 유지한다. 앱의 복원 로직은 바꾸지 않았다.

## 스크린샷 (합성 자료, git 무시 폴더)

`work/design-polish/before/`, `after/`, `verify/`. 이름은 `{폭}-{화면}.png`이며 화면은 library, library-full, list, empty, detail, detail-sources, reader, connections, settings다. verify에는 메뉴, 긴 제목, 토스트, 카드 포커스가 있다.

## 메인에 넘기는 제안: 태그 여러 개 선택

현재 `list_works`는 `all_tag` 하나와 사용자 태그 `tag` 하나만 받는다. 백엔드는 이번 범위 밖이라 바꾸지 않았다. 여러 태그를 AND로 거르려면 다음이 필요하다.

- `server.py`: `/api/works`가 `all_tag`를 여러 번 받는다(`qs.get('all_tag', [])`).
- `store.list_works`: 태그마다 지금의 EXISTS 조건을 하나씩 AND로 붙인다. 개수와 길이에 상한을 둔다.
- `app.js`: `state.allTag`를 배열로 바꾸고, 주소 `all_tag`를 반복 매개변수로 직렬화한다. 태그 줄 칩은 토글이 된다.

이전 북마크(`all_tag` 한 개)는 그대로 호환된다.

## 한계

- 실제 개인 라이브러리·실사이트 데이터로는 확인하지 않았다. 표지 실물의 색·비율 분포는 합성 자료와 다를 수 있다.
- Pretendard는 이 PC에 설치되어 있어 그 글꼴로 렌더됐다. 다른 기기에서는 시스템 한국어 글꼴로 대체된다.
- 업로드·폴더·보이스코믹·이미지 찾기·정리 대화상자는 공통 스타일만 적용됐다. 화면별 look-and-fix는 하지 않았다.
- 상세를 Esc로 닫으면 새 기록이 쌓여 앞으로 가기로 다시 열리지 않는다. 이는 기준 HEAD와 같은 기존 동작이며 바꾸지 않았다.
