# Studio 한정 SSH 터널 변경안 — 적용 전 별도 승인

현재 사용자 보고상 NAS의 LANraragi와 Studio는 healthy다. SSH 로그인은 성공하지만 유효 정책은 `allowtcpforwarding no`, `disableforwarding no`, `permitopen any`여서 터널 요청이 거부된다. 기존 시험 배포 승인에 기존 NAS SSH 전역 변경까지 포함됐다고 가정하지 않는다.

## 구체적 변경 범위

기존 `/etc/ssh/sshd_config`에 아래처럼 **확인된 계정 하나 + 확인된 PC IPv4 주소 하나**에만 적용되는 블록을 제안한다. 예시 주소는 문서용이며 실제 값은 사용자가 제공한 SSH 연결 정보로 정한다.

```text
Match User verified_user Address 192.0.2.50
    AllowTcpForwarding local
    PermitOpen 127.0.0.1:43120
```

기존 전역 `AllowTcpForwarding no`는 유지한다. 허용 목적지는 NAS loopback의 Studio 포트 하나이며 원격 포트 포워딩은 허용하지 않는다. Docker/NMLO/Stash 설정이나 공개 인터넷 리스너를 변경하지 않는다. 기존 SSH 서비스에 대한 구성 반영은 승인 대상이다.

[OpenSSH의 AllowTcpForwarding/Match/PermitOpen 설명](https://man.openbsd.org/sshd_config)은 local 포워딩과 목적지 제한의 의미를 정의한다. `ssh_forwarding_plan.py`는 검토용 블록을 생성하고 합성 설정을 검사하는 도구이며 **NAS 설정을 설치하거나 SSH 데몬을 reload하지 않는다**.

## 승인 후 적용 절차

1. 기존 NAS SSH 관리 창을 유지한다. 실제 사용 중인 config와 SSH 실행 방식을 확인한다. 기존 config를 NAS 안의 새 백업으로 보존하고 원래 파일을 덮어쓰기 전에 후보 파일을 별도로 작성한다. 백업은 클라우드/Git으로 보내지 않는다.
2. `sshd -t -f 후보`로 문법 검사를 수행한다. `sshd -T -C ... -f 후보`에는 실제 사용자/클라이언트 주소/NAS 주소/SSH 포트를 전달한다. 대상의 결과가 `allowtcpforwarding local`, `permitopen 127.0.0.1:43120`, `disableforwarding no`일 때만 진행한다.
3. 다른 계정과 다른 클라이언트 주소의 유효 정책을 원본과 비교한다. 기존 Include/Match/명령행 옵션 때문에 제한이 예상과 다르면 적용하지 않는다. 전역 허용으로 우회하지 않는다.
4. 후보를 반영하기 전에 SSH main PID/PidFile·실행 파일을 확인한다. 지원되는 안전한 reload 방식이 확인되지 않으면 중지한다. [OpenSSH는 main 데몬의 SIGHUP 구성 재읽기를 문서화](https://man.openbsd.org/sshd)한다. 포트/서비스 이름을 추정하거나 모든 sshd 프로세스를 종료하지 않는다.
5. 새 PC 터널 연결로 Studio 로그인 화면을 확인한 뒤 기존 관리 창을 닫는다. 오류 시 유지 중인 관리 창에서 해당 백업을 복원하고 문법 검사 후 같은 reload 경로로 원상 복구한다. 백업 경로를 적용 결과에 명시한다.

현재 단계는 **검사된 제안**이다. NAS에 이 변경을 적용·reload했거나 PC 브라우저 연결이 성공했다고 표시하지 않는다. IP가 바뀌면 새 PC 주소를 별도 확인해야 한다.

## 검증

표준 OpenSSH `sshd -T`와 임시 생성한 합성 host key만 사용해 검사했다. SSH 서버를 실행하거나 실제 NAS host key를 읽지 않았다. 대상 한정 허용, 두 가지 비대상 컨텍스트의 전체 정책 동일성, 기존 Match 차단 시 중지, DisableForwarding 차단 시 중지, 와일드카드/줄바꿈/중복 블록 거부를 확인했다. 실제 NAS 후보 config는 그 장치에서 위 절차로 다시 검사해야 한다.
