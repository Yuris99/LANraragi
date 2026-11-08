# Library 허브 로그인 · 공통 디자인 적용안

작성 2026-11-08. 대상 `library.yuris.io` 게이트웨이(NGINX). **아직 적용하지 않은 후보안**이다. 실제 적용은 사용자 승인 후, live 설정 비교·백업·`nginx -t` 순서로 한다.

## 바뀌는 점

| 지금 | 바뀐 뒤 |
| --- | --- |
| 브라우저 Basic 팝업. 로그인 화면·로그아웃 없음 | `/login` 허브 화면에서 한 번 로그인. 상단 바에 로그아웃 |
| 섹션 인증 검사가 `/api/health`(LANraragi까지 호출) | 가벼운 `/api/auth/check`(204/401, 외부 호출 없음) |
| 음성은 사용자 Basic을 그대로 Audio에 전달 | 허브 쿠키로 검사한 뒤 게이트웨이가 Audio 전용 자격을 넣음 |
| 섹션마다 다른 디자인, 오가는 메뉴 없음 | `/_library/tokens.css` + `/_library/shell.js` 공통 상단 바 |

Studio 쪽 구현: `studio/library_session.py`, `server.py`의 `/login`, `/api/session*`, `/api/auth/check`, `/_library/*`. 서명 쿠키 `library_session`(HttpOnly, SameSite=Lax, HTTPS면 Secure, 30일). 서명 키는 `session.key`(DB 폴더, 0600)와 `STUDIO_PASSWORD`로 만든다. 비밀번호를 바꾸거나 `session.key`를 지우면 모든 브라우저가 로그아웃된다. Basic 자격도 계속 받으므로 스크립트·기존 클라이언트는 그대로 동작한다. 쿠키 인증 POST는 같은 Origin일 때만 허용한다.

## 게이트웨이 변경 후보 (server 블록 안)

```nginx
# http 블록: 허브 쿠키를 섹션 앱으로 넘기지 않는다.
map $http_cookie $cookie_without_library {
    default $http_cookie;
    "~^(?<pre>.*?)(?:^|;\s*)library_session=[^;]*(?<post>.*)$" "$pre$post";
}

# server 블록
location = /internal/library-auth {
    internal;
    set $library_auth http://studio:8090;
    proxy_pass $library_auth/api/auth/check;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header Host library.yuris.io;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header Cookie $http_cookie;
}
location @library_login { return 303 /login?next=$request_uri; }
```

각 섹션 location(`/audio/`, `/roulette/`, `/cyoa/`, `/real/`; diet는 별도 운영이라 담당 세션이 판단)에:

```nginx
auth_request /internal/library-auth;
error_page 401 = @library_login;
```

- 기존 `/internal/roulette-auth`, `/internal/real-auth`는 위 하나로 대체한다(`/internal/diet-auth`는 diet 담당 판단).
- `/audio/`: `proxy_set_header Authorization "Basic <AUDIO 전용 자격 base64>";` 로 바꾼다. 자격 값은 NAS 게이트웨이 설정에만 두고 저장소에 넣지 않는다.
- `/real/`: `proxy_set_header Cookie $cookie_without_library;` (Stash 쿠키는 유지, 허브 쿠키는 제거).
- Studio `location /`: `proxy_set_header Cookie "";` → `proxy_set_header Cookie $http_cookie;` (허브 쿠키가 Studio에 도달해야 함).
- `/api/worker`, `/auth`, Authelia 차단 줄은 그대로 둔다.

## 적용 후 확인

1. 로그아웃 상태: `/`, `/audio/`, `/roulette/`, `/cyoa/`, `/real/` 탐색 → `/login?next=...`로 303. API는 401, Basic 팝업 없음.
2. 로그인 후: 다섯 섹션 모두 200, 상단 바 표시, 로그아웃 → 다시 303.
3. 위조 쿠키·다른 Origin POST → 401/403. `/api/worker` 외부 403 유지.
4. Stash 로그인 상태가 허브 로그인과 별개로 유지되는지, 음성 재생 Range(206)가 유지되는지 확인.

롤백: 게이트웨이 백업 설정 복원 후 reload. Studio 코드는 Basic도 계속 받으므로 게이트웨이만 되돌려도 기존 방식으로 동작한다.
