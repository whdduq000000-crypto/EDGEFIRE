"""Celery workers (Redis-backed). Stream messages are acknowledged after DB commit."""
import asyncio, json, os, socket, logging
from celery import Celery
from .settings import Settings
from .db import DB
from .main import assessment_for
from .wbs import gas_analysis
from .schemas import Telemetry
from sqlalchemy import text

s=Settings()
celery=Celery('edgefire',broker=s.redis_url or 'redis://127.0.0.1:6380/0')
celery.conf.update(task_ignore_result=True,task_acks_late=True,worker_prefetch_multiplier=1,task_reject_on_worker_lost=True,broker_connection_retry_on_startup=True,beat_schedule={'drain-telemetry-stream':{'task':'edgefire.drain','schedule':2.0}})
STREAM='edgefire:telemetry:ingest'; GROUP='edgefire-db'; DEAD='edgefire:telemetry:dead'

@celery.task(name='edgefire.dispatch',autoretry_for=(Exception,),retry_backoff=True,max_retries=4)
def simulate_dispatch(dispatch_id):
    db=DB(s)
    try:
        with db.engine.begin() as c:c.execute(text("UPDATE dispatch_log SET status='SIMULATED_NOT_SENT' WHERE id=:id AND status='PENDING_SIMULATION'"),{'id':dispatch_id})
    finally:db.engine.dispose()

@celery.task(name='edgefire.drain')
def drain():
    import redis
    r=redis.from_url(s.redis_url,decode_responses=True,socket_connect_timeout=2,socket_timeout=5)
    consumer=socket.gethostname()+'-'+str(os.getpid())
    db=DB(s)
    # Prevent concurrent scheduled drains for predictable ordering. Expired leases can recover.
    lock=r.lock('edgefire:telemetry:drain_lock',timeout=120,blocking_timeout=0)
    if not lock.acquire():r.close();db.engine.dispose();return
    try:
        try:r.xgroup_create(STREAM,GROUP,id='0',mkstream=True)
        except redis.ResponseError as e:
            if 'BUSYGROUP' not in str(e):raise
        stale=r.xautoclaim(STREAM,GROUP,consumer,min_idle_time=120000,start_id='0-0',count=30)[1]
        batch=stale or [m for _,items in r.xreadgroup(GROUP,consumer,{STREAM:'>'},count=30) for m in items]
        for mid,fields in batch:
            try:
                p=Telemetry.model_validate_json(fields['payload']).model_dump(exclude_none=True)
                a=gas_analysis(db,p,assessment_for(p,s.rules));row,new=db.save(p,a)
            except (ValueError,KeyError) as e:
                r.xadd(DEAD,{'stream_id':mid,'error':str(e)[:500]});r.xack(STREAM,GROUP,mid);r.xdel(STREAM,mid);continue
            event=row['payload']|{'event_type':'telemetry','event_id':row['id'],'assessment':row['result'],'received_at':row['created']}
            # If publish fails, leave entry pending for replay. Duplicate event IDs are safe for UI.
            from .bus import Bus
            async def publish():
                import redis.asyncio as ar
                bus=Bus(s.redis_url);bus.redis=ar.from_url(s.redis_url,decode_responses=True)
                try:
                    await bus.cache_node(event);await bus.redis.publish('edgefire.events',json.dumps(event,allow_nan=False))
                finally:await bus.redis.aclose()
            asyncio.run(publish())
            r.xack(STREAM,GROUP,mid);r.xdel(STREAM,mid)
    finally:
        try:lock.release()
        except redis.exceptions.LockError:pass
        r.close();db.engine.dispose()
