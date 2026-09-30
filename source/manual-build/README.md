# 빌드 적용 자료

이 폴더의 JSON은 빌더가 확인된 raw 변경과 그래픽 자원 배치를 적용하는 입력이다.

| 파일 | 적용 영역 |
|---|---|
| build-scope.json | 빌드에 포함되어야 하는 17개 구성요소 |
| source-baseline.json | 일본어 Disk A–G와 원본 KANJI1.ROM의 크기·SHA-256, 생성 KANJI1.ROM 지문 |
| disk-A__title-cg.json | 타이틀 이미지·스크롤·행 보정 |
| disk-A__ui.json | 메뉴·안내 문구 |
| disk-A__prologue.json | 오프닝 |
| disk-A__ending.json | 엔딩 |
| disk-A__end-credits.json | 엔딩 크레딧 |
| disk-B__battle-cg.json | 전투 CG |
| disk-B__system-text.json | 시스템 문구 |
| disk-C__system-text.json | 시스템 문구 |
| disk-D__act1.json | Act 1 |
| disk-D__act2.json | Act 2 |
| disk-D__act3.json | Act 3 |
| disk-E__act4.json | Act 4 |
| disk-F__act5.json | Act 5 |
| disk-F__error-text.json | 오류 문구 |
| disk-G__music.json | 음악 모드 |
| disk-G__prize.json | Prize 공지 |
| disk-G__warning.json | 경고 문구 |

패치 JSON은 대상 원본 지문과 raw 위치·기존 바이트·교체 바이트를 기록한다. 그래픽 JSON은 PNG 평면과 자원 배치 정보도 제공한다.