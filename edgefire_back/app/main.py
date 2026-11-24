import asyncio,hashlib,io,json,time,re,logging
from contextlib import asynccontextmanager
from fastapi import FastAPI,Depends,Header,HTTPException,WebSocket,WebSocketDisconnect,UploadFile,File,Form,Query,Response
from fastapi.responses import FileResponse,JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image,UnidentifiedImageError
import httpx
from .settings import Settings
from .db import DB
from .jobs import Jobs
from .bus import Bus
from .security import check,signer
from .wbs import gas_analysis, register_routes
from .integration import install as install_integration
from .schemas import Telemetry,WorkerPing,Claim,Lease,Failure
LOG=logging.getLogger('edgefire')
REGIONS=set('chuncheon seoul suwon incheon wonju gangneung goyang paju namyangju yangpyeong gapyeong pocheon sokcho donghae samcheok hongcheon pyeongchang jeongseon'.split())
Image.MAX_IMAGE_PIXELS=30_000_000

def validate_image(raw, jpeg_only=False):
    if not raw or len(raw)>10*1024*1024:raise HTTPException(413,'Image limit: 10 MiB')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in (['JPEG'] if jpeg_only else ['JPEG','PNG','WEBP']) or im.width*im.height>30_000_000 or im.getexif().get(274,1)!=1:raise ValueError('Invalid image format/size/orientation')
            im.load();return Image.MIME[im.format]
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):raise HTTPException(422,'Invalid image')

def assessment_for(payload,rules):
    source=payload['source']; candidates=[]
    for path,bounds in rules.get(source,{}).items():
        category,field=path.split('.',1);v=(payload.get(category) or {}).get(field)
        if type(v) not in (int,float):continue
        if category=='gas_data' and payload.get('gas_unit')!='ppm':continue
        candidates.append((1+sum(v>=b for b in bounds),path))
    level=max((x[0] for x in candidates),default=None)
    return {'status':'PROTOTYPE_RULE' if level is not None else 'NOT_EVALUATED','risk_level':level,'stage':1 if level is not None and level>=3 else None,'operational_use':False,'source':source,'notice':'설정된 연구용 규칙; 실제 화재 확증·안전 판정 아님' if level is not None else '관측값만 저장; 검증된 판정 기준 없음','matched_fields':[p for l,p in candidates if l==level]}

def create_app(settings=None):
    s=settings or Settings();s.validate();db=DB(s);jobs=Jobs(db,s.storage);bus=Bus(s.redis_url);issue,verify=signer(s.ws_key)
    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(db.init);await asyncio.to_thread(jobs.init);await bus.start()
        try:yield
        finally:await bus.close();db.engine.dispose()
    app=FastAPI(title='EDGE-FIRE Remote Backend',version='2.2.0',lifespan=lifespan)
    app.state.db=db;app.state.jobs=jobs;app.state.bus=bus
    app.add_middleware(CORSMiddleware,allow_origins=list(s.origins),allow_credentials=False,allow_methods=['GET','POST'],allow_headers=['Content-Type','X-API-Key'])
    def ui(x_api_key:str|None=Header(None)):
        if not check(x_api_key,s.ui_key):raise HTTPException(401,'Frontend API key required')
    def hardware(x_api_key:str|None=Header(None)):
        if not check(x_api_key,s.hw_key):raise HTTPException(401,'Hardware API key required')
    def worker(x_api_key:str|None=Header(None)):
        if not check(x_api_key,s.worker_key):raise HTTPException(401,'AI worker key required')
    async def aux(path,method='GET',params=None,payload=None):
        if not s.aux_url:raise HTTPException(503,'AI auxiliary service not configured')
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(45,connect=5),follow_redirects=False,trust_env=False) as client:
                response=await client.request(method,s.aux_url+path,headers={'X-API-Key':s.aux_token},params=params,json=payload)
        except httpx.HTTPError:raise HTTPException(503,'AI auxiliary service unavailable')
        if response.status_code>=400:
            try:detail=response.json().get('detail','AI auxiliary service error')
            except Exception:detail='AI auxiliary service error'
            raise HTTPException(response.status_code,detail)
        return response
    async def aux_json(path,**kw):return (await aux(path,**kw)).json()
    @app.get('/')
    def root():return {'status':'ONLINE','message':'EDGE-FIRE remote research prototype','version':'2.2.0'}
    @app.get('/health')
    def health():
        from sqlalchemy import text
        try:
            with db.engine.connect() as c:c.execute(text('SELECT 1'))
            return {'status':'OK','database':'postgis' if db.postgres else 'sqlite-test-mode','redis':'connected' if bus.connected else 'local-fallback','operational_use':False}
        except Exception:return JSONResponse({'status':'DB_UNAVAILABLE'},status_code=503)
    @app.post('/api/v1/telemetry/multimodal',status_code=202,dependencies=[Depends(hardware)])
    @app.post('/api/v1/telemetry',status_code=202,dependencies=[Depends(hardware)])
    async def ingest(packet:Telemetry, queued:bool=False):
        if queued:
            if not bus.redis:raise HTTPException(503,'Redis Stream required')
            try:mid=await bus.redis.xadd('edgefire:telemetry:ingest',{'payload':packet.model_dump_json(exclude_none=True)})
            except Exception:raise HTTPException(503,'Redis Stream unavailable')
            return {'status':'QUEUED','stream_id':mid,'node_id':packet.node_id,'notice':'DB commit pending; use history to verify'}
        payload=packet.model_dump(exclude_none=True);a=await asyncio.to_thread(gas_analysis,db,payload,assessment_for(payload,s.rules))
        try:r,new=await asyncio.to_thread(db.save,payload,a)
        except ValueError as e:raise HTTPException(409,str(e))
        event=r['payload']|{'event_type':'telemetry','event_id':r['id'],'assessment':r['result'],'received_at':r['created']}
        if new:await bus.cache_node(event);await bus.publish(event)
        return {'status':'STORED' if new else 'DUPLICATE','node_id':r['node_id'],'event_id':r['id'],'assessment':r['result']}
    @app.get('/api/v1/telemetry',dependencies=[Depends(ui)])
    @app.get('/api/v1/storage/telemetry',dependencies=[Depends(ui)])
    def history(node_id:str|None=None,limit:int=Query(100,ge=1,le=1000)):return db.history(node_id,limit)
    @app.get('/api/v1/storage/nodes',dependencies=[Depends(ui)])
    def nodes():return db.nodes()
    @app.get('/api/v1/gis/nodes.geojson',dependencies=[Depends(ui)])
    @app.get('/api/v1/storage/nodes.geojson',dependencies=[Depends(ui)])
    def geojson(west:float=-180,south:float=-90,east:float=180,north:float=90):
        if not (-180<=west<=east<=180 and -90<=south<=north<=90):raise HTTPException(422,'Invalid bounding box')
        return db.geojson(west,south,east,north)
    @app.get('/api/v1/gis/nearby',dependencies=[Depends(ui)])
    def nearby(latitude:float=Query(ge=-90,le=90),longitude:float=Query(ge=-180,le=180),radius_m:float=Query(1000,gt=0,le=100000)):
        try:return db.nearby(latitude,longitude,radius_m)
        except NotImplementedError:raise HTTPException(503,'PostGIS required')
    @app.get('/api/v1/gis/tiles/{z}/{x}/{y}.mvt',dependencies=[Depends(ui)])
    def tile(z:int,x:int,y:int):
        if not (0<=z<=22 and 0<=x<2**z and 0<=y<2**z):raise HTTPException(422,'Invalid tile coordinates')
        try:return Response(db.mvt(z,x,y),media_type='application/vnd.mapbox-vector-tile')
        except NotImplementedError:raise HTTPException(503,'PostGIS required')
    @app.get('/api/v1/storage/alerts',dependencies=[Depends(ui)])
    def alerts(limit:int=Query(100,ge=1,le=500)):return db.alerts(limit)
    @app.post('/api/v1/storage/alerts/{alert_id}/ack',dependencies=[Depends(ui)])
    def ack(alert_id:str):
        if not db.ack(alert_id):raise HTTPException(404,'Alert not found')
        return {'status':'ACKNOWLEDGED','operational_use':False}
    @app.get('/api/v1/storage/ws-ticket',dependencies=[Depends(ui)])
    def ticket():return {'ticket':issue(),'expires_in':90}
    @app.websocket('/api/v1/ws/hazard')
    @app.websocket('/ws/hazard')
    async def ws(socket:WebSocket):
        protocols=socket.scope.get('subprotocols',[]);token=next((p[7:] for p in protocols if p.startswith('ticket.')),None)
        if socket.headers.get('origin') not in s.origins or 'edgefire.v1' not in protocols or not token or not verify(token):await socket.close(code=1008);return
        await socket.accept(subprotocol='edgefire.v1');q=asyncio.Queue(maxsize=100);bus.clients.add(q)
        async def transmit():
            while True:
                try:event=await asyncio.wait_for(q.get(),timeout=20)
                except asyncio.TimeoutError:event={'event_type':'heartbeat','timestamp':int(time.time())}
                await socket.send_json(event)
        async def receive():
            while True:await socket.receive_text()
        t1=asyncio.create_task(transmit());t2=asyncio.create_task(receive())
        try:await asyncio.wait([t1,t2],return_when=asyncio.FIRST_COMPLETED)
        finally:
            bus.clients.discard(q)
            for t in (t1,t2):t.cancel()
            try:await asyncio.gather(t1,t2,return_exceptions=True)
            except asyncio.CancelledError:pass
    @app.get('/api/v1/storage/config',dependencies=[Depends(ui)])
    def config():
        w=jobs.workers();return {'storage_type':'central_db_files_remote_worker','operational_use':False,'worker_available':bool(w),'model_id':w[0]['model_id'] if w else 'unavailable','model_status':'training_snapshot_not_validated','ai_model_available':bool(w),'worker_count':len(w)}
    @app.get('/api/v1/storage/jobs',dependencies=[Depends(ui)])
    def list_jobs(region:str|None=None):
        if region and region not in REGIONS|{'unassigned'}:raise HTTPException(422,'Unknown region')
        return jobs.list(region)
    @app.get('/api/v1/storage/jobs/{jid}',dependencies=[Depends(ui)])
    def get_job(jid:str):return jobs.get(jid,kind='vision')
    @app.post('/api/v1/storage/jobs',status_code=202,dependencies=[Depends(ui)])
    async def upload(image:UploadFile=File(...),region_id:str|None=Form(None),node_id:str|None=Form(None),telemetry_event_id:str|None=Form(None)):
        if region_id and region_id not in REGIONS:raise HTTPException(422,'Unknown region')
        if node_id and not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',node_id):raise HTTPException(422,'Invalid node ID')
        if telemetry_event_id:
            e=await asyncio.to_thread(db.get,telemetry_event_id)
            if not e or (node_id and node_id!=e['node_id']):raise HTTPException(422,'Invalid/mismatched telemetry event')
            node_id=e['node_id']
        raw=await image.read(10*1024*1024+1);mime=await asyncio.to_thread(validate_image,raw)
        return await asyncio.to_thread(jobs.enqueue,raw,mime,'vision',region_id,node_id,telemetry_event_id)
    @app.post('/api/v1/storage/jobs/{jid}/location',dependencies=[Depends(ui)])
    def location(jid:str,payload:dict):
        if set(payload)!={'region_id'} or not isinstance(payload['region_id'],str) or payload['region_id'] not in REGIONS:raise HTTPException(422,'Unknown region')
        return jobs.change_region(jid,payload['region_id'])
    @app.post('/api/v1/storage/jobs/{jid}/retry',status_code=202,dependencies=[Depends(ui)])
    def retry(jid:str):
        jobs.get(jid,kind='vision');return jobs.retry(jid)
    @app.get('/api/v1/storage/jobs/{jid}/image',dependencies=[Depends(ui)])
    def image(jid:str):
        j=jobs.get(jid,private=True,kind='vision');return FileResponse(jobs.path('objects/'+j['object_id']),media_type=j['mime'],headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    @app.get('/api/v1/storage/jobs/{jid}/annotated',dependencies=[Depends(ui)])
    def annotated(jid:str):
        j=jobs.get(jid,private=True,kind='vision')
        if j['status']!='COMPLETED' or not j['annotated_path']:raise HTTPException(404,'Analysis pending')
        return FileResponse(jobs.path(j['annotated_path']),media_type='image/jpeg',headers={'Cache-Control':'no-store'})
    @app.get('/api/v1/storage/jobs/{jid}/result',dependencies=[Depends(ui)])
    def result(jid:str):
        j=jobs.get(jid,kind='vision')
        if j['status']!='COMPLETED':raise HTTPException(404,'Analysis pending')
        return j['result']
    @app.get('/api/v1/storage/models',dependencies=[Depends(ui)])
    async def models():
        if not s.aux_url:return {'status':'TRAINING_OR_NOT_REGISTERED','operational_use':False}
        return await aux_json('/models')
    @app.get('/api/v1/storage/model-examples',dependencies=[Depends(ui)])
    async def examples():return await aux_json('/model-examples') if s.aux_url else {'cases':[],'chemical_cids':[]}
    @app.post('/api/v1/storage/assessments',status_code=202,dependencies=[Depends(ui)])
    async def assessment(payload:dict):
        allowed={'vision_job_id','chemical_cid','temperature_c','response_features','reference_case_id'}
        if set(payload)-allowed or len(json.dumps(payload))>50000:raise HTTPException(422,'Invalid assessment input')
        if (await models()).get('status')!='RESEARCH_MODELS_REGISTERED':raise HTTPException(409,'Research models not registered')
        await aux_json('/validate-assessment',method='POST',payload=payload)
        vision=None
        if payload.get('vision_job_id'):
            j=await asyncio.to_thread(jobs.get,payload['vision_job_id'],False,'vision')
            if j['status']!='COMPLETED':raise HTTPException(409,'Image analysis pending')
            vision={'job_id':j['id'],'model_id':j['result'].get('model_id'),'detections':j['result'].get('detections',[]),'notice':'Detection score is not ignition probability'}
        data=json.dumps({'payload':payload,'vision':vision},ensure_ascii=False,allow_nan=False).encode()
        return await asyncio.to_thread(jobs.enqueue,data,'application/json','assessment')
    @app.get('/api/v1/storage/assessments/{jid}',dependencies=[Depends(ui)])
    def get_assessment(jid:str):return jobs.get(jid,kind='assessment')
    @app.get('/api/v1/storage/training-status',dependencies=[Depends(ui)])
    async def training():return await aux_json('/training-status') if s.aux_url else {'available':False}
    @app.get('/api/v1/storage/air-quality/stations',dependencies=[Depends(ui)])
    async def stations():return await aux_json('/air-quality/stations')
    @app.get('/api/v1/storage/air-quality/series',dependencies=[Depends(ui)])
    async def series(station:str,end:str|None=None):return await aux_json('/air-quality/series',params={'station':station,**({'end':end} if end else {})})
    @app.get('/api/v1/storage/forecast/regions',dependencies=[Depends(ui)])
    async def forecast_regions():return await aux_json('/forecast/regions')
    @app.get('/api/v1/storage/forecast',dependencies=[Depends(ui)])
    async def forecast_get():return await aux_json('/forecast')
    @app.post('/api/v1/storage/forecast',dependencies=[Depends(ui)])
    async def forecast(payload:dict):
        result=await aux_json('/forecast',method='POST',payload=payload)
        if result.get('type')!='FeatureCollection' or not isinstance(result.get('features'),list):raise HTTPException(502,'Invalid forecast format')
        result.setdefault('metadata',{})['operational_use']=False
        forecast_id=await asyncio.to_thread(db.record_forecast,result)
        await bus.publish({'event_type':'forecast','forecast_id':forecast_id,'forecast':result,'operational_use':False})
        return result
    @app.get('/api/v1/storage/vision-examples',dependencies=[Depends(ui)])
    async def vision_examples():return await aux_json('/vision-examples') if s.aux_url else {'status':'PREPARING','cases':[]}
    @app.get('/api/v1/storage/vision-examples/{case}/{variant}',dependencies=[Depends(ui)])
    async def example_image(case:str,variant:str):
        if not re.fullmatch(r'[a-f0-9]{16,64}',case) or variant not in {'original','ground-truth','prediction'}:raise HTTPException(404,'Invalid example')
        r=await aux('/vision-examples/'+case+'/'+variant);return Response(r.content,media_type='image/jpeg',headers={'Cache-Control':'no-store'})
    @app.post('/api/v1/worker/heartbeat',dependencies=[Depends(worker)])
    def heartbeat(p:WorkerPing):jobs.ping(p.worker_id,p.model_id,p.state);return {'ok':True}
    @app.post('/api/v1/worker/claim',dependencies=[Depends(worker)])
    def claim(p:Claim):return {'job':jobs.claim(p.worker_id,p.model_id)}
    @app.get('/api/v1/worker/jobs/{jid}/input',dependencies=[Depends(worker)])
    def input_file(jid:str,x_claim_token:str=Header(...)):
        j=jobs.owned(jid,x_claim_token);return FileResponse(jobs.path('objects/'+j['object_id']),media_type=j['mime'])
    @app.post('/api/v1/worker/jobs/{jid}/renew',dependencies=[Depends(worker)])
    def renew(jid:str,p:Lease):jobs.renew(jid,p.claim_token);return {'ok':True}
    @app.post('/api/v1/worker/jobs/{jid}/fail',dependencies=[Depends(worker)])
    def fail(jid:str,p:Failure):jobs.fail(jid,p.claim_token,p.error);return {'ok':True}
    @app.post('/api/v1/worker/jobs/{jid}/complete',dependencies=[Depends(worker)])
    async def complete(jid:str,claim_token:str=Form(...),result_json:str=Form(...),annotated:UploadFile|None=File(None)):
        j=await asyncio.to_thread(jobs.owned,jid,claim_token)
        try:
            if len(result_json)>2_000_000:raise ValueError('Result too large')
            r=json.loads(result_json);assert isinstance(r,dict);json.dumps(r,allow_nan=False)
        except (ValueError,AssertionError,TypeError):raise HTTPException(422,'Invalid result JSON')
        raw=await annotated.read(10*1024*1024+1) if annotated else None
        if j['kind']=='vision':
            if not raw or not isinstance(r.get('detections'),list) or not r.get('model_id') or not r.get('model_sha256'):raise HTTPException(422,'Vision result/image required')
            await asyncio.to_thread(validate_image,raw,True)
        completed=await asyncio.to_thread(jobs.complete,jid,claim_token,r,raw)
        await bus.publish({'event_type':'vision_review' if j['kind']=='vision' else 'assessment_completed','job_id':jid,'node_id':j['node_id'],'telemetry_event_id':j['telemetry_event_id'],'stage':2 if j['telemetry_event_id'] and j['kind']=='vision' else None,'result':completed['result'],'operational_use':False})
        return completed
    register_routes(app,db,bus,s,ui,hardware,worker,aux_json)
    install_integration(app,db,bus,s,ui,hardware,aux_json)
    return app
