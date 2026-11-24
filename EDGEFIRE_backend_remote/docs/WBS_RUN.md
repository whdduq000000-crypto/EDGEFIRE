# V2.1 실행 순서 (Windows BE)

필수: Git, Python 3.12, Docker Desktop(WSL2), Tailscale. Node는 FE 담당자가 설치/실행. MQTT가 실제 필요할 때만 paho-mqtt 및 TLS broker 설치. Python Celery Windows는 개발용 solo pool 사용(운영/성능 테스트는 Linux/WSL2 권장).

```powershell
git clone -b demo-integration https://github.com/whdduq000000-crypto/EDGEFIRE.git
cd EDGEFIRE\EDGEFIRE_backend_remote
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-test.txt
.\.venv\Scripts\python.exe scripts/init_env.py # existing .env not overwritten
docker compose up -d --wait
.\.venv\Scripts\python.exe scripts/start_backend.py
```

새 터미널에서 같은 폴더로 이동 후:
```powershell
Invoke-RestMethod http://127.0.0.1:8200/health
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/seed_demo_geo.py # 선택; synthetic only
```

Stream/Celery (Redis 실행, API DB init 완료 후 별도 2개 터미널; backend root):
```powershell
.\.venv\Scripts\python.exe -m celery -A app.tasks:celery worker --pool=solo --loglevel=INFO
```
```powershell
.\.venv\Scripts\python.exe -m celery -A app.tasks:celery beat --loglevel=INFO --schedule runtime/celerybeat-schedule
```
기본 API는 `STORED` 반환, `?queued=true`는 `QUEUED` (DB에 아직 없음). worker+beat 시작 후 조회/WS로 저장 확인. Windows solo는 성능 목표 측정용 아님. Redis 정상 연결이 아니라면 /health에 local-fallback 표시.

## FE: 기존 팀 main 코드도 연결 가능
`edgefire_front` 원본을 수정하지 않고 `/remote` 화면을 추가. AI 통합 브랜치를 쓰는 팀은 기존 `patch_frontend.py`를 사용. 두 패치를 동시에 적용하지 않음.
```powershell
# EDGEFIRE_backend_remote 폴더 기준
.\.venv\Scripts\python.exe adapters/frontend/patch_team_frontend.py --front ..\edgefire_front
```
`edgefire_front/.env.local`의 값은 `adapters/frontend/env.local.example`을 참고해서 실제 BE Tailscale IP와 FE 키로 설정. `npm ci`, `npm run build`, `npm run dev -- --hostname 127.0.0.1 --port 3200` 후 `http://127.0.0.1:3200/remote`. 원래 `/` 페이지는 보존(기존 예시 데이터 화면). `gitignore.txt`는 실제 `.gitignore`가 아니므로 FE 비밀 파일을 커밋하지 않도록 아래 명령으로 보호:
```powershell
Add-Content -Path ..\edgefire_front\.gitignore -Value "`n.env.local`n.env.*`nnode_modules/`n.next/"
```
AI 통합 FE는 `docs/REMOTE_SETUP.md` 기존 절차대로 `/`에서 테스트. 원래 공용 FE `/remote`는 실시간 센서/지도/이미지 분석을 검수할 수 있는 별도 경로이며 원본 화면과 모든 기능이 같은 것은 아님. 전체 Next 빌드 실기 확인 필요.

## 부하·TEP
`$env:HARDWARE_API_TOKEN='<키>'` 및 `$env:LOCAL_API_TOKEN='<키>'`는 해당 터미널에서만 설정. 실제 환경/운영 장비 대상 부하 금지.
```powershell
.\.venv\Scripts\python.exe scripts/tep_demo.py --base http://127.0.0.1:8200
.\.venv\Scripts\python.exe -m locust -f scripts/locustfile.py --headless -u 10 -r 2 -t 30s --host http://127.0.0.1:8200 --csv runtime/load_test
```
Locust 미설치 시 먼저 `.\.venv\Scripts\python.exe -m pip install locust` 실행. 10 유저 smoke load 후 환경별 증량. TPS, p95 및 실패율 기록. 1000 TPS 달성/50ms 이하를 수치 검증 전 주장하지 않음. TEP는 실제 챔버가 아니라 합성 CO/H2 입력.

## 실제 원격 연결
Tailscale 설치, 권한 승인 및 IP 확인 후 `.env` BIND_HOST에 BE tailnet IP 적용하고 서버 재시작. DB/Redis 포트는 localhost만, BE 8200 접근은 지정 팀원만 허용. FE는 `.env.local`을 수정하고 재시작. AI 보조 API는 8301 포트를 승인된 BE에서만 접근하게 설정. 세부 설명 `REMOTE_SETUP.md`. 실제 인증키는 역할별 개인 공유, 저장소에 올리지 않음.
