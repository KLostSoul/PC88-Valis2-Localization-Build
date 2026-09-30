# 행별 대조표

이 폴더에는 Disk A–G의 행별 분석표 23개가 있다. 원문 실행행, 제어 바이트, 한글 문자별 바이트, RAM 주소와 D88 raw 위치를 대조할 때 사용한다.

이 CSV들은 날짜별 분석을 뒷받침하는 상세 자료다. 빌드에서 직접 적용하는 변경 목록은 `source/manual-build/`에 있으며, 이 폴더의 행을 빌드에 자동 적용하지 않는다. 문서에 기재된 순번·행 수는 원본 실행 기록과 번역·패치 판본에서 세는 단위가 다를 수 있으므로 [통합 분석](../../../docs/integrated-source-analysis.md)의 판본별 설명과 함께 읽는다.

| 파일 | 내용 |
|---|---|
| `disk-A__prologue__historical-patch__2026-06-19.csv` | 6월 19일 프롤로그 패치의 원본·교체 바이트 기록. 8월 TEST9에 의해 대체된 과거 판본이며 현재 빌드 입력으로 사용하지 않음 |
| `disk-A__prologue__test9-ram-payloads.csv` | TEST9의 RAM 루틴·payload, 길이와 확인된 raw 대응 |
| `disk-A__prologue__test9-raw-changes.csv` | TEST9에서 확인된 D88 raw 주소와 이전·교체 바이트 |
| `disk-A__title__d473-raw-change.csv` | Disk A 타이틀 중앙 행 보정의 RAM/raw 위치와 이전·교체 바이트 |
| `disk-A__ui__row-comparison__2026-07-27.csv` | Disk A 메뉴·안내 문구의 원문, 번역, RAM/raw 위치와 글리프 바이트 |
| `disk-B__system-text__character-byte-comparison.csv` | Disk B 문구의 문자, 코드값, 바이트, 논리 위치와 raw 오프셋 대조 |
| `disk-B__system-text__layout-and-source-tables.csv` | Disk B 최종 기록 문서의 표·행 내용과 원본 지문 |
| `disk-C__system-text__character-byte-comparison.csv` | Disk C 문구의 문자, 코드값, 바이트, 논리 위치와 raw 오프셋 대조 |
| `disk-C__system-text__layout-and-source-tables.csv` | Disk C 최종 기록 문서의 표·행 내용과 원본 지문 |
| `disk-D__act1__runtime-source-rows.csv` | Act 1 원본 실행 순서, RAM/raw 주소, 제어행과 분류 |
| `disk-D__act1__character-byte-comparison.csv` | Act 1 행별 원문·한글 바이트와 raw 위치 대조 |
| `disk-D__act2__runtime-source-rows.csv` | Act 2 원본 실행 주소·바이트·제어행 요약 |
| `disk-D__act2__character-byte-comparison.csv` | Act 2 출력 슬롯별 원문·대상 바이트·raw 위치 대조 |
| `disk-D__act3__runtime-source-rows.csv` | Act 3 원본 실행 주소·바이트·제어행 요약 |
| `disk-D__act3__character-byte-comparison.csv` | Act 3 행별 원문·한글 바이트와 raw 위치 대조 |
| `disk-E__act4__row-comparison__2026-08-04.csv` | Act 4 교정판의 작업표 순번, 원본 행, 대상 바이트와 raw 위치 대조 |
| `disk-F__act5__runtime-source-rows.csv` | Act 5 원본 실행 주소·바이트와 페이로드 흐름 요약 |
| `disk-F__act5__character-byte-comparison.csv` | Act 5 출력 바이트·대상 문자와 두 페이로드의 raw 위치 대조 |
| `disk-F__error-text__source-rows.csv` | Disk F 오류 문구의 원문 바이트, 제어 코드와 주소 구간 |
| `disk-F__error-text__character-byte-map.csv` | 오류 문구의 문자별 코드값·바이트·raw 주소 대조 |
| `disk-G__music__text-and-address-table.csv` | 음악 모드 제목·작곡자 문안, RAM 구조, 포인터와 확인 상태 |
| `disk-G__music-warning__character-byte-comparison.csv` | 음악 제목·경고문 글자별 KANJI1 배정과 ROM 오프셋 대조 |
| `disk-G__warning-text__source-and-translation.csv` | Disk G 경고문 원문·번역, RAM/raw 범위와 동적 슬롯 |
