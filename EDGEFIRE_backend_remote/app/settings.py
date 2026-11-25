import os, json
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
def env(key,default=''): return os.environ.get(key,default)
class Settings:
    def __init__(self):
        self.db_url=env('DATABASE_URL','sqlite:///./runtime/telemetry.sqlite')
        self.redis_url=env('REDIS_URL')
        self.storage=Path(env('STORAGE_ROOT','./runtime')).resolve()
        self.ui_key=env('LOCAL_API_TOKEN'); self.hw_key=env('HARDWARE_API_TOKEN'); self.worker_key=env('WORKER_API_TOKEN'); self.ws_key=env('WS_SIGNING_KEY')
        self.origins=set(env('ALLOWED_ORIGINS','http://localhost:3200,http://127.0.0.1:3200').split(','))
        self.aux_url=env('AI_AUX_URL').rstrip('/'); self.aux_token=env('AI_AUX_TOKEN')
        self.rules=json.loads(env('RISK_RULES_JSON','{}'))
        if not isinstance(self.rules,dict): raise ValueError('RISK_RULES_JSON must be object')
        for k,v in self.rules.items():
            if k not in ('demo','measured') or not isinstance(v,dict): raise ValueError('Invalid source rule')
            for field,thresholds in v.items():
                if not (isinstance(field,str) and field.startswith(('gas_data.','raw_data.','thermal.')) and isinstance(thresholds,list) and len(thresholds)==4 and all(type(x) in (int,float) and __import__('math').isfinite(x) for x in thresholds) and all(a<b for a,b in zip(thresholds,thresholds[1:]))): raise ValueError('Invalid risk thresholds')
    def validate(self):
        keys=[self.ui_key,self.hw_key,self.worker_key,self.ws_key]
        if any(len(x)<24 or x=='REPLACE_ME' for x in keys) or len(set(keys))!=4: raise RuntimeError('Configure four distinct secret keys (scripts/init_env.py).')
        if self.aux_url and (len(self.aux_token)<24 or self.aux_token=='REPLACE_ME'): raise RuntimeError('Configure AI_AUX_TOKEN')
