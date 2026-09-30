# 일본어 원문·한국어 번역 참조

각 CSV는 Valis II 작업 자료에 실제로 적힌 일본어 문안과 한국어 문안을 출처·판본별로 찾아보기 위한 표다. 문장을 새로 만들거나 바이트에서 역변환해 채우지 않는다. 원문과 번역의 대응 관계가 자료에 명시되지 않았거나 한쪽 문안이 비어 있으면 빈칸과 상태로 남긴다.

## 표

| 파일 | 범위 |
|---|---|
| `disk-A__text-reference.csv` | Disk A UI·프롤로그·엔딩·크레딧 |
| `disk-B__system-text.csv` | Disk B 시스템 문구 |
| `disk-C__system-text.csv` | Disk C 시스템 문구 |
| `disk-D__acts-1-3.csv` | Disk D Act 1–3 |
| `disk-D__shared-errors.csv` | Disk D 공통 디스크 오류 문구 |
| `disk-E__act4.csv` | Disk E Act 4 |
| `disk-F__act5.csv` | Disk F Act 5 |
| `disk-F__error-text.csv` | Disk F 오류 문구 |
| `disk-G__music-prize-warning.csv` | Disk G Music·Prize·경고 문구 |

## 열

- `disk`, `area`, `sequence`: 디스크·영역·원자료의 순서 식별자
- `source_version`: 사용한 문서나 작업표의 날짜·판본
- `japanese_original`, `korean_translation`: 원자료에 적힌 문안. 전각 공백 표기와 제어 토큰은 구분을 위해 유지한다.
- `source_document`, `source_location`: 원본 파일명 및 페이지·표·행·그룹 등 위치
- `text_status`: 문안 쌍의 자료상 상태
- `patch_status`: 해당 문안의 패치표 적용 상태
- `execution_status`: 사용자 실행 확인 기록의 상태
- `notes`: 판본 차이, 분할·합침, 대응 관계 등 읽을 때 필요한 설명

번역 워크북, 원본 실행 분석, 직접 패치표는 작성 시점과 문안이 다를 수 있으므로 판본을 합치지 않는다. 이 CSV는 문안 참조용이며 빌더의 패치 입력이 아니다. 빌드 적용 데이터는 [`../manual-build/`](../manual-build/)에 있다.
