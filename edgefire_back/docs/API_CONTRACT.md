# API 계약 / ICD (v2.0)

서버 `http://<BE_IP>:8200` / 자동 Swagger `/docs`, OpenAPI `/openapi.json`. 인증 헤더 `X-API-Key`. 키는 FE, HW, AI worker 역할별로 다릅니다. 요청의 수치·시간·좌표는 실제 제공 데이터만 입력합니다. HTTP 오류는 위험 정상 판정이 아닙니다.

## 센서 입력 (HW key)

POST `/api/v1/telemetry/multimodal` (또는 `/api/v1/telemetry`). 기존 CO/H2/VOC 구조를 유지하되 미측정은 생략 가능. 예시는 **시연용 가상 데이터**.

```json
{
  "node_id": "NODE_WUI_0102",
  "boot_id": "BOOT_DEMO_001",
  "sequence_no": 1,
  "timestamp": 1795510000,
  "source": "demo",
  "gas_unit": "unknown",
  "raw_data": {"MQ2_adc": 12000, "MQ135_adc": 9500},
  "environment": {"temperature": 24.2, "humidity_percent": 49.5},
  "thermal": {"max_c": 29.1, "mean_c": 25.2, "frame_width": 32, "frame_height": 24},
  "latitude": 37.5,
  "longitude": 127.0,
  "rssi": -85,
  "snr": 8
}
```

- 필수: node_id, sequence_no, 최소 관측 1개. 원격 재전송에는 timestamp(Unix 초), boot_id(재부팅 세션 ID)도 반드시 고정. 시간 미입력은 수신 시각으로 보완되므로 구버전 재전송 시 충돌 가능. 202 응답 `STORED` 또는 동일 패킷 `DUPLICATE`. 같은 ID/순번에 다른 본문은 409. 누락/유효성 오류 422.
- `source`: measured(실제 관측), demo(합성/시연), unknown(출처 미확인). gas_unit: ppm(검증된 보정 값만), index, unknown. 보정되지 않은 MQ 센서는 `raw_data`에 ADC 또는 전압을 명확한 필드명으로 전달.
- `latitude/longitude`: 함께 제공, WGS84. 위치를 모르면 둘 다 생략. 열화상 값은 실제 센서 출력이 있을 때만 입력.
- `assessment`: 기본 NOT_EVALUATED/risk_level=null. 설정된 연구 규칙의 경우 PROTOTYPE_RULE/1~5, stage=1(3단계 이상). 이는 실제 안전 판정이 아님.
- 위험 규칙 `RISK_RULES_JSON`은 source별 측정 필드의 오름차순 경계 4개를 지정. 실측 규칙은 팀 검증 후에만 별도 설정. 기본값 비어 있음.

## FE 및 GIS (FE key)

| Method | 경로 | 반환 |
|---|---|---|
| GET | /health | DB/Redis 상태(인증 불필요) |
| GET | /api/v1/storage/telemetry?node_id=...&limit=100 | 최신순 row 목록: id, payload, result(assessment), created |
| GET | /api/v1/storage/nodes | 노드별 최근 패킷 |
| GET | /api/v1/storage/nodes.geojson | 실제 입력 좌표의 FeatureCollection |
| GET | /api/v1/gis/nodes.geojson?west=...&south=...&east=...&north=... | 공간 범위 조회 |
| GET | /api/v1/gis/nearby?latitude=37.5&longitude=127&radius_m=1000 | PostGIS 거리 조회 |
| GET | /api/v1/gis/tiles/{z}/{x}/{y}.mvt | PostGIS MVT, SQLite에서는 503 |
| GET | /api/v1/storage/alerts | 연구 규칙 트리거 이력 |
| POST | /api/v1/storage/alerts/{ALT_id}/ack | 관제 확인(외부 신고 아님) |
| GET | /api/v1/storage/ws-ticket | 브라우저 단기 티켓 |
| WS | /api/v1/ws/hazard (또는 /ws/hazard) | telemetry, vision_review, assessment_completed, forecast, heartbeat |

WS 연결 시 Origin은 BE 허용 목록에 일치해야 합니다. WebSocket protocols: `['edgefire.v1','ticket.'+ticket]`. 티켓 발급은 서버 프록시에서 FE API 키 사용. TTL 90초는 접속 시 검증하며 이미 연결된 세션 종료시간이 아님. FE 컴포넌트는 재연결 시 새 티켓 및 REST 이력 조회. Redis pub/sub 장애 시 단일 프로세스 대체 브로드캐스트; 영속 이력이 정본.

## 기존 AI 통합 FE API 호환 (FE key)

모두 `/api/v1/storage` prefix. 프론트 Next.js `/api/edgefire/...`에서 서버 프록시.

- GET `/config`, `/jobs?region=seoul`, `/jobs/{JOB_id}`, `/jobs/{id}/image`, `/jobs/{id}/annotated`, `/jobs/{id}/result`, `/training-status`, `/models`, `/model-examples`
- POST `/jobs` multipart `image`(JPEG/PNG/WEBP, ≤10MiB, 3천만 픽셀 이하), 선택 `region_id`, `node_id`, `telemetry_event_id`. 기존 18개 지역 ID 유지. 이미지 작업이 완료되면 결과 JSON/이미지 저장. `region_id`는 사용자가 정한 지역이며 GPS 검증 아님.
- POST `/jobs/{id}/location` JSON `{"region_id":"seoul"}`; `/jobs/{id}/retry` 실패한 것만 재시도. `/assessments` POST, `/assessments/{id}` GET: AI registry 등록된 경우에만 작동. 학습/등록 미완료 409.
- GET `/forecast`, `/forecast/regions`, POST `/forecast` (기존 region/latitude/longitude/input_time). AI PC 기존 서비스 계산 결과를 전달하고 중앙 DB에 기록·WS 이벤트 전송. 실제 지형/연료 모델 검증 결과가 아님.
- GET `/air-quality/stations`, `/air-quality/series?station=...&end=...`, `/vision-examples`, `/vision-examples/{case}/{variant}`. 과거 자료/비교 이미지가 없는 경우 503/준비 중/404 등으로 표현.

## 원격 AI worker (Worker key)

| Method | 경로 | 설명 |
|---|---|---|
| POST | /api/v1/worker/heartbeat | worker_id, model_id, state READY/STOPPED |
| POST | /api/v1/worker/claim | worker_id, model_id; job 또는 null |
| GET | /api/v1/worker/jobs/{id}/input | X-Claim-Token 별도 헤더; 입력 원본 |
| POST | /api/v1/worker/jobs/{id}/renew | claim_token; 120초 임대 연장 |
| POST | /api/v1/worker/jobs/{id}/complete | multipart claim_token, result_json, annotated JPEG(vision 필수) |
| POST | /api/v1/worker/jobs/{id}/fail | claim_token, error |

워커는 기존 `VisionPredictor`를 사용하며 원본 SHA256을 검사. stale token은 409, 최대 세 번 임대 만료 후 실패. 완료된 이미지 결과는 해당 작업에만 연결. job id와 event id를 혼동하지 않음. 영상 검토 stage=2는 직접 연결된 센서 이벤트가 있을 때만 전달되고, 모델 점수는 화재 발생 확률/실제 확증이 아님. 이미지 검출 결과·모델 ID·SHA256·검출 목록을 보존. AI worker 및 aux는 같은 AI PC에서 실행할 수 있으며 aux는 별도 인증.
