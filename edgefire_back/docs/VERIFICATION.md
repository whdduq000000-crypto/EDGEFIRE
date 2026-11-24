# 간트차트 대응 및 검증 범위

기준: 제공된 EDGE-FIRE 백엔드 6~15주차 간트차트, 11/23 AI·저장소 연동 변경 보고서, 공용 main f97b78d 및 AI 작업 브랜치 0ee2e91. 원본 저장소를 변경하지 않음.

| 간트 과제 | 새 코드 | 검증 상태 |
|---|---|---|
| W6–7 PostGIS 스키마/API/WS 규격 | app/db.py, app/schemas.py, docs/API_CONTRACT.md | 코드 작성; 실제 PostGIS 실행 전 |
| W8–9 FastAPI 센서 수집·조회 | POST /api/v1/telemetry/multimodal, GET /api/v1/storage/telemetry; 멱등성 | SQLite 테스트 통과 |
| W10–11 Swagger, DB 인덱스 | /docs, OpenAPI, node/time index 및 GiST | Swagger/SQLite 테스트 통과; PostGIS 인덱스 실측 전 |
| W11–12 Redis Pub/Sub, WS | app/bus.py, 인증 WS, 재연결/REST 복구 FE | WS 대체 모드 테스트 통과; 실제 Redis 통합 전 |
| W13–14 공간 타일, AI 확산 GeoJSON | PostGIS GeoJSON/MVT/ST_DWithin 및 AI aux 프록시, forecast 저장·WS | 코드 작성; 실제 PostGIS와 AI 기상 자산 실행 전 |
| W14–15 FE 통합·E2E·시연 | 프론트 패치, 원격 워커, HW sender, 테스트/가이드 | API 테스트 통과; 팀 PC/실측 장비/브라우저 E2E 전 |

팀 통합 WBS의 추가 목표(Daily Range Partitioning, PTZ Pelco-D 하드웨어 제어, 위성 백홀, Celery 및 실제 기관 신고, 1,000 TPS/50ms, ST_DWithin 10ms)는 현재 구현 완료로 계산하지 않습니다. 이 패키지는 PostGIS 기본 테이블 및 공간 인덱스, 원격 DB 작업 큐와 Redis Pub/Sub, 멱등 재전송을 사용합니다. 실장비 규격·기관 권한·현장 검증 없이 PTZ/신고를 실행하지 않습니다. 실제 성능 수치는 부하 테스트 후 기록해야 합니다.

## 검증 실행

Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m pytest -q
```

자동 검증은 독립 임시 SQLite DB 및 로컬 TestClient 환경을 사용하므로 실제 데이터에 영향을 주지 않습니다. 원격 AI 워커 API 검증은 모의 결과 fixture이며, 실제 YOLO 정확도나 기존 AI 모델 파일의 성공을 보장하지 않습니다.

검사: 상태/Swagger, 역할별 인증, 센서 수신·저장·중복·충돌·경보, raw/열화상·오류, WS 전달 및 Origin 거부, 신규 이미지→claim→원본 SHA→완료/조회, lease fencing·재시도, 잘못된 이미지·지역 및 미설정 보조 서비스 응답.

## 팀 PC 검수

- BE: `/health`에서 `database=postgis` 및 `redis=connected`. 실측 요청 후 Swagger/GET 조회, `/api/v1/gis/nearby`, MVT 파일 200. Redis 재시작 후 재연결 확인. Spatial API는 좌표가 입력된 센서만 표시.
- FE: AI branch 복사본에서 패치 실행 및 `npm run build`, 센서/과거 자료 탭, 실시간 값/시간/단위/출처, 지도 마커/재연결. 기존 원본 화면의 가상 정보나 94.2% 고정값을 실제 판정으로 사용하지 않음.
- AI: 실제 checkpoint로 2개 이상의 서로 다른 사진 분석, 각 job의 model ID, SHA, 결과 이미지 일치 확인. 기상·대기·비교 자료는 기존 실제 경로 확인. 확산 추정은 미검증 연구 결과.
- HW: 서로 다른 네트워크에서 게이트웨이 실측 JSON 5회 이상, 신호/순번/시간 검수. 오류/재전송 및 Pi 절전/재부팅 대응. 센서 보정 전 ppm 사용 금지.
- 조장: API 로그, FE 캡처, AI 결과, HW 로그를 동시에 기록. 전체 과정의 성공/실패 목록과 미구현 범위 명시.

## 제한

현재 생성 환경에 Docker/PostGIS/Redis, 외부 팀원 VPN, AI 로컬 모델 파일/데이터, 실제 센서 장치 및 기존 Next.js 전체 파일의 실행 환경이 없어 위 항목은 직접 실행하지 못했습니다. Python 코드와 로컬 API 계약 테스트 및 로컬 TCP 실전송 테스트를 별도 수행하고, 결과는 `TEST_RESULTS.txt`에 기록합니다. 프론트 패치는 정확한 읽기 확인 코드 앵커 기반이며 전체 Next.js 빌드는 팀원 PC 필수. 본 시스템은 학습용 연구 시제품이며 실제 화재 대응에 사용하지 않습니다.
