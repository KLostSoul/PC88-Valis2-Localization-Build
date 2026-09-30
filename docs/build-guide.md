# 새 한글 빌드 안내

## 입력

`import/`와 `output/` 폴더는 저장소 루트에 이미 포함되어 있다. `import/` 폴더에 다음 원본 파일을 넣는다. 필요한 파일이 없으면 빌드는 실행되지 않는다.

- 일본어 원본 Disk A–G D88 7개
- 원본 KANJI1 ROM 1개

빌더는 `import/`의 원본을 크기·SHA-256으로 Disk A–G 및 KANJI1 ROM에 대응시킨다. KANJI1에는 최종 글리프표의 558개 한글 글리프만 적용하고, 그 밖의 원본 ROM 바이트는 유지한다.

원본 크기·SHA-256은 [`source-baseline.json`](../source/manual-build/source-baseline.json)에 기록되어 있다. 해당 지문을 가진 원본이 빠졌거나 중복되면 빌드를 중단한다.

영역별 패치 JSON은 `disk-{A-G}__{영역}.json` 형식으로 이름을 붙인다. 예를 들어 `disk-A__prologue.json`, `disk-D__act1.json`, `disk-F__error-text.json`처럼 디스크 문자를 대문자로 쓰고 영역 이름은 소문자로 쓴다. `build-scope.json`과 `source-baseline.json`은 모든 디스크에 공통인 설정 파일이다.

## 실행

저장소 루트에서 실행한다.

```powershell
python -m tools.cli
```

기본 입력 경로는 `import/`이고 기본 출력 경로는 `output/`이다. `--original-dir`은 입력 폴더를, `--kanji-original-rom`은 별도로 둔 원본 ROM을 지정한다.

## 생성 결과

- `output/d88/`: 한글 적용 D88 Disk A–G
- `output/kanji/KANJI1.ROM`: 한글 글리프 ROM
- `output/ips/`: Disk A–G IPS와 `KANJI1.ips`
- `output/build-log.json`: 입력·출력 지문과 적용 기록

빌더는 확정 패치표의 raw 주소와 기존 바이트를 확인하고, D88 섹터 경계·중복 쓰기·글리프 표 558행을 검사한다. PNG에서 만든 그래픽 자원과 적용한 입력 파일 지문은 `build-log.json`에 기록한다. 각 IPS를 확인된 원본에 재적용해 생성 결과와 일치하는지 확인한다.
