# 빌드 도구

저장소 루트에서 python -m tools.cli를 실행하면 수록된 패치 자료를 적용하고 D88·KANJI1.ROM·IPS를 생성한다.

| 파일 | 역할 |
|---|---|
| cli.py | 명령줄 진입점 |
| manual_build.py | 원본·패치표·글리프표를 확인하고 전체 빌드 수행 |
| d88.py | D88 이미지와 섹터를 읽고 기록 |
| graphics_assets.py | Disk A 타이틀과 Disk B 전투 PNG를 게임 자원 형식으로 인코딩 |
| ips.py | IPS 생성·적용 및 결과 대조 |