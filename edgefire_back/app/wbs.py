"""Detailed W6–W15 prototype extensions. No live emergency dispatch."""
import json, math, time, uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from fastapi import Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, ConfigDict


def init_wbs(db,c):
    c.execute(text('CREATE TABLE IF NOT EXISTS wui_zones (zone_id VARCHAR(80) PRIMARY KEY, name TEXT NOT NULL, geometry TEXT NOT NULL, source VARCHAR(16) NOT NULL)'))
    c.execute(text('CREATE TABLE IF NOT EXISTS sensor_nodes (node_id VARCHAR(80) PRIMARY KEY, latitude DOUBLE PRECISION NOT NULL, longitude DOUBLE PRECISION NOT NULL, wui_zone_id VARCHAR(80), risk_level INT DEFAULT 0, kind VARCHAR(16) NOT NULL, source VARCHAR(16) NOT NULL, ts BIGINT NOT NULL)'))
    c.execute(text('CREATE TABLE IF NOT EXISTS wui_assets (asset_id VARCHAR(80) PRIMARY KEY, kind VARCHAR(16) NOT NULL, name TEXT NOT NULL, latitude DOUBLE PRECISION NOT NULL, longitude DOUBLE PRECISION NOT NULL, households INT NOT NULL DEFAULT 0, source VARCHAR(16) NOT NULL)'))
    c.execute(text('CREATE TABLE IF NOT EXISTS ptz_commands (id VARCHAR(40) PRIMARY KEY, created DOUBLE PRECISION NOT NULL, payload TEXT NOT NULL)'))
    c.execute(text('CREATE TABLE IF NOT EXISTS vision_metadata (id VARCHAR(40) PRIMARY KEY, created DOUBLE PRECISION NOT NULL, payload TEXT NOT NULL)'))
    c.execute(text('CREATE TABLE IF NOT EXISTS dispatch_log (id VARCHAR(40) PRIMARY KEY, created DOUBLE PRECISION NOT NULL, channel VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL, payload TEXT NOT NULL)'))
    c.execute(text('CREATE TABLE IF NOT EXISTS forecast_polygons (forecast_id VARCHAR(40) NOT NULL, feature_no INT NOT NULL, minutes INT NOT NULL, geometry TEXT NOT NULL, PRIMARY KEY(forecast_id,feature_no))'))
    tail=' PARTITION BY RANGE (ts)' if db.postgres else ''
    c.execute(text('CREATE TABLE IF NOT EXISTS telemetry_gas_logs (event_id VARCHAR(40) NOT NULL, ts BIGINT NOT NULL, node_id VARCHAR(80) NOT NULL, gas_json TEXT NOT NULL, PRIMARY KEY(ts,event_id))'+tail))
    c.execute(text('CREATE INDEX IF NOT EXISTS gas_node_ts ON telemetry_gas_logs(node_id,ts DESC)'))
    c.execute(text('CREATE INDEX IF NOT EXISTS telemetry_sync ON telemetry(created,id)'))
    if db.postgres:
        for table in ('sensor_nodes','wui_assets'):
            c.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS location geometry(Point,4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude,latitude),4326)) STORED'))
            c.execute(text(f'CREATE INDEX IF NOT EXISTS {table}_location_gist ON {table} USING GIST(location)'))
            c.execute(text(f'CREATE INDEX IF NOT EXISTS {table}_geography_gist ON {table} USING GIST((location::geography))'))
        for table in ('wui_zones','forecast_polygons'):
            c.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS geom geometry(Geometry,4326)'))
            c.execute(text(f'CREATE INDEX IF NOT EXISTS {table}_geom_gist ON {table} USING GIST(geom)'))
        c.execute(text('CREATE INDEX IF NOT EXISTS gas_ts_brin ON telemetry_gas_logs USING BRIN(ts)'))
        for i in range(-1,3): ensure_partition(c,int(time.time())+i*86400)


def ensure_partition(c,ts):
    day=datetime.fromtimestamp(ts,timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    name='telemetry_gas_logs_'+day.strftime('%Y%m%d'); start=int(day.timestamp()); end=start+86400
    if c.execute(text('SELECT to_regclass(:name)'),{'name':name}).scalar() is None:
        c.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':start})
        if c.execute(text('SELECT to_regclass(:name)'),{'name':name}).scalar() is not None:return
        c.execute(text(f'CREATE TABLE IF NOT EXISTS {name} PARTITION OF telemetry_gas_logs FOR VALUES FROM ({start}) TO ({end})'))


def mirror_packet(db,c,p,eid,a):
    if p.get('gas_data'):
        if db.postgres:ensure_partition(c,p['timestamp'])
        c.execute(text('INSERT INTO telemetry_gas_logs VALUES(:id,:ts,:node,:gas) ON CONFLICT DO NOTHING'),dict(id=eid,ts=p['timestamp'],node=p['node_id'],gas=json.dumps({'gas_data':p['gas_data'],'gas_unit':p['gas_unit'],'source':p['source']})))
    if p.get('latitude') is not None:
        c.execute(text('''INSERT INTO sensor_nodes(node_id,latitude,longitude,risk_level,kind,source,ts) VALUES(:node,:lat,:lon,:risk,'sensor',:source,:ts) ON CONFLICT(node_id) DO UPDATE SET latitude=excluded.latitude,longitude=excluded.longitude,risk_level=excluded.risk_level,source=excluded.source,ts=excluded.ts WHERE excluded.ts>=sensor_nodes.ts'''),dict(node=p['node_id'],lat=p['latitude'],lon=p['longitude'],risk=a.get('risk_level') or 0,source=p['source'],ts=p['timestamp']))


def gas_analysis(db,p,assessment):
    """Rates and ratio are observations, never proof of ignition or false-alarm rejection."""
    gas=p.get('gas_data') or {}; metrics={'status':'INSUFFICIENT_INPUT','rates_per_second':{},'CO_H2_ratio':None,'operational_use':False}
    if p['gas_unit']!='ppm' or not gas: return assessment|{'ensemble':metrics}
    with db.engine.connect() as c:
        rows=c.execute(text('SELECT payload FROM telemetry WHERE node_id=:node AND boot_id=:boot AND source=:source AND ts<:ts ORDER BY ts DESC,created DESC LIMIT 30'),dict(node=p['node_id'],boot=p['boot_id'],source=p['source'],ts=p['timestamp'])).scalars()
        prev=next((v for r in rows if (v:=json.loads(r)).get('gas_unit')=='ppm' and v.get('gas_data')),None)
    if prev:
        dt=p['timestamp']-prev['timestamp']; metrics['interval_seconds']=dt
        if dt<=300:
            for k,v in gas.items():
                old=prev['gas_data'].get(k)
                if v is not None and old is not None:metrics['rates_per_second'][k]=(v-old)/dt
    if gas.get('CO') is not None and gas.get('H2') is not None and gas['H2']>0:metrics['CO_H2_ratio']=gas['CO']/gas['H2']
    if metrics['rates_per_second'] and metrics['CO_H2_ratio'] is not None:metrics['status']='RESEARCH_FEATURES_ONLY'
    metrics['notice']='오탐 구분 임계값 및 실측 보정 미검증; 조성비만으로 화목보일러/영농소각/산불을 확정하지 않음'
    return assessment|{'ensemble':metrics}


def bearing(lat1,lon1,lat2,lon2):
    if (lat1,lon1)==(lat2,lon2):raise ValueError('Identical coordinates')
    a,b,d=map(math.radians,(lat1,lat2,lon2-lon1));return math.degrees(math.atan2(math.sin(d)*math.cos(b),math.cos(a)*math.sin(b)-math.sin(a)*math.cos(b)*math.cos(d)))%360


def pelco(address,action,speed):
    commands={'left':(0,4,speed,0),'right':(0,2,speed,0),'up':(0,8,0,speed),'down':(0,16,0,speed),'zoom_in':(0,32,0,0),'zoom_out':(0,64,0,0),'stop':(0,0,0,0)}
    data=[address,*commands[action]];return bytes([255,*data,sum(data)%256]).hex().upper()


class Point(BaseModel):
    model_config=ConfigDict(extra='forbid')
    latitude:float=Field(ge=-90,le=90,allow_inf_nan=False)
    longitude:float=Field(ge=-180,le=180,allow_inf_nan=False)
class PTZ(BaseModel):
    model_config=ConfigDict(extra='forbid')
    camera:Point|None=None
    target:Point|None=None
    action:str=Field(pattern='^(auto|left|right|up|down|zoom_in|zoom_out|stop)$')
    address:int=Field(1,ge=1,le=255)
    speed:int=Field(16,ge=0,le=63)
class Detection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    class_name:str=Field(min_length=1,max_length=80)
    score:float=Field(ge=0,le=1,allow_inf_nan=False)
    bbox_xyxy:list[float]=Field(min_length=4,max_length=4)
class Vision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    node_id:str=Field(min_length=1,max_length=80)
    model_id:str=Field(min_length=1,max_length=160)
    timestamp:int=Field(ge=0,le=4102444800)
    detections:list[Detection]=Field(max_length=100)
    ir_snapshot_url:str|None=Field(None,max_length=2048)
    inference_ms:float|None=Field(None,ge=0,allow_inf_nan=False)
class Dispatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    channel:str=Field(pattern='^(119|forest|relay|cbs|alimtalk)$')
    event_id:str=Field(pattern=r'^EVT_[a-f0-9]{32}$')


def register_routes(app,db,bus,s,ui,hardware,worker,aux_json):
    def list_table(table):
        with db.engine.connect() as c:return [dict(r) for r in c.execute(text(f'SELECT * FROM {table}')).mappings()]
    @app.get('/api/v1/zones',dependencies=[Depends(ui)])
    def zones():return {'type':'FeatureCollection','features':[{'type':'Feature','geometry':json.loads(r['geometry']),'properties':{'zone_id':r['zone_id'],'name':r['name'],'source':r['source']}} for r in list_table('wui_zones')]}
    @app.get('/api/v1/zones/{zone_id}',dependencies=[Depends(ui)])
    def zone(zone_id:str):
        with db.engine.connect() as c:r=c.execute(text('SELECT zone_id,name,geometry,source FROM wui_zones WHERE zone_id=:id'),{'id':zone_id}).mappings().first()
        if not r:raise HTTPException(404,'Zone not registered')
        return {'type':'Feature','geometry':json.loads(r['geometry']),'properties':{k:r[k] for k in ('zone_id','name','source')}}
    @app.get('/api/v1/sensors',dependencies=[Depends(ui)])
    def sensors():return db.nodes()
    @app.get('/api/v1/sensors/nearby',dependencies=[Depends(ui)])
    def nearby(latitude:float=Query(ge=-90,le=90),longitude:float=Query(ge=-180,le=180),radius_m:float=Query(1000,gt=0,le=100000)):
        if not db.postgres:raise HTTPException(503,'PostGIS required')
        sql='''SELECT node_id,kind,source,ST_Distance(location::geography,ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography) distance_m FROM sensor_nodes WHERE ST_DWithin(location::geography,ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography,:r) ORDER BY location::geography <-> ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography LIMIT 1000'''
        with db.engine.connect() as c:return [dict(r) for r in c.execute(text(sql),dict(lat=latitude,lon=longitude,r=radius_m)).mappings()]
    @app.get('/api/v1/telemetry/history',dependencies=[Depends(ui)])
    def history(node_id:str|None=None,hours:int=Query(24,ge=1,le=24),limit:int=Query(1000,ge=1,le=5000)):
        sql='SELECT * FROM telemetry WHERE ts>=:since '+('AND node_id=:node ' if node_id else '')+'ORDER BY ts DESC,created DESC LIMIT :limit'
        with db.engine.connect() as c:return [db.decode(r) for r in c.execute(text(sql),dict(since=int(time.time())-hours*3600,node=node_id,limit=limit)).mappings()]
    @app.get('/api/v1/storage/sync',dependencies=[Depends(ui)])
    def sync(after_created:float=Query(0,ge=0),after_id:str='',limit:int=Query(1000,ge=1,le=5000)):
        with db.engine.connect() as c:rows=[db.decode(r) for r in c.execute(text('SELECT * FROM telemetry WHERE created>:t OR (created=:t AND id>:id) ORDER BY created,id LIMIT :n'),dict(t=after_created,id=after_id,n=limit+1)).mappings()]
        page=rows[:limit];last=page[-1] if page else None
        return {'rows':page,'has_more':len(rows)>limit,'cursor':{'after_created':last['created'] if last else after_created,'after_id':last['id'] if last else after_id}}
    @app.post('/api/v1/camera/ptz/command',dependencies=[Depends(ui)])
    def ptz(p:PTZ):
        result={'id':'PTZ_'+uuid.uuid4().hex,'status':'SIMULATED_NOT_SENT','operational_use':False,'action':p.action}
        if p.action=='auto':
            if not p.camera or not p.target:raise HTTPException(422,'Camera and target coordinates required')
            a,b=p.camera,p.target
            try:
                if db.postgres:
                    with db.engine.connect() as c: angle=c.execute(text('SELECT degrees(ST_Azimuth(ST_SetSRID(ST_MakePoint(:a,:b),4326)::geography,ST_SetSRID(ST_MakePoint(:c,:d),4326)::geography))'),dict(a=a.longitude,b=a.latitude,c=b.longitude,d=b.latitude)).scalar()
                    if angle is None:raise ValueError('Identical coordinates')
                else:angle=bearing(a.latitude,a.longitude,b.latitude,b.longitude)
            except ValueError as e:raise HTTPException(422,str(e))
            result.update(target_azimuth_deg=angle,notice='Absolute pointing requires camera calibration/feedback; no automatic motor command sent')
        else:result['pelco_d_hex']=pelco(p.address,p.action,p.speed)
        with db.engine.begin() as c:c.execute(text('INSERT INTO ptz_commands VALUES(:id,:t,:p)'),dict(id=result['id'],t=time.time(),p=json.dumps(result)))
        return result
    @app.post('/api/v1/vision/metadata',dependencies=[Depends(hardware)])
    async def metadata(p:Vision):
        for det in p.detections:
            x,y,X,Y=det.bbox_xyxy
            if not all(math.isfinite(v) for v in (x,y,X,Y)) or min(x,y)<0 or X<=x or Y<=y:raise HTTPException(422,'Invalid bbox')
        item=p.model_dump()|{'id':'VIS_'+uuid.uuid4().hex,'status':'RESEARCH_RESULT','operational_use':False,'stage':2,'notice':'검토 결과, 화재 확정 아님'}
        with db.engine.begin() as c:c.execute(text('INSERT INTO vision_metadata VALUES(:id,:t,:p)'),dict(id=item['id'],t=time.time(),p=json.dumps(item,allow_nan=False)))
        await bus.publish({'event_type':'vision_review','node_id':p.node_id,'result':item,'stage':2,'operational_use':False});return item
    @app.get('/api/v1/vision/metadata',dependencies=[Depends(ui)])
    def vision_history(limit:int=Query(100,ge=1,le=500)):
        with db.engine.connect() as c:return [json.loads(r) for r in c.execute(text('SELECT payload FROM vision_metadata ORDER BY created DESC LIMIT :n'),{'n':limit}).scalars()]
    @app.get('/api/v1/prediction/diffusion',dependencies=[Depends(ui)])
    def diffusion(forecast_id:str|None=None):
        with db.engine.connect() as c:r=c.execute(text('SELECT id,payload FROM forecasts '+('WHERE id=:id ' if forecast_id else '')+'ORDER BY created DESC LIMIT 1'),{'id':forecast_id}).mappings().first()
        if not r:raise HTTPException(404,'Forecast not calculated')
        result=json.loads(r['payload']);result.setdefault('metadata',{})['forecast_id']=r['id'];return result
    @app.get('/api/v1/prediction/diffusion/{forecast_id}/impact',dependencies=[Depends(ui)])
    def impact(forecast_id:str):
        if not db.postgres:raise HTTPException(503,'PostGIS required')
        with db.engine.connect() as c:
            if not c.execute(text('SELECT 1 FROM forecasts WHERE id=:id'),{'id':forecast_id}).first():raise HTTPException(404,'Forecast missing')
            assets=c.execute(text('SELECT DISTINCT a.asset_id,a.name,a.kind,a.households,a.source FROM wui_assets a JOIN forecast_polygons p ON ST_Intersects(p.geom,a.location) WHERE p.forecast_id=:id AND p.minutes=30'),{'id':forecast_id}).mappings().all()
            total=c.execute(text('SELECT count(*) FROM wui_assets')).scalar()
        return {'status':'RESEARCH_INTERSECTION' if total else 'NO_REGISTERED_ASSETS','assets':[dict(a) for a in assets],'households':sum(a['households'] for a in assets) if total else None,'operational_use':False}
    @app.get('/api/v1/prediction/diffusion/{forecast_id}/tiles/{z}/{x}/{y}.mvt',dependencies=[Depends(ui)])
    def forecast_tile(forecast_id:str,z:int,x:int,y:int):
        if not db.postgres:raise HTTPException(503,'PostGIS required')
        if not 0<=z<=22 or not 0<=x<2**z or not 0<=y<2**z:raise HTTPException(422,'Invalid tile')
        with db.engine.connect() as c: data=c.execute(text('''WITH b AS (SELECT ST_TileEnvelope(:z,:x,:y) geom), t AS (SELECT minutes,ST_AsMVTGeom(ST_Transform(p.geom,3857),b.geom,4096,64,true) geom FROM forecast_polygons p,b WHERE forecast_id=:id AND ST_Intersects(p.geom,ST_Transform(b.geom,4326))) SELECT ST_AsMVT(t,'forecast',4096,'geom') FROM t'''),dict(z=z,x=x,y=y,id=forecast_id)).scalar()
        return Response(bytes(data or b''),media_type='application/vnd.mapbox-vector-tile')
    @app.post('/api/v1/dispatch/simulate',status_code=202,dependencies=[Depends(ui)])
    def dispatch(p:Dispatch):
        event=db.get(p.event_id)
        if not event:raise HTTPException(404,'Event missing')
        item={'id':'DSP_'+uuid.uuid4().hex,'channel':p.channel,'event_id':p.event_id,'operational_use':False,'notice':'실제 신고·문자·방송은 전송하지 않습니다.'}
        with db.engine.begin() as c:c.execute(text('INSERT INTO dispatch_log VALUES(:id,:t,:ch,:st,:p)'),dict(id=item['id'],t=time.time(),ch=p.channel,st='PENDING_SIMULATION',p=json.dumps(item)))
        try:
            if s.redis_url:
                from .tasks import simulate_dispatch
                simulate_dispatch.delay(item['id'])
            else:
                with db.engine.begin() as c:c.execute(text("UPDATE dispatch_log SET status='SIMULATED_NOT_SENT' WHERE id=:id"),{'id':item['id']})
        except Exception:
            with db.engine.begin() as c:c.execute(text("UPDATE dispatch_log SET status='QUEUE_UNAVAILABLE' WHERE id=:id"),{'id':item['id']})
            raise HTTPException(503,'Simulation queue unavailable')
        return item|{'status':'PENDING_SIMULATION' if s.redis_url else 'SIMULATED_NOT_SENT'}
    @app.get('/api/v1/dispatch/stats',dependencies=[Depends(ui)])
    def dispatch_stats():
        with db.engine.connect() as c:rows=[dict(r) for r in c.execute(text('SELECT channel,status,count(*) count FROM dispatch_log GROUP BY channel,status')).mappings()]
        return {'counts':rows,'operational_use':False}
