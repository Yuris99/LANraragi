# 실제 만화 파일 삭제

상세 화면의 **원본 파일 삭제**는 확인창에서 파일명·크기를 보여주고, 영구 삭제 확인 체크 후 **실제 파일 영구 삭제**를 눌렀을 때만 작업을 등록한다. 미리보기·취소·창 닫기만으로 파일을 삭제하지 않는다. 확정한 작업은 창을 닫아도 진행된다. 한 번에 한 작품의 파일만 처리한다. 제목·태그·출처·평점·즐겨찾기·읽기 기록은 남고, 완료 후 파일 연결만 해제된다.

기존 앱 배포 통로는 NAS 원본 쓰기 권한을 줄 수 없다. 호환 실행기는 앱43 이상 배포와 **별도 NAS-local 작업자 설치**가 모두 필요하다. 작업자가 없거나 코드 해시·최근 heartbeat가 맞지 않으면 삭제 요청을 받지 않는다. 설치만으로 운영 작품을 삭제하거나 예제 삭제 요청을 만들지 않는다.

`install-file-deletion.sh preview`는 변경 없이 계획만 표시한다. `install <검증한 40자리 소스 커밋> <file_deletion.py의 SHA256>`은 NAS 관리자 설치다. 기존 LANraragi `NASOriginals` RO mount에서 실제 원본 루트를 확인해 그 안의 **manga/images 두 폴더만** 새 작업자에 RW로 연결한다. 기존 Studio/LANraragi의 권한·마운트·Compose·배포 컨트롤러·ACL은 바꾸지 않고 기존 서비스를 재시작하지 않는다.

새 작업자 `library-studio-file-deletion`은 고정 이미지/코드, network none, RO rootfs, 메모리256MiB·swap 없음, Docker socket/포트 없음으로 실행된다. 부트스트랩에만 UID0과 DAC_OVERRIDE/SETUID/SETGID를 쓰고, 원본·DB를 열기 전에 기존 Studio의 비루트 UID/GID로 real/effective/saved ID를 모두 영구 전환한다. 이후 DAC_OVERRIDE만 남고 root 복귀·사용자/그룹 전환 권한은 없다. DB 접근 중에는 DAC_OVERRIDE의 effective 권한도 내린다. 자기 Studio data/uploads만 추가 RW이며 DB/WAL/SHM의 비루트 소유권을 보존한다. 코드 디렉터리는 NAS root 소유0700, 코드0400/RO mount로 고정하고 앱 자동 배포로 교체하지 않는다.

## NAS 커널 호환 자원 제한

실제 Docker24.0.2/커널4.4.302+에서는 CPU CFS quota/period와 pids cgroup이 미지원이었다. 기존 `--cpus 0.5 --pids-limit 32` 설치는 실행하지 않았다. 호환 v2는 이 차이를 사용자에게 제시하고 승인받은 뒤 설치한다.

- 프로세스·스레드는 영구 비루트 전환 후 `RLIMIT_NPROC=32:32`로 제한한다. UID0·CAP_SYS_ADMIN·CAP_SYS_RESOURCE의 한도 예외가 없다. 이 한도는 컨테이너별 pids cgroup이 아니라 **같은 real UID 전체의 Linux 스레드 수를 기준으로 자식 생성을 차단**한다. 다른 NAS 프로세스가 같은 UID를 사용하면 작업자의 가용 자식 수는 더 적을 수 있다. 정상 삭제 작업자는 자식/스레드를 만들지 않는 단일 프로세스다.
- CPU는 논리CPU0 하나에 고정하고 CPU shares128·nice19로 낮은 우선순위를 적용한다. 파일 확인은 작은 블록마다 CPU 사용 시간을 측정해 평균 약0.5 CPU를 목표로 쉰다. **이 평균 속도 제어는 커널의 0.5 CPU 강제 상한과 동일하지 않으며, 순간 최대는 고정된 논리CPU 한 개**다. CPU shares도 상대 가중치이며 고정 비율 상한이 아니다.
- 메모리는256MiB로 제한하고 memory-swap도256MiB로 지정해 작업자 swap을 허용하지 않는다. 이미지의 자동 healthcheck는 끄며 heartbeat로 확인한다.
- 설치기는 해당 NAS의 memory/swap/cpu-shares/cpuset 지원을 확인한다. 고정 코드만 연결한 network-none/RO 컨테이너와 전용 tmpfs에서 권한 전환·root 복귀 거부·NPROC 실제 EAGAIN 차단·DB 소유권을 먼저 시험한다. 원본·운영 DB 볼륨은 이 시험에 연결하지 않는다. 시험이 실패하면 실제 삭제 작업자를 시작하지 않는다.

미리보기는 실제 백엔드 다운로드 전체 SHA256과 크기 및 LANraragi ID를 확인한다. 작업자는 정해진 저장소에서 실제 파일 전체 해시가 일치하는 유일한 파일을 찾고, 확정 뒤 파일/작품 연결/진행 중 다운로드를 다시 확인한다. 중복 후보·경로 이탈·링크·NAS 내부 폴더·변경된 파일은 삭제하지 않는다. 폴더 재귀 삭제와 NAS 원본 ACL 변경은 구현하지 않는다.

파일 경로와 inode/크기/시간을 내구성 있는 삭제 intent에 먼저 기록한다. 중단 후에는 그 동일한 경로만 복구하며 새 대상을 추측하지 않는다. 삭제 완료 기록은 오래된 백엔드 색인의 재연결과 Studio 미디어 제공을 막는다. 명시적인 재업로드 또는 전체 해시가 검증된 새 다운로드로 파일을 복원할 수 있다. 백업·NAS 휴지통·스냅샷까지 지우는 보안 삭제 기능은 아니다.

설치 후 관리 API `/api/works/<작품ID>/file-deletion`의 `ready`를 읽기 전용으로 확인한다. 운영 작품을 자동으로 삭제해 설치 검증하지 않는다. 작업자 중지는 이 고정 이름의 컨테이너에 한정하며 DB/파일/설치 폴더를 자동 정리하지 않는다. 최초 설치가 실패해 폴더가 남으면 덮어쓰지 말고 NAS-local 상태를 확인한다.
