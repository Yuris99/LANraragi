# Library 통합 · 디자인 통일 계획

작성 2026-11-08. 담당: 만화 스튜디오 메인 세션(통합·디자인 담당). 다이어트(`/diet/`)는 별도로 운영하므로 범위에서 뺀다.

## 목표

`library.yuris.io`의 다섯 섹션을 **한 서비스처럼** 만든다.

1. 로그인은 허브(`/login`)에서 한 번만 한다. 모든 섹션이 같은 세션을 쓰고, 로그아웃도 한 번이면 된다.
2. 모든 섹션이 같은 상단 바(만화 · 음성 · 룰렛 · CYOA · 실사)로 서로 오간다.
3. 만화 스튜디오 디자인을 기준으로 색·글꼴·간격·컴포넌트를 하나로 맞춘다.

## 대상

| 섹션 | 경로 | 프로젝트 | 형태 | 현재 스타일 |
| --- | --- | --- | --- | --- |
| 만화 | `/` | LANraragi `feature/library-studio` | Git | 기준. Pretendard, 따뜻한 검정 + 호박색 |
| 음성 | `/audio/` | LANraragi-Audio `feature/audio-studio` | Git(같은 저장소, 다른 작업트리) | Segoe UI, 토큰 8개 |
| 룰렛 | `/roulette/` | FR `main` | Git, 가드 미등록 | Poppins·Jua, CSS 8개 |
| CYOA | `/cyoa/` | CYOA-Studio | 폴더(Git 아님) | IBM Plex Sans, 게이트웨이 미연결 |
| 실사 | `/real/` | NMLO(Stash 커스텀 UI) | 폴더(Git 아님) | Stash 기본 + `nmlo-stash-ui.css` |

## 섹션 색

디자인과 UI/UX는 다섯 섹션이 같다. **포인트 색(`--lib-accent`) 하나만** 섹션마다 다르다. 배경·면·선·글자·경고(`--lib-danger`)·성공(`--lib-success`)은 모두 공통이다.

| 섹션 | 색 | 토큰 | 배경 대비 |
| --- | --- | --- | --- |
| 만화 | 호박 `#e8b04a` | `--lib-accent-manga` | 9.9:1 |
| 음성 | 청록 `#5ec8b6` | `--lib-accent-audio` | 9.6:1 |
| 룰렛 | 장미 `#ee8fc4` | `--lib-accent-roulette` | 8.7:1 |
| CYOA | 보라 `#ab9ff2` | `--lib-accent-cyoa` | 8.3:1 |
| 실사 | 하늘 `#72b6ec` | `--lib-accent-real` | 8.9:1 |

- 각 섹션 HTML은 `<html data-library-section="audio">`처럼 자기 섹션을 표시한다. 그러면 `--lib-accent`, `--lib-accent-soft`, `--lib-accent-ink`가 자동으로 그 섹션 색이 된다.
- 섹션 코드는 `--lib-accent*`만 쓴다. 색상값을 직접 쓰지 않는다.
- 포인트 색은 지금 위치 표시, 진행률·평점·즐겨찾기, 주요 강조에만 쓴다. 버튼 주 색은 공통(밝은 글자색 반전)으로 둔다.
- 상단 바에서는 현재 섹션 아이콘과 밑줄이 그 섹션 색으로 표시된다. 다른 탭에 마우스를 올리면 그 섹션 색이 미리 보인다.
- 로그인 화면은 허브이므로 만화(호박) 색을 쓴다.

## 일관성 원칙

1. **원본은 하나다.** 토큰·상단 바·공통 컴포넌트는 Studio의 `library_kit.py`에만 두고 `/_library/*`로 제공한다. 각 섹션은 불러오기만 하고 복사·수정하지 않는다.
2. **작업자는 디자인을 정하지 않는다.** 할 수 있는 일은 ① 기존 변수를 `--lib-*`에 연결, ② 공통 컴포넌트 클래스 적용, ③ 상단 바 때문에 생긴 레이아웃 문제 수정, 이 세 가지다.
3. **금지:** 새 색상값·글꼴·그림자·모서리값 추가, 기능·API·데이터 변경, 공통 키트 복사.
4. **검사는 같은 기준으로 한다.** 정해진 화면 크기(1440×900, 390×844)로 캡처하고, 토큰 밖의 색상값이 남았는지 자동 검사한다.
5. **최종 승인은 통합 세션이 한다.** 다섯 섹션 캡처를 나란히 비교한 뒤 승인한다. 승인 전에는 병합·배포하지 않는다.

## 단계

### 1단계 · 허브 로그인 + 공통 바 — 완료(커밋 `29a1505f`, 미배포)

- `library_session.py`: 서명 쿠키 세션, 로그인 실패 시 대기, Origin 검사.
- `/login`, `/api/session*`, `/api/auth/check`(게이트웨이 인증 확인용, 204/401).
- `library_kit.py`: `tokens.css`, `bar.css`, `shell.js`, 로그인 화면. 기존 업데이트 채널로 배포 가능.
- 만화 화면에 적용. 테스트 10개 추가, 기존 Studio 테스트 통과.

### 2단계 · 공통 컴포넌트와 규격 확정 — 완료(미배포)

- `components.css`를 `library_kit.py`에 추가한다. 대상: 버튼(주·보조·텍스트·위험), 입력칸, 선택칸, 카드, 목록 행, 대화상자, 알림(토스트), 빈 화면, 사이드바 메뉴, 페이지 제목, 배지.
- 만화 화면을 이 클래스로 정리해 **기준 화면**을 확정한다. 데스크톱·모바일 캡처를 남긴다.
- 이 문서에 컴포넌트 규격표와 작업자 검사 목록을 추가한다.
- **2단계를 확정하기 전에는 작업자를 띄우지 않는다.**

#### 2단계 결과 — 공통 컴포넌트 규격

기준 화면: 로그인 후 **`/library-guide`**. 섹션 버튼을 누르면 포인트 색만 바뀐다. 작업자 결과는 이 화면과 나란히 놓고 비교한다.

불러오는 순서(각 섹션 HTML `<head>`):

```html
<html lang="ko" data-library-section="audio">  <!-- manga|audio|roulette|cyoa|real -->
<link rel="stylesheet" href="/_library/tokens.css">
<link rel="stylesheet" href="/_library/components.css">
<link rel="stylesheet" href="섹션 자체 CSS">     <!-- 공통 뒤에 둔다 -->
<script src="/_library/shell.js" defer></script>
```

| 용도 | 클래스 | 비고 |
| --- | --- | --- |
| 페이지 기본 | `body.lib-base` | 배경·글꼴·포커스 링 |
| 레이아웃 | `.lib-sidebar` + `.lib-main` | 232px 사이드바, 900px 이하에서 시트(`.lib-nav-open`) |
| 섹션 제목 | `.lib-section-title` + `small` | 사이드바 맨 위. 로고는 공통 바에만 둔다 |
| 메뉴 | `.lib-nav-label`, `.lib-nav`, `.lib-nav-item(.is-active)`, `.lib-count` | 선택 항목 아이콘 = 섹션 색 |
| 제목 | `.lib-page-head`, `.lib-h1`, `.lib-h2`, `.lib-page-count`, `.lib-lead`, `.lib-muted` | h1 26px / h2 18px |
| 툴바 | `.lib-toolbar`, `.lib-actions` | 아래 구분선 |
| 버튼 | `.lib-btn`(보조), `.lib-btn-primary`(주, 반전), `.lib-btn-text`, `.lib-btn-danger`, `.lib-icon-btn` | 주 버튼은 화면당 하나. 섹션 색을 버튼 배경에 쓰지 않는다 |
| 입력 | `.lib-field`(label), `.lib-input`(input·select·textarea), `.lib-hint`, `.lib-search` | 높이 40px |
| 필터·태그 | `.lib-chips`, `.lib-chip(.is-selected)`, `.lib-tag`, `.lib-badge(-accent/-danger/-success)` | |
| 카드 | `.lib-grid`, `.lib-cover-card`, `.lib-cover(-wide/-square/-fill)`, `.lib-cover-title`, `.lib-cover-meta`, `.lib-cover-progress>i` | 기본 3:4, 영상·사진은 wide/square |
| 목록 | `.lib-list`, `.lib-row`, `.lib-row-main`, `.lib-row-title`, `.lib-row-meta` | |
| 패널 | `.lib-panel` | |
| 대화상자 | `dialog.lib-dialog`, `.lib-dialog-actions` | |
| 알림 | `.lib-notice(-danger/-success)`, `.lib-toast` | |
| 빈 화면 | `.lib-empty` | 아이콘 + h2 + 설명 + 주 버튼 |
| 진행·평점 | `.lib-progress>i`, `.lib-rating` | 섹션 색 |

#### 작업자 검사 목록

1. `<html data-library-section>`과 위 불러오기 순서를 지켰다.
2. 섹션 CSS에 남은 색상값(`#…`, `rgb(…)`, `hsl(…)`)은 `--lib-*` 토큰 연결과 검은 그림자·오버레이(`rgb(0 0 0 / …)`)뿐이다. 검사 명령: `rg -n "#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(" <섹션 CSS>`. 남은 줄마다 이유를 보고한다.
3. 글꼴은 `--lib-font` 하나다. 외부 웹폰트를 불러오지 않는다.
4. 상단 바와 겹치는 고정 요소가 없다(`--lib-bar-h` 사용).
5. 1440×900, 390×844 두 크기로 주요 화면을 캡처해 `/library-guide`와 비교했다.
6. 기능·API·데이터를 바꾸지 않았다. 기존 테스트를 실행했다.

### 3단계 · 섹션별 Claude 작업자

| 섹션 | 선행 조건 | 작업 공간 |
| --- | --- | --- |
| 음성 | 음성 메인 세션의 미커밋 변경을 먼저 커밋 | `feature/audio-studio` 기준 새 작업트리 |
| 룰렛 | FR 가드 등록 | FR `main` 기준 새 작업트리 |
| CYOA | 그 프로젝트 세션이 같은 시간에 작업하지 않음 | 폴더 직접 수정(Git 아님). 작업 전 백업 |
| 실사 | 같음 | Stash 커스텀 CSS/JS(`deploy/stash-ui`)만 수정 |

작업자 지시서에 넣을 공통 내용: 이 문서 경로, 허용·금지 범위, 불러올 두 줄(`/_library/tokens.css`, `/_library/shell.js`, 필요하면 `components.css`), 캡처 크기, 색상값 검사, 보고 형식(브랜치/HEAD, 변경 파일, 검사 결과, 캡처 경로, 남은 문제). 푸시·병합·배포는 하지 않는다.

### 4단계 · 통합 검토

- 다섯 섹션 캡처를 나란히 비교한다. 어긋난 곳은 해당 작업자에게 다시 보낸다.
- 로그인→섹션 이동→로그아웃 흐름을 로컬에서 확인한다.

### 5단계 · 적용(각각 사용자 승인 필요)

1. 만화 Studio 푸시와 앱 42 배포.
2. 게이트웨이 변경: `deploy/library-gateway/LIBRARY_HUB_LOGIN.ko.md`. live 설정을 비교하고 백업한 뒤 `nginx -t`로 검사하고 reload.
3. 섹션별 배포. 각 프로젝트의 기존 배포 절차를 따른다.
4. 실제 `library.yuris.io`에서 확인: 로그아웃 상태에서 섹션별 303, 로그인 후 200, 위조 쿠키 401, `/api/worker` 403, 음성 Range 206, Stash 로그인 유지.

## 승인이 필요한 결정

- [ ] 2단계 이후 3단계 작업자 생성(다른 프로젝트 작업 공간 생성·가드 등록 포함)
- [ ] 게이트웨이 변경 적용
- [ ] 만화 푸시·배포, 섹션별 배포

## 위험과 대응

| 위험 | 대응 |
| --- | --- |
| 작업자마다 해석이 달라짐 | 원본 하나 + 컴포넌트 클래스 고정 + 색상값 검사 + 통합 세션 비교 승인 |
| 음성 세션의 미커밋 변경과 충돌 | 커밋된 상태에서만 작업트리 생성 |
| 폴더 프로젝트(CYOA·NMLO) 동시 수정 | 작업 시간을 분리하고 작업 전 백업 |
| 게이트웨이 변경 실패 | Studio가 Basic도 계속 받으므로 백업 설정 복원만으로 원래대로 돌아감 |
| Stash 업데이트로 커스텀 CSS 깨짐 | Stash 선택자는 최소로 쓰고, 상단 바는 shadow DOM이라 영향 없음 |
