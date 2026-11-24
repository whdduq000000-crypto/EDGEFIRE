from pathlib import Path
import secrets
p=Path(__file__).resolve().parents[1]; dst=p/'.env'
if dst.exists(): raise SystemExit('.env already exists; not overwritten.')
s=(p/'.env.example').read_text(encoding='utf-8')
for name in ['LOCAL_API_TOKEN','HARDWARE_API_TOKEN','WORKER_API_TOKEN','WS_SIGNING_KEY','AI_AUX_TOKEN']:
    s=s.replace(name+'=REPLACE_ME',name+'='+secrets.token_urlsafe(32))
pw=secrets.token_hex(18); s=s.replace('edgefire_local',pw)
dst.write_text(s,encoding='utf-8'); print('Created .env. Do not commit or publicly share it.')
