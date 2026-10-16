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

## 승인 후 실행 도구

`configure-tunnel.sh`는 기본 `plan`에서 변경하지 않는다. `apply 사용자 PC_IP NAS_IP SSH포트`는 sudo에서만 실행하며 기존 보고의 deny/no/any 정책과 정확한 주 데몬/PidFile/실행 파일/프로세스 식별값을 확인한다. 명령행 config/option override, 예상과 다른 기존 Match, 다른 인증 정책 변화, 원본 동시 변경은 적용 전에 중지한다. 후보/원본/유효 정책 검사는 NAS의 새 root 전용 `/etc/ssh/.studio-tunnel.XXXXXX` 디렉터리에 보관하며 전송하지 않는다.

검사 통과 후 같은 파일시스템에서 후보를 반영하고 확인된 main PID 하나에만 HUP을 보낸다. 반영 후 오류가 나면 원본 복원을 시도하며, 데몬 식별이 달라졌으면 임의 프로세스에 신호를 보내지 않는다. `rollback 백업디렉터리`도 현재 파일이 해당 적용본과 동일할 때만 복원한다. 기존 SSH 관리 창을 유지하고 출력의 백업/복구 경로를 NAS 안에 보존한다.

승인된 계정/주소로 다음 형태를 사용한다(아래는 문서용 값이다).

```sh
sudo sh configure-tunnel.sh apply verified_user 192.0.2.50 192.0.2.1 22
```

성공 후 PC에서 **기존에 거부된 터널 연결을 종료하고 새 SSH 연결**을 연다. 기존 SSH 연결에는 이전 포워딩 정책이 남을 수 있다. NAS 관리 세션은 새 터널/로그인 화면 확인까지 유지한다. 새 연결이 실패하면 출력과 백업 경로로 진단하며 전역 허용이나 모든 sshd 종료로 바꾸지 않는다.

현재 대화에서는 사용자에게 계정·PC·Studio 목적지 범위를 제시한 뒤 승인을 받았다. 실제 NAS 적용/새 터널 성공은 사용자의 실행 결과를 받아야 확인할 수 있다.
