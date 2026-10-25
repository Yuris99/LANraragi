# EhViewer와 Studio의 접속 구현 비교

2026-10-25 KST. 공개 소스 읽기 비교만 수행했다. EhViewer 설치/실행, NAS 설정 변경,
추가 E-Hentai 요청은 하지 않았다. 이 문서는 실제 수집 성공 보고가 아니다.

## 이전 참고의 실제 범위

`SOURCE_METADATA.md`는 EhViewer의 상세/페이지 파서·쿠키 저장소·다운로드 상태 구조를
검토했다고 기록하며 Java/Kotlin 코드를 복사하거나 실행하지 않았다고 명시한다.
실제 전송 엔진의 기능 동등성이나 같은 NAS 환경의 연결 성공을 검증한 기록은 아니다.

기준은 해당 문서에 지정된
[xiaojieonly/Ehviewer_CN_SXJ 고정 커밋 dfe35624](https://github.com/xiaojieonly/Ehviewer_CN_SXJ/tree/dfe356244d234c91f2bf65af60903f80b407a838)다.
공개 Git tree와 아래 실제 소스를 읽었다. 참고 복사본은 Git 밖의 Orca scratch에만 저장했다.

## 확인한 차이

| 항목 | 고정 EhViewer 소스 | 현재 Studio | 의미 |
| --- | --- | --- | --- |
| HTTP 전송 | OkHttp, 연결 풀, 연결 실패 복구, 쿠키 저장소, 캐시 | CPython/OpenSSL의 urllib opener와 요청별 CookieJar | 같은 전송 구현이 아니다. 차이가 현재 reset 원인이라는 증거는 아직 없다 |
| DNS | 사용자 hosts/내장 hosts/선택 DoH/시스템 조회 분기 | 기본 해석 경로 | 실제 DNS/접속 경로가 같다고 가정할 수 없다. 내장 IP/DoH를 임의 이식하지 않는다 |
| TLS | 설정/VPN 상태에 따른 별도 socket factory 및 예외 시 trust manager 분기 | 기본 인증서/호스트 검증, 별도 우회 분기 없음 | 전송 소스를 무조건 복사하지 않는다. 인증서 검증 생략이나 접속 경로 변경은 적용하지 않았다 |
| 요청 헤더 | Chrome을 식별하는 UA와 사이트 Referer/Origin 등을 구성 | LibraryStudio 식별 UA, 제한된 Accept | 차이는 사실이나 브라우저 UA 위장으로 해결하지 않는다 |
| 세션 | 지속 cookie repository와 요청별 추가 설정 cookie | 명시적으로 가져온 계정 세션만 사용, 요청별 jar | 세션 존재는 두 구현 모두 실제 접근 성공의 증명이 아니다 |
| 정보 수집 | 목록 보강용 gdata POST, 상세/댓글은 별도 HTML GET/파싱 | 상세 HTML GET/파싱 | API 사용만으로 댓글/페이지나 현재 전송 reset이 해결된다고 할 수 없다 |

### 근거 소스

- [EhApplication.java L378-L469](https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/dfe356244d234c91f2bf65af60903f80b407a838/app/src/main/java/com/hippo/ehviewer/EhApplication.java#L378-L469): OkHttp 구성과 조건부 TLS 경로.
- [EhHosts.java](https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/dfe356244d234c91f2bf65af60903f80b407a838/app/src/main/java/com/hippo/ehviewer/client/EhHosts.java): DNS 경로와 결과 선택.
- [EhSSLSocketFactory.java](https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/dfe356244d234c91f2bf65af60903f80b407a838/app/src/main/java/com/hippo/network/EhSSLSocketFactory.java) 및 [EhX509TrustManager.java](https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/dfe356244d234c91f2bf65af60903f80b407a838/app/src/main/java/com/hippo/network/EhX509TrustManager.java): 별도 socket 생성과 일부 fallback의 빈 신뢰 검사 구현. 모든 경로가 검증을 생략한다고 일반화하지 않는다.
- [ChromeRequestBuilder.java](https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/dfe356244d234c91f2bf65af60903f80b407a838/app/src/main/java/com/hippo/okhttp/ChromeRequestBuilder.java) 및 [EhRequestBuilder.java](https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/dfe356244d234c91f2bf65af60903f80b407a838/app/src/main/java/com/hippo/ehviewer/client/EhRequestBuilder.java): 헤더 구성.
- [EhCookieStore.java](https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/dfe356244d234c91f2bf65af60903f80b407a838/app/src/main/java/com/hippo/ehviewer/client/EhCookieStore.java): 계정 cookie 존재 판정과 요청용 cookie 조합. 사용자 기기의 실제 설정/쿠키는 읽지 않았다.
- [EhEngine.java L301-L390](https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/dfe356244d234c91f2bf65af60903f80b407a838/app/src/main/java/com/hippo/ehviewer/client/EhEngine.java#L301-L390): gdata 목록 보강과 상세 HTML 요청은 별도 경로.
- [EhUrl.java](https://github.com/xiaojieonly/Ehviewer_CN_SXJ/blob/dfe356244d234c91f2bf65af60903f80b407a838/app/src/main/java/com/hippo/ehviewer/client/EhUrl.java): 이 기준의 E-Hentai API는 같은 e-hentai.org 호스트의 api.php다. 별도 LANraragi EH 플러그인은 api.e-hentai.org를 쓰지만 이를 현재 오류 뒤의 우회/fallback으로 호출하지 않았다.

## 현재 실패와 연결할 수 있는 범위

확정된 최신 실패는 `saved_session / unavailable / connection_reset / HTTP status 없음`이다.
문서가 반환되지 않아 Studio의 상세 파서까지 도달하지 못했다. 따라서 파서 구조를 참고했다는
이전 조사만으로 현재 접속 동작을 검증했다고 보고할 수 없다.

Android EhViewer와 NAS Python은 OS·TLS 구현·DNS·프록시·설정이 다를 수 있다.
실제 사용 중인 Android 앱의 fork/버전/네트워크 옵션은 확인하지 않았으므로, 공개 소스의
설정 분기가 사용자 기기에서 켜져 있다거나 이것이 NAS reset의 원인이라고 단정하지 않는다.

## 최소 해결 검토 순서

1. 준비된 읽기 전용 단계 관찰 도구를 메인이 독립 검토한 뒤, DSM 인증 복구 후 기존 정상 사용자 권한에서 원래 테스트 URL 1회만 관찰한다. 실제 요청 전 담당/횟수와 간격을 공유한다.
2. 표준 DNS/TCP/TLS/HTTP 헤더 중 어느 단계인지와 실행환경 proxy/CA override 유무를 먼저 확인한다. 설정값·키·URL·응답 문서·예외 본문은 출력하지 않는다.
3. 정상 클라이언트의 일시적 전송 오류 복구가 필요한 경우에만 동일 출처·동일 인증·인증서 검증을 유지하는 제한적 복구를 별도 설계/검사한다. 현재 코드는 자동 재시도하지 않는다. HTTP403/429·인증서·추가 인증/접근 제한에 대한 반복이나 다른 경로 대체는 제안하지 않는다.
4. DNS/TLS/권한/브라우저 위장이나 인증서 검증 생략 분기는 옮기지 않는다. 다른 HTTP 라이브러리나 API로 바꾸면 해결된다는 추측성 배포도 하지 않는다.

이 비교 결과는 메인에 검토용으로 전달한다. 런타임 코드/manifest/배포 번호 변경이 없으므로
새 테스트나 배포를 추가하지 않았다. 실제 NAS 단계 관찰과 새 수집 성공 확인은 남아 있다.
