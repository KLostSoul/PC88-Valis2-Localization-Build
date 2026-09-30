# 근거와 현재 빌드 상태

서로 다른 날짜의 실행 기록과 패치표는 각각의 대상 판본에 귀속한다. 번역 문안, 글리프·토큰 배정, D88 raw 위치, 파일 비교, 게임 실행 확인은 서로 다른 근거로 기록한다.

## 빌드 입력 근거

- 일본어 원본 Disk A–G와 원본 `KANJI1.ROM`의 기준 크기·SHA-256은 [`source-baseline.json`](../source/manual-build/source-baseline.json)에 있다.
- 빌드 입력은 저장소 루트 `import/`의 원본 Disk A–G D88과 원본 KANJI1 ROM이다. 크기·SHA-256으로 식별한다.
- 한글 `output/kanji/KANJI1.ROM`은 원본 ROM에 최종 `hangul.csv`와 동일한 558행의 32바이트 글리프를 적용해 생성한다. 원본 SHA-256은 `7608040cffb1951e5cc567abb63f75b5746777a1ba96196c1b75606b793bb4bb`, 생성 ROM은 `e5646601d83fc2685340a183fa50d3c4fca8daf449acefc35544ef790e775aab`다. 변경 16,820바이트는 모두 558개 글리프 슬롯 안에 있고 표 밖 변경은 0바이트다.
- 빌더는 확인된 원본 KANJI1 ROM에서 생성 한글 ROM으로 `KANJI1.ips`를 만들고, 재적용 결과를 출력 ROM과 대조한다.
- 필수 영역과 후보 영역은 [`build-scope.json`](../source/manual-build/build-scope.json)에 있다. `manual-build/`의 표는 raw 위치·이전/교체 바이트·근거가 확인된 영역만 완료로 표시한다.

## 산출 확인

빌드가 완료되면 `output/build-log.json`에 결과가 기록된다.
