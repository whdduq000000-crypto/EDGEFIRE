# W6–W15 진행률 점검표 (2026-11-24)

진행률은 상세 계획서의 개발 산출물 기준 자체 추정치. 동일 가중치 체크포인트별 1=요구 코드/문서 준비, 0.5=일부 또는 모의/대체 구현, 0=미구현. 실제 장비/성능/원격 검증 성공률이 아님. 주차별 반올림. 

| 주차 | 체크포인트 점수 | 코드 준비율 | 실제 확인 |
|---|---:|---:|---|
| W6 | 2.5/3 | 83% | ICD/아키텍처/Swagger·Postman; OpenAPI 3.1 사용, MQTT 실연결 미검증 |
| W7 | 3/4 | 75% | 공간 스키마·구역/nearby 코드; PostGIS 및 10ms 미검증 |
| W8 | 3/3 | 100% | 센서 API/TTL/WS 코드 준비, SQLite API·WS 테스트; Redis/Celery/LoRa 미검증 |
| W9 | 1.5/3 | 50% | 변화율/비율 계산 테스트; 오탐 판정 모델·pg_partman 미적용, BRIN 조회 실검증 전 |
| W10 | 2.5/4 | 63% | 방위각·Pelco-D 프레임·bbox 메타데이터; 실제 RS485/NPU 20ms 미검증 |
| W11 | 2/3 | 67% | 기존 AI 확산 연계/GeoJSON·MVT/impact join; PINN/GNN 및 자동 확정 트리거 없음 |
| W12 | 0.5/3 | 17% | Celery 모의 전파 큐·통계; 실제 기관 API 및 IP Relay/2,000건/s 미구현·미검증 |
| W13 | 1.5/3 | 50% | 부분 E2E, 멱등·spool, history/재연결; 실제 위성 및 무누락 보장 없음 |
| W14 | 1.5/3 | 50% | Locust·TEP 합성 입력·기본 pool 설정; 목표 TPS/지연 미측정 |
| W15 | 1/2 | 50% | 실행·보고 초안과 시험 기록; 최종 보고서 및 현장 라이브 검증 남음 |

SQLite 자동 테스트 11개 통과 (3회 반복). GitHub demo-integration에 기존 팀 FE 기반 /remote 별도 화면 포함; 원래 / 페이지 및 main 브랜치 보존. FE 전체 빌드, 실제 팀 PC Tailscale, PostgreSQL/PostGIS, Redis/Celery, YOLO 가중치 및 장비 검증은 팀 실행 후 확인해야 한다.
