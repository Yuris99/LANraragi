# 기존 NAS 위치에서 CBZ로 전환

2026-10-18 사용자는 전용 Docker 볼륨에 사본을 계속 만드는 대신, 기존 NAS 위치에서 작품 폴더를 CBZ로 압축하고 검증 성공 후 그 원본 작품 폴더를 삭제하도록 명시했다. 이 승인으로 이전의 원본 영구 보존 요구는 **선택한 작품 폴더의 검증 후 삭제에 한해** 변경됐다. Stash/NMLO 컨테이너, 계정/ACL, 개인 자료 업로드, 기존 Studio 사본/DB 삭제는 여전히 범위 밖이다.

`archive_in_place.py`는 웹 서비스에서 불러오지 않는 독립 NAS-local 도구다. 자동 배포 채널/기존 읽기 전용 폴더 작업자는 원본 쓰기 권한이 없으며, 이 도구를 설치하거나 실행하지 않는다. 새 코드를 GitHub에 올려도 NAS 원본은 변하지 않는다.

기존 `manga/작품/`를 `manga/작품.cbz`로 변환한다. 같은 이름의 CBZ는 덮어쓰거나 원본 삭제의 근거로 재사용하지 않는다. JPEG/PNG/WebP 등 이미 압축된 이미지는 ZIP_STORED로 묶어 불필요한 CPU 사용을 줄인다. 이미지 재인코딩은 하지 않는다. 따라서 용량 감소보다는 라이브러리 형식 전환이며, 작업 중에는 한 작품만큼 추가 여유 공간이 필요하다.

- 기본값은 plan이다. `--apply --delete-source`를 함께 지정했을 때만 검증 후 삭제한다.
- 압축본은 원본 작품 폴더 옆의 숨겨진 `.part`에 생성한다. 하위 폴더, 빈 폴더, 숨김 파일과 일반 비이미지 파일도 모두 포함한다.
- 전체 파일 목록·크기를 비교하고, 압축본의 **모든 파일을 다시 읽어 원본과 SHA-256을 대조**한다. 파일/디렉터리 변경도 확인한다.
- 파일과 부모 디렉터리에 fsync한 뒤, 기존 파일을 바꾸지 않는 atomic hard-link로 `.cbz`를 게시한다. 게시된 inode와 전체 내용도 재검증한다.
- 그 후에만 확인했던 개별 원본 파일과 비워진 폴더를 제거한다. `rm -rf`/`shutil.rmtree`는 사용하지 않는다. 삭제 직전 파일 상태와 디렉터리 신원을 다시 확인한다.
- 원본을 수정하는 다른 프로그램은 먼저 멈춰야 한다. flock은 이 도구/기존 가져오기 작업 사이의 협력 잠금이며, File Station이나 다른 앱의 쓰기를 막지 못한다. 실행 중 원본이나 새 CBZ를 다른 프로그램에서 편집하지 않는다.
- 기존 가져오기와 같은 `folder-pilot.lock`을 사용하며, DB에 queued/running 요청이 있으면 전환을 거부한다. DB는 읽기 전용으로 조회한다. 기존 예약 작업이나 Compose/서비스 설정은 바꾸지 않는다.
- 심볼릭 링크, 하드 링크, 특수 파일이 있는 작품은 검토 대상으로 남긴다. Synology 내부 `@eaDir`/`@tmp`/`#recycle`도 기본적으로 보류한다. 명시적 `--preserve-nas-metadata` 모드는 이 트리의 모든 파일/빈 폴더를 CBZ 내부 `__studio_nas_metadata__.zip`에 원래 상대 이름으로 보존하고, 그 내부 모든 파일까지 원본 SHA-256과 대조한다. 그래서 캐시 이미지가 리더 페이지에 섞이지 않는다. 해당 예약 파일명이 원본에 이미 있으면 중단한다. 메타데이터를 버리고 원본 폴더 전체를 지우는 동작은 없다. 복구는 CBZ를 푼 후 이 내부 ZIP도 같은 루트에 풀면 된다. ACL·확장 속성 등 파일시스템 메타데이터 백업은 아니다. 내부 ZIP의 임시 공간까지 추가로 확인한다.
- 한 작품 2GiB, 20,000항목/16단계, 전체 탐색 10,000디렉터리로 제한한다. 컬렉션 루트 자체는 압축/삭제하지 않는다. 이미지가 직접 들어 있는 첫 하위 폴더를 작품 경계로 삼고 그 하위 트리도 함께 보존한다. 이미지가 컬렉션 루트에 직접 놓였거나 폴더 구조가 다른 경우 별도 확인이 필요하다.
- 적용 중 오류가 하나라도 발생하면 다음 작품으로 진행하지 않는다. 이미 완전히 전환된 작품은 CBZ만 남아 다음 탐색에서 제외된다. 게시 뒤 중단되면 완전한 CBZ와 일부 원본이 함께 남을 수 있다. 기존 CBZ가 있는 원본은 자동 재삭제하지 말고 NAS-local에서 확인한다. `.part`도 자동으로 삭제하지 않는다.

예시(개인 경로는 NAS에서만 입력):

```sh
python archive_in_place.py '/승인한/작품폴더'                  # plan
python archive_in_place.py '/승인한/작품폴더' --apply --delete-source
python archive_in_place.py --root '/승인한/원본루트' --collection manga
python archive_in_place.py --root '/승인한/원본루트' --collection manga --database /data/studio.db --apply --delete-source
```

## 연결 전환은 별도 검증

### NAS 중단 보고와 제한된 재시도

사용자가 실제 NAS에서 연결 overlay 존재, LANraragi UID1026, `local_updates=disabled`를 보고했다. 이전 generation3 `deployment=healthy`는 앱 코드 배포 기록이며 연결 전환 성공을 증명하지 않는다. 원래 실행기는 실패 단계를 기록하지 않았으므로 정확한 과거 실패 원인은 미확인이다. 임시 Compose JSON 파일을 권한 없는 컨테이너에서 bind로 읽던 검사를 NAS-local 표준 입력 파이프로 바꿨다. 자격정보가 포함된 구성은 여전히 클라우드/로그에 출력하지 않는다. 새 실행기는 `connection_phase`와 실패 단계/종료 코드를 표시하고 NAS-local 시도 폴더에 고정 단계 이름만 기록한다.

apply 재시도는 **업데이트가 중지되고, 기존 컨트롤러/설정 해시가 모두 일치하고, root 소유의 정상 JSON overlay가 같은 승인 경로의 정확한 UID0/RO 제안이며, 실제 LANraragi가 기존 UID로 healthy이고 NASOriginals mount가 없고, overlay가 이미 고정 목록에 등록되지 않은 경우에만** 허용한다. 두 배포 잠금을 가진 상태에서 그 미적용 파일을 새 시도 폴더에 보관한 후 고정 제안을 다시 생성한다. 다른 경로/설정, symlink, 등록된 연결, 라이브 mount, 실행 중인 root reader, 활성 업데이트가 있는 경우에는 교체하지 않는다. 새 파일은 명시적으로 mode0600을 적용한다. 성공한 경우에만 추가 overlay 해시를 고정하고 앱 자동 업데이트를 복구한다. 실패하면 계속 중지하고 백업을 보존한다. 일반 설정 변경/권한 확대를 자동 채택하는 복구 경로가 아니다.

검증: 거부 조건5개 단위 테스트 및 `STUDIO_INPLACE_PENDING=1 python -B studio/tests/inplace_connection_smoke.py` 실제 합성 스택 재현 통과. 이 재현은 NAS와 같은 미적용 overlay/중지 상태에서 시작해 미적용 파일 보관, root RO 연결,3페이지/캐시 제외, 다운로드 해시, Studio-only 재생성 뒤 LRR 보존 및 자동 업데이트 상태 복구를 확인했다. NAS 장비에서 새 재시도가 성공했다는 뜻은 아니다. 원본 쓰기와 삭제는 여전히 전체 preflight와 건강한 연결 전환 뒤의 명시적 converter apply에서만 실행한다.

**압축 도구 준비와 LANraragi 경로 연결은 별개다.** 사용자 보고 시점의 NAS LANraragi에는 원본 루트가 연결돼 있지 않았다. GitHub 코드 게시만으로 새 CBZ가 Studio 목록에 자동으로 나타난다고 주장하면 안 된다. 기존 앱 업로드 볼륨의 사본과 DB·태그·읽던 위치도 그대로 둔다. 기존 앱 사본의 경로/ID와 새 CBZ의 연결을 확인하기 전 자동 정리하지 않는다.

최종 배포안은 LANraragi에 승인한 원본 루트를 읽기 전용으로 추가하고, 그 서비스의 실제 실행 UID가 해당 폴더와 CBZ를 읽을 수 있는지 확인해야 한다. 앞선 NAS 진단에서 비루트 읽기는 실패했으므로, Docker mount만으로 읽기 권한 문제까지 해결됐다고 가정하지 않는다. 계정/ACL이나 LANraragi 실행 계정을 임의로 바꾸지 않는다. Compose 변경은 기존 고정 배포 채널의 해시 검증을 멈추므로 새 기준을 조용히 채택해서도 안 된다. 기존 Stash가 작품 폴더를 참조한다면 CBZ 전환 뒤 그 경로는 사라질 수 있으며, Stash 설정/DB는 이 도구가 수정하지 않는다.

### NAS-local 연결 전환안

최종 `migrate-inplace-library.sh plan|apply '<승인한 NAS 루트>'`는 고정 커밋6daa6671a408b126742f0daef8147eb6ac9a2d25의 압축 도구/연결 실행기를 해시 검증해 사용한다. 두 컬렉션을 `--preserve-nas-metadata`로 **먼저 전부 plan**하고, 후보 중 오류/기존 CBZ 충돌/불안정 파일/링크/한도 초과가 하나라도 있으면 서비스 전환과 원본 쓰기 전에 멈춘다. plan은 여기서 끝난다. apply는 아래 연결 전환이 건강하게 끝난 뒤에만 network-none/RO rootfs/256MiB/최소 capability의 임시 컨테이너에서 원본 RW + 자기 Studio DB 볼륨을 연결해 순서대로 압축·검증·삭제한다. 전체를 한 번 요청하며 작품마다 개수 진행률을 출력한다. 원본 RW는 이 명시적 일회 작업에만 있고 LANraragi의 입력은 계속 RO다. 기존 큐 작업이 남아 있으면 전환 도구의 공유 잠금/DB 검사가 원본 압축·삭제를 막는다. 소스 경로는 NAS-local 인자일 뿐 GitHub에 저장하지 않는다. 기존 연결 overlay가 있으면 설치를 반복 덮어쓰지 않는다.

`connect-inplace-library.sh plan|apply '<승인한 NAS 루트>'`를 준비했다. plan은 변경이 없고, apply는 다음의 구체적인 서비스 변경을 수행한다. **이는 임시 root 리더 실행과 달리 LANraragi 웹/API·작업자 프로세스를 컨테이너 내 UID/GID0:0으로 바꾸는 권한 전환**이다. 원본 경로는 이 서비스에서도 RO이며 Docker socket/host privilege/공개 포트는 추가하지 않는다. 사용자가 NAS-local에서 이 별도 전환을 적용하기 전에는 기존 앱 자동 배포로 실행되지 않는다.

1. 기존 NAS 프로젝트/두 이미지/건강 상태/자기 볼륨 label, 고정 배포 컨트롤러 및 기존 설정 해시를 확인한다. 배포/앱 업데이트 잠금을 취득한다. 기존 설정이 달라졌으면 멈춘다.
2. 새 `compose.archive.yaml` 하나를 만든다. 변경 허용 범위는 LANraragi의 LRR_UID/GID0:0과 `content/NASOriginals`의 승인 루트 RO mount 하나다. 전후 Compose를 비교해 그 외 설정 변경을 거부한다. 비밀이 포함된 임시 Compose JSON은 NAS-local0700 디렉터리에만 두고 검사 후 지운다. 원본 `.env`/기본 Compose/UID1026:100 Studio는 바꾸지 않는다.
3. Studio SQLite를 일관 백업한다. LANraragi만 `up -d --no-deps lanraragi`로 재생성하고 healthy·koyomi의 실제 UID0·원본 RO mount·Studio 시작 시각 보존을 확인한다. 앱 DB/사본을 삭제하거나 되돌리지 않는다. 이 백업은 LANraragi Redis DB 전체 백업이라는 뜻이 아니다.
4. 원래 설정 해시가 여전히 같은지 확인한 뒤에만, 명시적으로 검토한 새 overlay 해시 하나를 기존 NAS-local 고정 목록에 추가한다. 이를 통해 기존 Studio-only 배포는 계속되며 추가 연결 파일도 해시로 보호한다. 컨트롤러/업데이터 코드는 교체하지 않는다. 이후 전체 프로젝트를 수동 재기동할 때는 `-f compose.archive.yaml`도 포함한다. 자동 앱 업데이트의 `--no-deps studio`는 LANraragi를 재시작하지 않는다.
5. 연결 실패 시 새 overlay/백업을 보존하고 앱 자동 업데이트를 일시 중지한다. 자동으로 삭제/권한 복구/원본 전환을 시도하지 않는다. 같은 설치를 반복 덮어쓰지 말고 NAS-local 상태를 확인한다.

이 전환으로 새 LANraragi 출력은 자기 DB/썸네일/플러그인 볼륨에서 root 소유가 될 수 있다. 비루트로 되돌리는 작업은 원본 경로 접근과 **자기 볼륨만**의 소유권을 별도로 검토해야 한다. NAS 원본이나 다른 서비스 볼륨에 재귀 chown을 하지 않는다.

`plan-inplace-nas.sh '<NAS-local 원본 루트>'`는 고정 커밋/해시의 도구로 두 컬렉션을 읽기 전용 검사하고, 현재 Studio UID/GID로 루트/manga/images 경로가 열리는지만 출력한다. 파일명·이미지·DB·환경변수/키를 출력하지 않는다. 소스도 DB도 쓰기 마운트하지 않으며 서비스/배포 설정은 바꾸지 않는다. 이는 경로 연결안을 준비하기 위한 진단이며, 압축·삭제 명령이 아니다. 비루트 probe가 성공해도 모든 하위 폴더의 접근을 검증한 것은 아니다.

## 검증 기록

새로운22개 압축/원본삭제 테스트와3개 실행기 차단 테스트를 포함한 총187개 테스트 통과. 실행기 테스트는 해시 불일치·실패한 사전 검사 뒤에는 연결/삭제가 실행되지 않고 plan 입력이 RO임을 확인한다. 생성한 PNG/JPEG/WebP 및 비이미지 파일만 사용했다. 전체 바이트 대조·중첩/빈 폴더·충돌·링크/특수 파일·NAS 내부 폴더 보류 및 내부 ZIP 보존/해시 실패·공간 부족·중간 변경·검증 실패·게시/삭제 중 중단·배치 중단·기존 가져오기 잠금을 검사했다. 실제 Docker(network none, RO rootfs, 최소 capability, 256MiB)에서도 생성한 한 작품을 같은 위치에 CBZ로 게시하고 검증 후 원본을 제거했다.

`python -B studio/tests/inplace_connection_smoke.py`는 별도 합성 스택에서 NAS처럼 비루트 접근이 막힌 이미지/캐시 폴더를 만들고, 같은 위치에 CBZ로 전환한 뒤 원본 폴더를 제거한다. 실제 LANraragi0.9.81을 UID0으로 전환해 RO 경로를 읽고, Studio 동기화·실제 페이지3장(캐시 제외)·전체 다운로드 SHA-256·Studio 시작 시각 보존·추가 overlay 해시 고정·임시 자격정보 JSON 제거를 검증했다. 이 Docker 이미지는 기존 NAS용 소스의 개발 이미지이며, NAS 장비에서의 실행 증거는 아니다.

사용자가 실행한 이전 NAS-local 읽기 전용 plan 보고는 후보324개, 오류32개 모두 `nas_system_directory_requires_review`, appUID1026:100의 root/manga/images 읽기 불가였다. 표시된5,913,908,166바이트는 보류되지 않은 후보들의 합계이며 전체324개의 총 용량으로 해석하지 않는다. 실제 NAS 파일 전환·원본 삭제·새 경로 연결은 아직 수행하지 않았다.

최종 복구 실행기는 연결 코드 SHA256 `ed7ad36b144f8b34af56a2f32b3eaeae17268905d1ba043b96422b42783f3274`와 기존 압축 도구 해시를 고정한다. 전체193개 테스트 통과(기존187 + 미적용 설정 거부5 + 사전 검사 성공 후 연결 단계 진입/실패코드 전달1). 실패 시 `migration_exit`와 `phase`도 출력한다. 수정한 실행기로 NAS에서 재시도한 결과는 아직 미확인이다. 원래16e2eeaf 실행기를 반복하거나 검사 없이 자동 배포만 켜는 방식은 사용하지 않는다.
