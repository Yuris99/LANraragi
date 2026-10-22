# 독립 Docker 로컬 테스트

이 구성은 NAS 배포가 아니다. 기존 `library-studio` Compose 파일·컨테이너·DB 볼륨·`.env`를 사용하지 않는다.

| 구분 | 기존 만화 Studio | 기존 Python 음성 개발 서버 | 새 Docker 음성 테스트 |
| --- | --- | --- | --- |
| 프로젝트 | library-studio | 해당 없음 | audio-studio-test |
| 로컬 포트 | 43120 | 43130 | 43132 |
| DB | studio-data / 기존 Redis | audio-studio/data/audio.sqlite3 | audio-studio-test_audio-test-data |
| 미디어 | 기존 만화 라이브러리 | audio-studio/media | audio-studio-test_audio-test-media, 읽기 전용 |

Docker 테스트는 새로운 빈 카탈로그로 시작한다. 개인 파일·기존 개발 DB는 자동으로 가져오지 않는다. 이미지 빌드 컨텍스트는 음성 소스·웹 자산·Python 테스트만 허용한다. 빌드 과정에서 Python 테스트를 실행하며 최종 이미지에 테스트·임시 DB를 포함하지 않는다.

## 시작

Docker Desktop의 Linux 엔진이 실행 중이어야 한다. 저장소 루트에서:

```powershell
docker compose -f audio-studio/compose.test.yaml config --quiet
docker compose -f audio-studio/compose.test.yaml up -d --build --wait
```

접속: `http://127.0.0.1:43132`. 바인딩은 호스트 loopback 전용이며 휴대폰/외부 네트워크에는 공개하지 않는다. 컨테이너 내부는 Docker 포트 전달을 위해 `0.0.0.0:43130`을 사용한다. 컨테이너 데이터 볼륨은 분리되어 있고 루트 파일 시스템은 읽기 전용이다. 자동 재시작은 끈다. 로그인 테스트가 필요하면 실행 환경에 `AUDIO_STUDIO_PASSWORD`를 설정한다. 값은 커밋하지 않는다.

## 확인과 중지

```powershell
docker compose -f audio-studio/compose.test.yaml ps
Invoke-RestMethod http://127.0.0.1:43132/api/health
docker compose -f audio-studio/compose.test.yaml stop
```

`stop`은 테스트 컨테이너만 멈추고 데이터를 보존한다. 이 문서의 명령은 기존 Studio 서비스를 시작/중지하지 않는다. 단, Docker Desktop 자체를 새로 켜면 기존 Docker 컨테이너들의 재시작 정책에 따라 함께 시작될 수 있으므로 이는 별도로 판단해야 한다.

현재 테스트용 미디어 볼륨은 비어 있다. 실제 트랙·자막을 테스트하려면 합성 fixture를 이 전용 볼륨에 준비하는 절차가 추가로 필요하다. 기존 개인 미디어 폴더를 연결하거나 NAS 경로를 마운트하지 않는다. NAS용 경로·인증·HTTPS·휴대폰 접속 설정은 포함하지 않는다.
