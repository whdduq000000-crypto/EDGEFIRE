# EDGE-FIRE 백엔드 v2.0 — 원격 통합 패키지

2026-11-24 | FastAPI · PostgreSQL/PostGIS · Redis · WebSocket · 원격 AI 워커 · 센서 게이트웨이

**먼저 `docs/REMOTE_SETUP.md`를 읽으세요.** 이 프로젝트는 기존 팀 공용 코드를 덮어쓰지 않는 별도 백엔드입니다. 기존 AI 브랜치의 이미지 저장·결과·기상 API 계약을 유지하는 중앙 서버를 제공합니다. 네 팀원이 서로 다른 Wi-Fi에 있어도 같은 사설 VPN에 연결해 테스트하도록 구성했습니다.

## 1. 실행 순서 (백엔드 Windows)

Python 3.11/3.12, Docker Desktop(Compose), Tailscale이 필요합니다. PowerShell에서 이 폴더로 이동하세요.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/init_env.py
notepad .env
```

`.env`의 `BIND_HOST`를 팀장 PC의 실제 Tailscale IPv4로 변경합니다. (먼저 로컬만 테스트하려면 127.0.0.1.) 임의 공개 IP나 `0.0.0.0`로 무방비 공개하지 마세요. `RISK_RULES_JSON`은 기본 `{}`로 판정을 보류합니다. 테스트용 규칙이 필요할 때만 다음처럼 설정합니다.

```dotenv
RISK_RULES_JSON='{"demo":{"gas_data.CO":[10,20,40,80]}}'
```

위 값은 **합성 테스트 데이터 전용**이며 산불 안전 기준이 아닙니다.

```powershell
docker compose up -d --wait
.\.venv\Scripts\python.exe scripts/start_backend.py
```

브라우저에서 `http://<BE_TAILSCALE_IP>:8200/docs`와 `/health` 확인. `database=postgis`, `redis=connected`인지 확인합니다. 8200은 BE, 3200은 FE, 8301은 AI 보조 데이터 서비스입니다. DB/Redis 포트는 로컬에만 연결됩니다.

Docker가 없을 경우 **테스트 모드**만 사용 가능합니다. `.env`에서 `DATABASE_URL=sqlite:///./runtime/telemetry.sqlite`, `REDIS_URL=`로 바꾼 뒤 다시 실행합니다. 이 경우 PostGIS 공간 타일·거리 조회와 Redis 경로는 미검증/미사용이라고 기록합니다. DB 전환 시 기존 SQLite 기록이 자동 이전되지 않습니다.

## 2. 파일 구조

```
main.py                       ASGI 진입점
app/main.py                   REST, Swagger, WS, 원격 AI 작업 API, 보조 자료 프록시
app/settings.py               환경설정·인증 키 검사
app/schemas.py                센서·열화상·워커 스키마
app/db.py                     저장·조회·중복방지·PostGIS DDL/GeoJSON/MVT/거리·경보
app/jobs.py                   분석 큐·임대/재시도·원본/결과 파일 저장
app/bus.py                    Redis Pub/Sub·단일 프로세스 대체 브로드캐스트
app/security.py               단기 WS 티켓
compose.yaml                  PostgreSQL/PostGIS, Redis
adapters/remote_ai_worker.py  기존 AI VisionPredictor를 호출하는 원격 워커
adapters/ai_aux.py            AI PC의 기상·대기·모델·비교 이미지 서비스
adapters/hardware_sender.py   하드웨어 JSONL/시리얼 수신 및 재전송
adapters/frontend/            기존 AI 통합 프론트 수정 패치 + 실시간 차트
scripts/                      키 생성, 서버 실행, 네트워크 검수
 tests/                       자동 API 계약 검증
 docs/                        역할별 연결, API, 간트차트, 검증 가이드
```

## 3. 완료 범위 및 주의

- 팀 공용 원본 `whdduq000000-crypto/EDGEFIRE` main `f97b78d` 및 AI `codex/storage-worker-integration` `0ee2e91` 계약을 바탕으로 새 코드를 작성했습니다.
- 이미지 워커는 공유 SQLite 파일을 네트워크로 열지 않고 중앙 API에서 작업을 받아 원본·결과를 주고받습니다. AI 데이터와 모델은 AI PC에 남겨둡니다.
- 센서값은 실제 제공 값만 저장합니다. MQ 보정 없이 CO/H2/VOC의 정확한 ppm으로 간주하지 않습니다. 기본 위험 단계는 null(판정 대기)입니다. 이미지 검출은 산불 확증이 아닙니다.
- 실제 PTZ 자동 선회·119·문자·방송 송출·위성 백홀·현장 산불 검증을 하지 않습니다. 비상 버튼은 기존 시연 UI에 한정합니다.
- 로컬 SQLite 모드에서 자동 테스트 통과. 실제 PostGIS/Redis/팀원 VPN/YOLO 가중치/하드웨어/Next.js 전체 빌드는 각 PC에서 최종 검수 필요합니다. 자세한 구분은 `docs/VERIFICATION.md`.

## 4. 원본 코드 변경 금지 및 병합

이 패키지는 독립 실행용입니다. 기존 main을 덮어쓰지 말고 팀 저장소의 새 브랜치 또는 별도 폴더에서 실행합니다. 기존 `edgefire_back`과 동시에 동일 포트를 사용하지 않습니다. 새 코드 공개 전에 `.env`, 이미지, DB, 학습 체크포인트를 제외하고 검수 후 커밋하세요. FE 패치는 **AI 통합 브랜치의 복사본**에 적용합니다. 기존 공용 FE main만으로는 AI 기능이 없습니다.
