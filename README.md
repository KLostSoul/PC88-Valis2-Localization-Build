# PC-88 몽환전사 바리스 II 한글 패치 빌드

![몽환전사 바리스 II 타이틀 이미지](Images/valis2.PNG)

원본 PC-88 디스크와 ROM에 패치표를 적용해 한글 빌드 결과를 만드는 Python 프로젝트다.

## 입력 자료

`import/` 폴더에 다음 원본·ROM 파일을 넣는다. 필요한 파일이 빠지면 빌드는 실행되지 않는다.

- 일본어 원본 Disk A–G D88 7개
- 일본어 원본 KANJI1 ROM 1개

빌더는 `import/`의 원본을 크기·SHA-256으로 Disk A–G 및 KANJI1 ROM에 대응시킨다. KANJI1에는 `source/kanji/glyph-assignment-reference.csv`의 최종 558개 한글 글리프만 적용한다. ROM의 나머지 바이트는 원본값을 유지한다.

원본 크기·SHA-256은 [`source-baseline.json`](source/manual-build/source-baseline.json)에 기록되어 있다. 해당 지문을 가진 원본이 빠졌거나 중복되면 빌드를 중단한다.

## 빌드 실행

저장소 루트에서 실행한다.

```powershell
python -m pip install -r requirements.txt
python -m tools.cli
```

빌더는 기본으로 `import/`에서 입력을 읽고 `output/`에 결과를 만든다. `--original-dir`은 입력 폴더를, `--kanji-original-rom`은 별도로 둔 원본 ROM을 지정한다.

## 생성 결과

- `output/d88/`: 한글 적용 D88 Disk A–G
- `output/kanji/KANJI1.ROM`: 빌드에 사용한 한글 글리프 ROM
- `output/ips/`: Disk A–G용 IPS 7개와 `KANJI1.ips`
- `output/build-log.json`: 입력·출력 지문, 패치표 지문과 적용 결과

각 IPS는 확인된 일본어 원본에 재적용해 생성 D88 또는 ROM과 바이트 단위로 일치하는지 확인한다.

## 저장소 구성

- `docs/`: [문서 안내](docs/README.md), [통합 분석](docs/integrated-source-analysis.md), 빌드·근거 안내
- `import/`: 원본 D88 7개와 원본 KANJI1 ROM 입력 위치
- `output/`: 빌드 결과 위치
- `source/`: [자료 폴더 안내](source/README.md)와 빌드·참조 자료
- [일본어 원문·한국어 번역 참조표](source/text-reference/README.md): 영역별 문안과 출처
- `source/patches/`: 영역별 분석·교차 확인 자료
- `source/kanji/`: 글리프와 토큰 조회표
- `tools/`: [도구 안내](tools/README.md), D88 처리, 패치 적용, IPS 생성·재적용 확인


## 라이선스와 원작 권리

MIT 라이선스는 이 저장소에서 직접 작성한 빌드 코드에 적용한다. 번역문·분석 자료·패치표와 원작 게임의 프로그램·텍스트·이미지·음악·상표에 대한 권리는 각 권리자에게 있다.
