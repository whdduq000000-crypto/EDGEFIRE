import json,uuid,time,hashlib,os
from pathlib import Path
from sqlalchemy import text
from fastapi import HTTPException
class Jobs:
    def __init__(self,db,root): self.db=db; self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True)
    def init(self):
        with self.db.engine.begin() as c:
            c.execute(text('''CREATE TABLE IF NOT EXISTS jobs(id VARCHAR(40) PRIMARY KEY,kind VARCHAR(16) NOT NULL,created DOUBLE PRECISION NOT NULL,updated DOUBLE PRECISION NOT NULL,status VARCHAR(16) NOT NULL,object_id VARCHAR(32) NOT NULL,mime VARCHAR(80) NOT NULL,sha256 VARCHAR(64) NOT NULL,region_id VARCHAR(32),node_id VARCHAR(80),telemetry_event_id VARCHAR(40),attempts INTEGER NOT NULL DEFAULT 0,claim_token VARCHAR(32),lease_until DOUBLE PRECISION,worker_id VARCHAR(80),result TEXT,error TEXT,result_path TEXT,annotated_path TEXT)'''))
            c.execute(text('CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status,created)'))
            c.execute(text('CREATE INDEX IF NOT EXISTS jobs_region_created ON jobs(region_id,created DESC)'))
            c.execute(text('''CREATE TABLE IF NOT EXISTS workers(id VARCHAR(80) PRIMARY KEY,model_id VARCHAR(160) NOT NULL,updated DOUBLE PRECISION NOT NULL,state VARCHAR(16) NOT NULL)'''))
    def path(self,rel):
        p=(self.root/rel).resolve()
        if not p.is_relative_to(self.root): raise ValueError('Invalid file path')
        return p
    def write(self,rel,data):
        p=self.path(rel);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with tmp.open('xb') as f: f.write(data);f.flush();os.fsync(f.fileno())
            os.replace(tmp,p)
        finally: tmp.unlink(missing_ok=True)
    @staticmethod
    def decode(row,private=False):
        v=dict(row); v['result']=json.loads(v['result']) if v['result'] else None
        if not private: v.pop('claim_token',None);v.pop('lease_until',None);v.pop('object_id',None);v.pop('result_path',None);v.pop('annotated_path',None)
        return v
    def get(self,jid,private=False,kind=None):
        with self.db.engine.connect() as c: r=c.execute(text('SELECT * FROM jobs WHERE id=:id'),{'id':jid}).mappings().first()
        if not r or (kind and r['kind']!=kind):raise HTTPException(404,'작업을 찾을 수 없습니다.')
        return self.decode(r,private)
    def enqueue(self,raw,mime,kind='vision',region=None,node=None,event=None):
        oid=uuid.uuid4().hex;jid='JOB_'+uuid.uuid4().hex; now=time.time();self.write('objects/'+oid,raw)
        try:
            with self.db.engine.begin() as c: c.execute(text('''INSERT INTO jobs(id,kind,created,updated,status,object_id,mime,sha256,region_id,node_id,telemetry_event_id) VALUES(:id,:kind,:now,:now,'PENDING',:oid,:mime,:sha,:region,:node,:event)'''),dict(id=jid,kind=kind,now=now,oid=oid,mime=mime,sha=hashlib.sha256(raw).hexdigest(),region=region,node=node,event=event))
        except Exception:self.path('objects/'+oid).unlink(missing_ok=True);raise
        return self.get(jid)
    def list(self,region=None,limit=100):
        where=' AND region_id IS NULL' if region=='unassigned' else (' AND region_id=:region' if region else '')
        with self.db.engine.connect() as c:return [self.decode(r) for r in c.execute(text("SELECT * FROM jobs WHERE kind='vision'"+where+' ORDER BY created DESC LIMIT :limit'),dict(region=region,limit=limit)).mappings()]
    def change_region(self,jid,region):
        self.get(jid,kind='vision')
        with self.db.engine.begin() as c:c.execute(text('UPDATE jobs SET region_id=:region,updated=:now WHERE id=:id'),dict(region=region,now=time.time(),id=jid))
        return self.get(jid)
    def retry(self,jid):
        self.get(jid)
        with self.db.engine.begin() as c:
            n=c.execute(text("UPDATE jobs SET status='PENDING',attempts=0,error=NULL,claim_token=NULL,lease_until=NULL,updated=:now WHERE id=:id AND status='FAILED'"),dict(id=jid,now=time.time())).rowcount
        if not n:raise HTTPException(409,'실패한 작업만 재시도할 수 있습니다.')
        return self.get(jid)
    def ping(self,worker_id,model_id,state='READY'):
        with self.db.engine.begin() as c:c.execute(text('INSERT INTO workers(id,model_id,updated,state) VALUES(:id,:model,:now,:state) ON CONFLICT(id) DO UPDATE SET model_id=excluded.model_id,updated=excluded.updated,state=excluded.state'),dict(id=worker_id,model=model_id,now=time.time(),state=state))
    def workers(self):
        with self.db.engine.connect() as c:return [dict(r) for r in c.execute(text("SELECT id,model_id,updated,state FROM workers WHERE state='READY' AND updated>:cut ORDER BY updated DESC"),{'cut':time.time()-45}).mappings()]
    def claim(self,worker_id,model_id):
        self.ping(worker_id,model_id); now=time.time(); token=uuid.uuid4().hex
        with self.db.engine.begin() as c:
            if not self.db.postgres: c.exec_driver_sql('BEGIN IMMEDIATE')
            c.execute(text("UPDATE jobs SET status=CASE WHEN attempts>=3 THEN 'FAILED' ELSE 'PENDING' END,error='Worker lease expired',claim_token=NULL,lease_until=NULL,updated=:now WHERE status='RUNNING' AND lease_until<:now"),{'now':now})
            sql="SELECT id FROM jobs WHERE status='PENDING' ORDER BY created,id LIMIT 1"+(' FOR UPDATE SKIP LOCKED' if self.db.postgres else '')
            row=c.execute(text(sql)).first()
            if not row:return None
            jid=row[0]; n=c.execute(text("UPDATE jobs SET status='RUNNING',attempts=attempts+1,claim_token=:token,lease_until=:until,worker_id=:worker,error=NULL,updated=:now WHERE id=:id AND status='PENDING'"),dict(token=token,until=now+120,worker=worker_id,now=now,id=jid)).rowcount
            if not n:return None
        return self.get(jid,private=True)
    def owned(self,jid,token):
        job=self.get(jid,private=True)
        if job['status']!='RUNNING' or job['claim_token']!=token or (job['lease_until'] or 0)<=time.time():raise HTTPException(409,'Job lease no longer valid')
        return job
    def renew(self,jid,token):
        now=time.time()
        with self.db.engine.begin() as c:n=c.execute(text("UPDATE jobs SET lease_until=:until,updated=:now WHERE id=:id AND claim_token=:token AND status='RUNNING' AND lease_until>:now"),dict(until=now+120,now=now,id=jid,token=token)).rowcount
        if not n:raise HTTPException(409,'Job lease no longer valid')
    def complete(self,jid,token,result,annotated):
        job=self.owned(jid,token); now=time.time();prefix=f'results/{jid}/{token}'; rp=prefix+'/result.json';ap=prefix+'/annotated.jpg' if annotated else None
        result=dict(result,job_id=jid,input_sha256=job['sha256'],completed_at=now,operational_use=False)
        if job['kind']=='vision': result['model_status']='training_snapshot_not_validated'
        raw=json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf-8')
        if len(raw)>2_000_000:raise HTTPException(413,'Result exceeds 2 MB')
        self.write(rp,raw)
        if annotated:self.write(ap,annotated)
        with self.db.engine.begin() as c:
            n=c.execute(text("UPDATE jobs SET status='COMPLETED',result=:result,result_path=:rp,annotated_path=:ap,error=NULL,lease_until=NULL,updated=:now WHERE id=:id AND claim_token=:token AND status='RUNNING' AND lease_until>:now"),dict(result=raw.decode(),rp=rp,ap=ap,now=time.time(),id=jid,token=token)).rowcount
            if not n:raise HTTPException(409,'Job lease no longer valid')
        return self.get(jid)
    def fail(self,jid,token,error):
        now=time.time()
        with self.db.engine.begin() as c:n=c.execute(text("UPDATE jobs SET status='FAILED',error=:err,updated=:now,lease_until=NULL WHERE id=:id AND claim_token=:token AND status='RUNNING' AND lease_until>:now"),dict(err=error,now=now,id=jid,token=token)).rowcount
        if not n:raise HTTPException(409,'Job lease no longer valid')
