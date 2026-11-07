# 유리 스튜디오 출처 기록 v1

파일 이름은 `studio-source-<작품 번호>.json`, 형식 식별자는 `yuri-studio-source`,
버전은 정수 `1`이다. 스튜디오 DB에 같은 구조를 보관하고 JSON으로 내보낼 수 있다.
원본 압축 파일과 `.ehviewer`·`ComicInfo.xml`은 변경하지 않는다.

```json
{
  "format": "yuri-studio-source",
  "version": 1,
  "work": {
    "local_id": "generated-local-id",
    "library_id": "generated-library-id",
    "title": "사용자가 정한 작품명",
    "artist": "",
    "pages": 49
  },
  "sources": [],
  "evidence": [{
    "provider": "exhentai",
    "external_id": "123",
    "url": "https://exhentai.org/g/123/abcdefghij/",
    "metadata": {"title": "원본 제목", "tags": ["language:korean"]},
    "origin": {"kind": "embedded-comicinfo", "file": "ComicInfo.xml", "sha256": "generated-file-digest", "url_basis": "original-url"},
    "verification": {"state": "local_metadata", "remote_access_verified": false}
  }],
  "inspection": {"state": "read", "at": 0}
}
```

`work`는 현재 보관본의 식별 정보다. `sources`는 실제 연결된 출처와 최신 수집
정보이고, `evidence`는 원본 내부 기록에서 읽은 단서다. 원본 제목·작가·언어·
태그·페이지 수를 보존하며, 사용자 작품명·파일·판본은 덮어쓰지 않는다.

`local_metadata`는 원본 기록을 읽었다는 뜻이다. 원격 접근·계정 인증 성공을
뜻하지 않는다. 형식 이상이나 상충 정보는 `needs_review`로 보존하고 자동
연결하지 않는다. `.ehviewer`에서 복원한 기본 E-Hentai URL과 같은 번호·토큰의
ComicInfo 익헨 URL은 같은 계열의 일치하는 근거로 취급하되 명시된 원래 호스트를
우선한다. 서로 다른 작품 번호·토큰은 합치지 않는다.

CBOR 및 기존 텍스트 `.ehviewer`에서 작품 번호·갤러리 토큰·페이지 수만 읽는다.
갤러리 토큰은 원본 작품 URL의 일부다. 로그인 쿠키·비밀번호·개별 페이지 접근
토큰 맵은 이 형식에 넣지 않는다. 압축 파일은 범위 요청으로 필요한 정보만 읽고
추출하지 않는다. 정보 파일은 128KiB, 전체 메타데이터 범위 전송은 2MiB로 제한한다.

**전체 작품 정보 갱신**은 원본 기록에서 확실한 주소를 먼저 복원한 뒤 기존
정보 수집 경로를 순서대로 실행한다. 연결 소유권 충돌·형식 이상은 검토 대상으로
남긴다. 원본의 404·410은 개별 자료의 기존 기록을 유지하고 다음 자료를 갱신한다.
접근·연결 오류가 발생하면 해당 원래 호스트의 추가 요청을 보류한다. 이 작업은
화면을 열어 둔 동안 실행하며 중지할 수 있다.

작품별 **원본 출처 · 정보 찾기**에서는 원본 기록, 페이지 이미지, 제목,
Hitomi 작가 색인의 후보를 비교하고 선택한다. 이미지 검색은 원본 페이지의
SHA-1 파일 지문을 이헨 또는 익헨의 정상 파일 검색에 전송한다. 이미지 자체를
자동 업로드하지 않는다. 지문이 사이트에 색인되지 않았거나 단색 이미지이면
유사 후보를 찾지 못할 수 있다. 제목·작가·언어·페이지 수·태그 비교는 판단
근거이며 이미지 유사도 점수를 만들어 표시하지 않는다. 검색 후보는 사용자가
선택해야 출처로 연결된다.

검색 주소는 원본 기록 또는 이미 연결된 출처의 호스트를 우선한다. 둘 다 없는
작품은 저장된 익헨 계정 세션을 사용할 수 있으면 익헨에서 처음 검색하고,
그 외에는 이헨에서 검색한다. 요청 실패 뒤 주소를 바꾸어 재시도하지 않는다.

이미지 후보 표지 프록시는 HTTPS `ehgt.org`의 JPG·PNG·WebP만 읽는다.
다른 호스트·리다이렉트·인증 전달은 허용하지 않는다. 로그인·접근 제한은
정상적으로 해결해야 하며, 실패한 출처를 다른 주소로 우회하지 않는다.

참고: [EHViewer SpiderInfo](https://github.com/seven332/EhViewer/blob/master/app/src/main/java/com/hippo/ehviewer/spider/SpiderInfo.java),
[E-Hentai 파일 검색](https://ehwiki.org/wiki/Gallery_Searching#File_Search).
