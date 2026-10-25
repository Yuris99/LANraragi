# E-Hentai 연결 조사 및 메인 검토 자료

기록일: 2026-10-24. 이 작업은 연결 문제의 원인 확정이나 NAS 복구 완료가 아니다.

## 작업 권한 및 기준

- 작업 공간: `C:/Users/mose1/orca/workspaces/LANraragi/ehentai-connection-fix`
- 배정/현재 브랜치: `Yuris99/ehentai-connection-fix`
- 기준 HEAD: `d034eb12523c6f75a3f4600edc8018392f7f39d8`
- 시작 및 수정 후 가드: `active=true`, `role=worker`, 경로/브랜치 일치.
- 다른 작업트리는 지정된 메인 인계 문서만 읽었다. 메인 역할·통합 권한은 맡지 않았다.

## 실제 접속 조사

전체 로컬 테스트보다 먼저 문서와 `http://127.0.0.1:43120/api/health`를 확인했다.
현재 결과도 `WinError 10061` 연결 거부다. 이는 localhost까지의 경로 실패이며
NAS 서비스 중단, 터널 부재, E-Hentai 인증 실패 중 어느 하나를 확정하지 못한다.
현재 주소를 사용자에게 확인했으나 사용자는 모른다고 답했다.
연결된 브라우저 인벤토리는 비어 있어 Studio 탭에서 대체 경로를 찾지 못했다.
기존 인계/Compose/접속 안내에서 확인한 경로는 NAS loopback 43120과 SSH 터널이다.
대체 접속 경로나 터널을 새로 만들지 않았다.

| 확인 대상 | 결과 |
| --- | --- |
| Studio 적용 버전 | 미확인. 앱 20은 배포 요청 기록 |
| desktop 서비스 적용 버전 | 미확인. 서비스 5는 배포 요청 기록 |
| NAS 저장 세션/최근 요청 모드/HTTP 상태/파싱 결과 | 접근 불가로 미확인 |
| 실제 사이트 인증·댓글·다운로드 | 미검증. 실제 사이트 요청/자료 다운로드 없음 |

## 확인한 코드 결함과 수정

`site_sessions._source_document`는 정상 응답의 HTTP 상태를 진단 trace에 넣지 않았다.
`source_document`는 오류 결과의 `http_status`만 읽어, HTTP 200/206 등을 받은 뒤에도
사이트 연결 화면의 최근 조회에서 HTTP 상태가 사라졌다. 응답 크기 제한처럼
HTTP 응답 이후 검사에서 실패한 경우에도 상태가 사라졌다.

정상 응답/HTTP 오류의 상태를 trace에 기록하고 최근 요청 진단에서 이를 사용한다.
URL·본문·쿠키 값은 진단에 추가하지 않는다. HTTP 응답 수신과 메타데이터 파싱은
분리되어 있으며 `ok`는 문서 수신이라는 기존 의미를 유지한다. 실제 로그인 유효성은
증명하지 않는다. 인증 화면/잘못된 작품 식별자는 기존 메타데이터 파서가 거절한다.
ExHentai의 별도 세션 요구, 엔진 비활성, 재시도/redirect 제한은 그대로다.

변경 파일:

- `studio/site_sessions.py`: HTTP 상태 기록 누락 수정.
- `studio/tests/test_session_import.py`: HTTP 응답 모형에 실제 응답의 `status=200` 추가.
- `studio/tests/test_source_diagnostics.py`: 디스크 세션을 쓰지 않는 합성 회귀 7개.
- 이 검토 문서.

## 검사와 재현

```powershell
python -B -X utf8 -m unittest discover -s studio/tests -p test_source_diagnostics.py -v
python -B -X utf8 -m unittest discover -s studio/tests -p test_metadata.py -v
python -B -X utf8 -m unittest discover -s studio/tests -p test_auto_sources.py -v
git diff --check
```

- 새 회귀 7/7 통과: 정상 갤러리, HTTP200 인증 화면/번호 불일치, 저장 세션과 인증
  유효성 구분, 검색 응답, HTTP403과 연결 실패 구분, 응답 크기 초과, ExHentai 무세션 중지.
- 새 검사를 기준 HEAD의 `site_sessions.py`로 메모리에서 실행하면 HTTP 상태 누락으로
  6개 assertion 실패(인증 화면/식별자 불일치의 두 subtest 포함), 수정 후 모두 통과.
- 메타데이터 11개 중 10개 통과. 자동 출처 15개 중 10개 통과.
- 위 기존 검사 6개 오류는 기준 HEAD에서도 전부 같은 오류로 재현했다:
  Windows의 `os.getuid` 부재 4개, 기존 백업 `os.fsync`의 bad file descriptor 2개.
  Unix 세션 권한 검사를 무력화하거나 백업 코드를 이번 범위에 끌어들이지 않았다.
- 전체 합계: 관련 검사 33개 중 27개 통과, 기존 Windows 환경 오류 6개.
- `test_session_import.py`의 실제 vault/RPC 검사는 이 Windows 환경에서 미검증.
  POSIX 환경에서 함께 재검사해야 한다. WSL/Docker 조회도 접근 거부여서 Linux
  런타임 검증은 수행하지 못했다. 권한·서비스·전역 설정은 변경하지 않았다.
- JS 구문은 stdin으로 검사 통과. UI 변경은 최종 diff에 없다. diff 검사 통과.

## 메인 검토 시 필요한 다음 단계

1. 기존 NAS 서비스/터널 운영 상태와 실제 사용 가능한 Studio 경로를 확인한다.
   이 작업자는 운영 변경을 수행하지 않았다. 터널 재연결/서비스 재시작이 필요하면
   실제 원인을 확인하고 기존 구성의 구체적인 조치에 대해 별도 승인을 받는다.
2. 읽기 전용으로 health의 앱 버전, 사이트 연결의 서비스 기능/세션/최근 요청을 확인한다.
3. 정상 권한의 적법한 테스트 대상으로 실제 메타데이터 파싱·댓글을 별도 확인한다.
   세션 저장이나 HTTP200만으로 성공 처리하지 않는다. 다운로드/NAS 게시 검증은
   이번 운영 데이터 변경 금지 범위 밖이므로 별도 승인이 필요하다.
4. 수정 검토 및 POSIX 검사 후, 필요 시 기존 앱/desktop 배포 채널의 소스 해시와
   적용 버전을 준비한다. 이 작업에서는 release manifest/배포 번호를 변경하지 않았다.

커밋·push·병합·배포 없음. NAS DB·원본·서비스·터널·권한·공개 노출 변경 없음.

## 후속 읽기 전용 확인

사용자의 계속 진행 요청 후 기존 SSH 설정에서 등록된 NAS 대상을 확인했다.
키·비밀번호·쿠키를 읽지 않고 Host/HostName/Port/LocalForward/Include 항목만
조회했다. 실제 값은 이 보고서에 복사하지 않는다.

- 현재 `ssh`/`plink`/`putty` 프로세스와 43100–43140 범위 리스너가 조회되지 않았다.
- localhost 43120은 계속 연결 거부다.
- 등록된 NAS의 SSH 22 및 Studio 43120 TCP 연결은 각각 4초 후 시간 초과였다.
  NAS Studio가 loopback 전용이라는 기존 구성상 LAN의 43120 무응답만으로
  Studio 중단을 판단할 수 없다. SSH 무응답도 전원/네트워크/주소/방화벽 중
  원인을 확정하지 못한다. SSH 인증이나 터널 연결은 시도하지 않았다.
- 위 조회는 최초 샌드박스의 접근 거부와 구분하기 위해 정상 권한 승인 흐름으로
  다시 확인했다. 권한 확대 후에도 NAS TCP 시간 초과는 동일했다.
- Docker는 정상 권한으로 재조회해도 Linux engine pipe가 없었다. 단순 클라이언트
  권한 오류와 구분되며, 현재 Linux Docker 검사를 실행할 수 없다. Docker를
  시작하거나 새 컨테이너/이미지를 만들지는 않았다.

실제 검증의 선행 조건은 기존 NAS 관리 접속 경로가 다시 응답하는 것이다.
메인은 NAS의 전원/네트워크/기존 SSH 대상 유효성을 먼저 확인하고, 필요한
운영 조치를 별도 승인 범위에서 결정해야 한다. 현재 증거로 인증 문제를
수정했다거나 서비스를 재시작하면 해결된다고 단정하지 않는다.
