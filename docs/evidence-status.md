# 근거와 빌드 확인

문안, 글리프 배정, raw 패치 위치와 실행 기록은 각각 해당 자료에서 확인하고, 최종 적용은 원본 바이트와 빌드 산출물의 대조로 확인한다.

## 입력과 글리프 ROM

- 일본어 원본 Disk A–G와 원본 `KANJI1.ROM`의 기준 크기·SHA-256은 [`source-baseline.json`](../source/manual-build/source-baseline.json)에 있다.
- 원본 D88 7개와 KANJI1 ROM을 저장소 루트 `import/`에 두면 기준 크기·SHA-256으로 식별한다.
- `output/kanji/KANJI1.ROM`은 원본 ROM에 최종 글리프표 558행을 적용해 만든다. 원본 SHA-256은 `7608040cffb1951e5cc567abb63f75b5746777a1ba96196c1b75606b793bb4bb`, 생성 SHA-256은 `e5646601d83fc2685340a183fa50d3c4fca8daf449acefc35544ef790e775aab`다. 달라진 16,820바이트는 558개 지정 글리프 슬롯에 있다.

## 현재 빌드

빌드는 완료됐다. 에뮬레이터에서 최종 빌드의 화면 표시, 게임 진행, PCM 동작까지 확인했다. 로컬 `output/build-log.json`은 Disk A–G와 `KANJI1.ROM`의 산출 지문을 기록하고, 8개 IPS 각각의 재적용 결과가 해당 산출 파일과 일치함을 기록한다.

필수·후보 영역은 [`build-scope.json`](../source/manual-build/build-scope.json)에, 각 패치의 raw 위치·이전 바이트·교체 바이트는 `source/manual-build/`의 패치 정의에 있다.
