# 자료 대응표

각 빌드 영역은 원본 문서의 시간·행·RAM 주소·raw D88 주소·이전 바이트가 실제로 연결되는 경우에만 빌드 패치표로 만든다. 아래는 작업 폴더 자료가 다루는 영역이다. 현재 반영 가능 여부는 [`build-scope.json`](../source/manual-build/build-scope.json)의 필수 ID와 해당 JSON의 `complete` 값으로 확인한다.

일본어 원문과 한국어 번역 문안은 [`source/text-reference/`](../source/text-reference/README.md)의 영역별 참조표에서 출처와 함께 확인할 수 있다. 해당 표는 문안 조회용이며 빌드 패치 입력은 아니다.

| 디스크 | 영역 | 직접 자료의 종류 |
|---|---|---|
| A | UI·메뉴·타이틀 CG·프롤로그 | UI 번역표, 타이틀/CG 분석, 런타임 덤프, 오프닝 패치표, `source/graphics/disk-A__*` PNG 평면 |
| A | 엔딩·크레딧 | 엔딩 원문/번역 워크시트, 크레딧 제어·문자열 표, 실행 기록 |
| B | 시스템 문구·전투 CG | Disk B 최종 raw 패치 기록, CG 자원 분석, `source/graphics/disk-B__battle-cg/` PNG 평면 |
| C | 시스템 문구·고정 store | Disk C 최종 raw 패치 기록과 동적 store 기록 |
| D | Act 1–3 | Act별 런타임 덤프, 순번/번역/토큰/주소 패치표 |
| E | Act 4 | 8월 4일 교정 작업표, 원시 덤프와 raw 위치 대조 |
| F | Act 5·디스크 오류 문구 | Act 5 실행 로그·payload 표, 오류 안내 번역/토큰 작업표 |
| G | Prize·Music·경고 | Prize 번역표, Music 텍스트/포인터 분석, 경고 주소·제어 기록 |
| 공통 | KANJI 글리프 | 최종 `hangul.csv`와 동일한 558행 글리프 배정표, 원본 KANJI1 ROM |

기존 `source/patches/` 표는 직접 자료의 특정 날짜 상태·토큰 대조·후속 판본을 보존한다. 텍스트와 기계 코드 패치는 `source/manual-build/`의 raw 오프셋·old/new byte·근거를 사용하고, Disk A/B 그래픽은 `source/graphics/`의 PNG 평면을 인코딩해 만든다. 그래픽의 RAM 시작 주소, 평면 순서, 저장 형식과 raw 섹터 범위는 해당 manual-build JSON에 명시한다.
