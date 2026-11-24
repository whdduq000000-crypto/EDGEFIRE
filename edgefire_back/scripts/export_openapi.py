"""Export actual FastAPI OpenAPI schema without a running server or real credentials."""
import os, sys, tempfile, json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from app.main import create_app
from app.settings import Settings
with tempfile.TemporaryDirectory() as tmp:
    os.environ.update(DATABASE_URL='sqlite:///'+str(Path(tmp)/'export.sqlite'),STORAGE_ROOT=tmp,REDIS_URL='',AI_AUX_URL='',RISK_RULES_JSON='{}',LOCAL_API_TOKEN='x'*32,HARDWARE_API_TOKEN='y'*32,WORKER_API_TOKEN='z'*32,WS_SIGNING_KEY='s'*32)
    app=create_app(Settings())
    target=root/'docs'/'openapi.json'
    target.write_text(json.dumps(app.openapi(),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    app.state.db.engine.dispose()
    print(target)
