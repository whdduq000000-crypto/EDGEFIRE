# W6–W15 진행 현황 V2.2

2026-11-24 상세 개발 계획 기준. 코드/문서 준비와 실제 실험 완료를 분리한다. 아래 수치는 이번 발표용 소프트웨어 체크포인트 5개(각 주차 동일) 중 준비된 개수다. 모의 기능은 모의 범위만 완료. 원래 WBS의 모든 요구를 충족한 비율과 동일하지 않다.

| 주차 | 준비된 체크포인트 / 전체 | 발표용 코드 준비율 | 원래 계획 잔여 |
|---|---:|---:|---|
| W6 | SRS/ICD, Pydantic, REST/WS, MQTT adapter, Swagger/Postman 5/5 | 100% | OpenAPI 3.0 대신 실제 3.1, MQTT TLS broker 검증 |
| W7 | DB 스키마, GiST, KNN, GeoJSON, 등록 API 5/5 | 100% | PostGIS 실기동, 실제 공간 자료, 10ms 검증 |
| W8 | 센서 API, Stream, Celery, TTL Hash, WS 5/5 | 100% | Redis/Celery/LoRa/LTE 실기동 |
| W9 | 변화율, 조성비, native 일별 파티션, BRIN, 이력 5/5 | 100% | 검증된 오탐 분류/pg_partman 미적용 |
| W10 | 방위각, 7B frame, command history, bbox, IR metadata 5/5 | 100% | 실제 RS485/PTZ 피드백/NPU 20ms |
| W11 | event 좌표 요청, 기존 AI proxy, GeoJSON, MVT, impact 5/5 | 100% | PINN/GNN 및 실시간 자동 트리거, 실제 기상/시설물 |
| W12 | mock 채널, Celery queue, 이력/통계, relay 후보 4/5 | 80% | 실제 기관 OAuth2/mTLS, IP Relay, CBS/알림톡 및 2000/s |
| W13 | 멱등키, spool, sequence gaps, cursor, synthetic E2E 5/5 | 100% | 위성 failover, 실장비 0누락 검증 |
| W14 | Locust, TEP fixture, baseline tuning, 검수 절차 4/5 | 80% | 목표 1000 TPS/50ms, pgBouncer 및 실제 TEP |
| W15 | API 문서, ERD/아키텍처, 보고 초안, 실행 가이드 4/5 | 80% | 라이브 팀 통합/실측 KPI 제출 |

자동 테스트: SQLite 기반 14개 통과. PostGIS/Redis/Celery·Next.js 전체 빌드·Tailscale·실물 장비·실제 모델은 미검증. 100%는 위에 열거한 발표용 파일 준비만 뜻하며, 원래 WBS의 실환경 검증을 완료했다는 뜻이 아니다. 일부 요구사항은 대체 구현/모의 전용이며 정식 목표에서 제외할 수 없다.
