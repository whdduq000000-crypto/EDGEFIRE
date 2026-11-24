# 팀원 공유용 메시지

내일 원격 통합은 팀장 BE 서버를 기준으로 진행합니다. 각자 Tailscale을 설치하고 팀장 tailnet 접속/권한을 확인해 주세요. BE 주소와 각자 필요한 키는 개인 메시지로 공유합니다. `.env` 전체나 비밀번호는 올리지 않습니다.

- BE: 8200번으로 PostGIS/Redis/WS/API 서버 실행. /health 확인 후 팀원 접속 검수.
- FE: AI 통합 브랜치의 별도 복사본에 adapters/frontend/patch_frontend.py 적용. .env.local에 BE 주소/FE 키 설정 후 3200번으로 실행. 실시간 센서와 기존 이미지 분석/지도 검수.
- AI: 기존 고정 모델 그대로 remote_ai_worker.py 실행. 보조 자료가 준비되면 ai_aux.py를 8301로 실행. 기존 로컬 SQLite 공유 방식은 원격에 사용하지 않음.
- HW 2명: 센서/게이트웨이 JSONL 출력 합의. hardware_sender.py의 demo 전송 성공 후 실제 값 전송. 원시 ADC/단위/시각/노드 ID 기록. LoRa가 안 되면 Wi-Fi 우회 시연임을 분명히 표시.

테스트 순서는 BE /health → FE WS → demo 5개 → HW 실측 → AI 신규 이미지 → 확산 자료 → 끊김/재연결 → 통합 시연 영상. 실제 확인되지 않은 결과는 완료로 체크하지 않습니다.
