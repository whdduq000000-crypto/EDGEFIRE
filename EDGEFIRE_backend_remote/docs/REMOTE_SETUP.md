# 11월 25일 원격 통합 실행 가이드

## A. 팀 공통 — 서로 다른 Wi-Fi 해결

추천: [Tailscale](https://tailscale.com/docs/how-to/quickstart). 각자 계정으로 가입하고 팀장 tailnet에 초대하거나 필요한 기기 공유를 승인합니다. 같은 계정 비밀번호를 공유하지 않습니다. 요금제/초대 인원·기기 수 제한은 계정 화면에서 확인합니다. 필요한 방향은 **FE→BE:8200**, **AI→BE:8200**, **HW gateway→BE:8200**, **BE→AI:8301**입니다. 한 기기 공유만으로 마지막 역방향 접근이 자동 허용되는 것은 아닙니다. 같은 tailnet 및 권한 정책으로 이 네 방향을 허용합니다.

1. BE, FE, AI, HW 게이트웨이 PC/Pi에 설치. Raspberry Pi OS는 [Linux 공식 안내](https://tailscale.com/docs/install/linux) 참조.
2. 각자 `tailscale ip -4` 또는 Tailscale 앱에서 100.x.y.z 주소 확인. 네 PC/AI PC 주소를 기록하고, 팀장에게만 공유.
3. 각 PC에서 상대의 Tailscale IP 접근 확인. Windows PowerShell: `Test-NetConnection <BE_IP> -Port 8200` (서버 실행 후). AI 보조 서버는 BE에서 `Test-NetConnection <AI_IP> -Port 8301`.
4. Windows 방화벽은 필요한 TCP 포트만, 로컬 Tailscale IP 및 승인된 상대 Tailscale IP 범위로 제한해 허용합니다. 공유기 포트포워딩, 인터넷 공개, Tailscale Funnel을 사용하지 않습니다.
5. FE 브라우저는 FE PC에서 `http://127.0.0.1:3200`으로 접속합니다. 다른 팀원도 FE를 보기 원하면 FE PC 화면 공유 또는 각 PC에 FE 로컬 실행(원격 공개 금지). 발표 PC에서 로컬 FE를 실행하는 것도 가능합니다.

참고: [Tailscale 연결](https://tailscale.com/docs/how-to/connect-to-devices), [초대](https://tailscale.com/docs/features/sharing/how-to/invite-any-user), [접근 제어](https://tailscale.com/docs/features/access-control).

## B. 팀장/백엔드 PC

README 순서로 설치 후 `scripts/init_env.py`로 `.env` 생성. 다음 값 수정:

```dotenv
BIND_HOST=100.x.y.z
PORT=8200
# AI 담당자의 실제 Tailscale 주소. AI aux 미준비면 비워둘 수 있음.
AI_AUX_URL=http://100.a.b.c:8301
ALLOWED_ORIGINS=http://127.0.0.1:3200,http://localhost:3200,http://127.0.0.1:3000,http://localhost:3000
```

`100.x.y.z`, `100.a.b.c`는 예시 자리표시자이며 실제 IP로 바꿉니다. .env 전체를 단톡/GitHub에 올리지 말고 아래 값만 역할별 개인 메시지로 전달하세요.

| 대상 | 공유 값 |
|---|---|
| FE | BE_URL, LOCAL_API_TOKEN |
| AI | BE_URL, WORKER_API_TOKEN, AI_AUX_TOKEN |
| HW | BE_URL, HARDWARE_API_TOKEN |

`WS_SIGNING_KEY`, DB 암호는 팀장 PC에만 보관. 인증키는 내일 검수 후 필요 시 회전. `.env` 수정 후 BE를 다시 시작해야 반영됩니다.

```powershell
docker compose up -d --wait
.\.venv\Scripts\python.exe scripts/start_backend.py
```

새 PowerShell에서 `Invoke-RestMethod http://<BE_IP>:8200/health`. DB와 Redis를 외부 공유하지 않습니다. 서버 PC 절전 해제 및 지속 실행 필요. Docker Desktop이 설치되어 있지 않다면 README의 SQLite 모드로 먼저 통신을 검수한 뒤 PostGIS/Redis로 재전환합니다.

## C. 프론트 담당자

1. 기존 [AI 통합 브랜치](https://github.com/5eungju/edge-fire-ai-data/tree/codex/storage-worker-integration)를 새 폴더에 내려받습니다. `edgefire_AI/fire_forecast/regions.json`도 필요하므로 전체 저장소 구조를 유지합니다. **기존 팀 FE `main`이 아니라 AI 브랜치의 `edgefire_front`를 패치 대상으로 지정**합니다.
2. 배포 ZIP을 풀고 새 PowerShell에서 ZIP 폴더로 이동 후 아래 명령. `<경로>`는 실제 경로로 치환.

```powershell
py adapters/frontend/patch_frontend.py --front 'C:\work\edge-fire-ai-data\edgefire_front'
```

패치 스크립트는 지정된 소스 앵커가 다르면 변경 전 중단합니다. 원본은 별도 형제 폴더 `edgefire_front_remote_patch_backup`에 백업합니다. `LiveTelemetry.tsx`를 추가하고 `page.tsx`, `CesiumMap.js`, 프록시 allowlist를 변경합니다. 기존 AI 이미지·지역·과거 대기 화면은 보존합니다. 원격 차트와 실제 노드 목록을 추가합니다. `/team-demo`는 기존 예시 화면이고 발표에서 사용하지 마세요.

3. `edgefire_front/.env.local` 생성(샘플 `adapters/frontend/env.local.example`). 아래 IP/키를 실제 값으로 바꿉니다.

```dotenv
BACKEND_BASE_URL=http://<BE_IP>:8200
NEXT_PUBLIC_EDGEFIRE_WS_URL=ws://<BE_IP>:8200/api/v1/ws/hazard
FRONTEND_BASE_URL=http://127.0.0.1:3200
LOCAL_API_TOKEN=<FE 전용 인증키>
```

`LOCAL_API_TOKEN`에는 `NEXT_PUBLIC_`을 붙이지 않습니다. `NEXT_PUBLIC_EDGEFIRE_WS_URL`에는 키를 넣지 않습니다. 서버 프록시가 REST 인증을 하고 브라우저는 90초 유효 단기 WS 접속 티켓만 발급받습니다.

```powershell
cd 'C:\work\edge-fire-ai-data\edgefire_front'
npm ci
npm run build
npm run dev -- --hostname 127.0.0.1 --port 3200
```

lockfile이 없는 복사본이면 `npm install` 후 lockfile 생성. Node.js 버전/패키지 호환 오류는 AI 브랜치의 기존 설치 환경을 우선 재사용하세요. `.env.local` 변경 시 Next 재시작(빌드 배포라면 다시 빌드). `http://127.0.0.1:3200`에서 WS 연결 표시·센서 수신·사진 업로드 확인. 원격 지도에서 실제 좌표 없는 장치는 마커를 만들지 않으며 차트에는 표시합니다. 모의 테스트 좌표는 `source=demo`와 함께 표시합니다.

## D. AI 담당자 — 기존 모델 그대로 사용

AI 저장소는 위 브랜치 기준. 기존 코드/가중치/데이터를 유지하며 **기존 `integration/run_local.py`는 원격 통합용으로 쓰지 않습니다.** 이 실행기는 과거 단일 노트북 구조입니다. 새 워커가 중앙 BE에서 이미지 작업을 가져옵니다.

기존 AI Python 환경에서 `httpx`, FastAPI, uvicorn이 설치됐는지 확인. 기존 모델과 YOLO 의존성은 그대로 사용합니다. 중간 스냅샷 `training-snapshot-06a79486d923` 또는 담당자가 실제로 확인한 고정 체크포인트 경로/ID를 입력. 모델 최종 검증 여부를 과장하지 않습니다.

**터미널 1 — 원격 추론 워커** (AI PC, ZIP 폴더 기준):

```powershell
$env:EDGEFIRE_BACKEND_URL='http://<BE_IP>:8200'
$env:WORKER_API_TOKEN='<AI 워커 키>'
py adapters/remote_ai_worker.py --ai-source 'C:\work\edge-fire-ai-data\edgefire_AI' --model 'C:\actual\fixed_snapshot.pt' --model-id 'training-snapshot-06a79486d923' --registry-root 'C:\actual\edgefire_storage_v1'
```

`--registry-root`는 선택 인자이며 multi_model_registry.json이 준비되어 있을 때만 실제 저장소 경로로 지정. 없으면 이 인자를 제거하고 이미지 분석만 검수. `--model-id`는 실제 모델 ID와 일치하도록 입력. 모델 파일을 실행 중인 학습 `last.pt`로 직접 가리키지 말고 고정 복사본 사용. 토큰 유효 여부 확인. AI PC의 모델/전체 데이터는 GitHub에 공개 업로드하지 않음.

**터미널 2 — 기존 기상·대기·비교 이미지·통합모델 API 보조 서비스**:

```powershell
$env:AI_AUX_TOKEN='<AI 보조 API 키>'
py adapters/ai_aux.py --ai-source 'C:\work\edge-fire-ai-data\edgefire_AI' --storage-root 'C:\actual\edgefire_storage_v1' --weather-root 'C:\actual\fire_forecast_202512' --air-root 'C:\actual\air_quality_2026_v2' --examples-root 'C:\actual\image_comparison_demo_v1' --training-status 'C:\actual\status.json' --host <AI_IP> --port 8301
```

AI 담당자가 갖고 있는 실제 경로를 확인해서 치환합니다. 보조 데이터가 없다면 해당 기능은 503/준비 중을 표시해야 하며 사진 분석은 독립 실행 가능. BE `.env`에서 `AI_AUX_URL` 및 같은 `AI_AUX_TOKEN` 설정 확인 후 재시작. 기존 데이터 서비스의 현장 정확도·최종 모델은 이 패키지가 보증하지 않습니다.

## E. 하드웨어 담당자 — Gateway / Raspberry Pi

Pi 또는 게이트웨이에서 Tailscale 사용. LoRa 장치 자체에는 VPN이 필요하지 않으며 게이트웨이가 백엔드로 HTTP 전송합니다. 센서 읽기/LoRa 수신 코드에서 JSON 한 줄을 표준 출력 또는 시리얼로 보내도록 담당자가 연결합니다. 현재 장비 배선/드라이버/LoRa 프레임 규격은 확보되지 않아 이 패키지가 대신 확정하지 않습니다.

Linux/Pi:

```bash
export EDGEFIRE_BACKEND_URL='http://<BE_IP>:8200'
export HARDWARE_API_TOKEN='<HW 키>'
python3 adapters/hardware_sender.py --demo --count 5 --interval 2
```

`--demo`는 합성 입력입니다. FE 화면에서 시연으로 표기되는지 확인. **실센서 연결**은 실제 센서 스크립트가 JSONL을 stdout으로 출력하게 만든 뒤 다음 중 하나를 사용합니다.

```bash
python3 actual_sensor_reader.py | python3 adapters/hardware_sender.py --stdin
# 게이트웨이가 USB 시리얼로 JSONL을 보내는 경우 (pyserial 설치 필요)
python3 -m pip install pyserial
python3 adapters/hardware_sender.py --serial /dev/ttyUSB0 --baud 115200
# 저장 파일 재전송
python3 adapters/hardware_sender.py --file readings.jsonl
# 네트워크 복구 후 이전 PENDING 데이터 재전송
python3 adapters/hardware_sender.py --drain
```

Windows PowerShell에서는 `$env:EDGEFIRE_BACKEND_URL='...'`, `$env:HARDWARE_API_TOKEN='...'` 후 `py` 사용. `actual_sensor_reader.py`는 팀 HW 코드의 이름으로 교체. JSON 구조는 API_CONTRACT.md 참조. 실제 HW가 쓰는 장치 ID/순번/시각·단위를 공유. CO/H2/VOC는 보정된 실측이 없다면 생략하고 `raw_data`에 ADC 값을 기록합니다. `source=measured`는 실제 장치의 관측을 의미할 뿐 ppm 정확도나 산불 여부를 보증하지 않습니다.

게이트웨이 스풀은 SQLite에 남습니다. 재시도 시 boot_id/sequence_no/timestamp를 유지합니다. `REJECTED`는 오류를 검토하여 수정된 신규 패킷으로 재전송해야 하며 자동 반복하지 않습니다. 실측 데이터로 보이게 테스트 수치를 조작하지 않습니다.

## F. 내일 통합 순서 (이대로 진행)

1. BE `/health` 및 `/docs`. DB/Redis 연결 확인. 팀원에게 `Test-NetConnection` 결과 받기.
2. FE 앱 실행 → WS 연결 표시 확인. HW `--demo` 5회 → `STORED` 로그, FE 차트의 값·시간 확인. 데모 규칙 사용 시 위험 1~5단계 표기.
3. HW 실제 센서/게이트웨이 JSONL 전송 → `source=measured`, ADC 원시값, 시각/열화상(가능하면) 확인. 센서 좌표가 없으면 차트만 확인.
4. AI 워커 실행 → FE 사진 업로드 → PENDING/RUNNING/COMPLETED, 원본·결과 이미지/검출 확인. 사진과 선택 센서 이벤트를 수동 연결하면 2차 영상 검토 이벤트를 WS로 반환. 자동 촬영/실화재 확증은 아님.
5. AI aux 실행 → BE 기상/대기 자료 경로 확인, FE 지역·시간 선택 및 GeoJSON 표시. 보조 데이터 없으면 오류/준비 상태 확인.
6. 네트워크를 잠시 끊은 뒤 복구 → HW `--drain`, FE 자동 재연결·REST 이력 재조회, AI 워커 임대/재시도 확인. 로그와 화면 캡처.
7. 통합 재시작 후 5회 반복. 실제 성능·연동 성공 기준을 기록한 뒤 발표 자료에 반영. 실제 신고·방송은 하지 않음.
