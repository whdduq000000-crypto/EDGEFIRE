"""Additional WBS endpoints. External equipment and emergency dispatch remain simulated."""
import json, math, time
from typing import Literal
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from .schemas import Id, Number

class NodeRegistration(BaseModel):
    model_config=ConfigDict(extra='forbid')
    node_id: Id
    latitude: Number=Field(ge=-90,le=90)
    longitude: Number=Field(ge=-180,le=180)
    kind: Literal['sensor','camera']='sensor'
    source: Literal['demo','measured','unknown']='unknown'
    wui_zone_id: Id|None=None

class AssetRegistration(BaseModel):
    model_config=ConfigDict(extra='forbid')
    asset_id: Id
    kind: Literal['village','facility','relay']
    name: str=Field(min_length=1,max_length=160)
    latitude: Number=Field(ge=-90,le=90)
    longitude: Number=Field(ge=-180,le=180)
    households: int=Field(0,ge=0,le=1000000)
    source: Literal['demo','measured','unknown']='unknown'

class ZoneRegistration(BaseModel):
    model_config=ConfigDict(extra='forbid')
    zone_id: Id
    name: str=Field(min_length=1,max_length=160)
    source: Literal['demo','measured','unknown']='unknown'
    # Simple GeoJSON Polygon; PostGIS also checks topology.
    coordinates: list[list[tuple[Number,Number]]]=Field(min_length=1,max_length=50)
    @model_validator(mode='after')
    def check_rings(self):
        if sum(map(len,self.coordinates))>10000:raise ValueError('Too many coordinates')
        for ring in self.coordinates:
            if len(ring)<4 or ring[0]!=ring[-1] or len(set(ring))<3:raise ValueError('Closed polygon ring with at least three distinct points required')
            if any(not(-180<=lon<=180 and -90<=lat<=90) for lon,lat in ring):raise ValueError('Invalid coordinates')
        return self


def install(app,db,bus,s,ui,hardware,aux_json):
    @app.post('/api/v1/zones',dependencies=[Depends(ui)])
    def register_zone(p:ZoneRegistration):
        data=p.model_dump();g=json.dumps({'type':'Polygon','coordinates':data.pop('coordinates')},allow_nan=False)
        with db.engine.begin() as c:
            if db.postgres and not c.execute(text('SELECT ST_IsValid(ST_SetSRID(ST_GeomFromGeoJSON(:g),4326)) AND NOT ST_IsEmpty(ST_GeomFromGeoJSON(:g))'),{'g':g}).scalar():raise HTTPException(422,'Invalid polygon topology')
            c.execute(text('INSERT INTO wui_zones(zone_id,name,source,geometry) VALUES(:zone_id,:name,:source,:g) ON CONFLICT(zone_id) DO UPDATE SET name=excluded.name,source=excluded.source,geometry=excluded.geometry'),data|{'g':g})
            if db.postgres:c.execute(text('UPDATE wui_zones SET geom=ST_SetSRID(ST_GeomFromGeoJSON(:g),4326) WHERE zone_id=:zone_id'),data|{'g':g})
        return {'status':'REGISTERED','zone_id':p.zone_id,'operational_use':False}
    @app.post('/api/v1/sensors/register',dependencies=[Depends(ui)])
    def register_node(p:NodeRegistration):
        with db.engine.begin() as c:
            if p.wui_zone_id and not c.execute(text('SELECT 1 FROM wui_zones WHERE zone_id=:z'),{'z':p.wui_zone_id}).first():raise HTTPException(404,'Zone not registered')
            c.execute(text('''INSERT INTO sensor_nodes(node_id,latitude,longitude,wui_zone_id,risk_level,kind,source,ts) VALUES(:node_id,:latitude,:longitude,:wui_zone_id,0,:kind,:source,0) ON CONFLICT(node_id) DO UPDATE SET latitude=excluded.latitude,longitude=excluded.longitude,wui_zone_id=excluded.wui_zone_id,kind=excluded.kind,source=excluded.source'''),p.model_dump())
        return {'status':'REGISTERED','node_id':p.node_id,'operational_use':False}
    @app.get('/api/v1/sensors/registry',dependencies=[Depends(ui)])
    def registry():
        with db.engine.connect() as c:return [dict(r) for r in c.execute(text('SELECT node_id,latitude,longitude,wui_zone_id,risk_level,kind,source,ts FROM sensor_nodes ORDER BY node_id LIMIT 1000')).mappings()]
    @app.post('/api/v1/gis/assets',dependencies=[Depends(ui)])
    def register_asset(p:AssetRegistration):
        with db.engine.begin() as c:c.execute(text('''INSERT INTO wui_assets(asset_id,kind,name,latitude,longitude,households,source) VALUES(:asset_id,:kind,:name,:latitude,:longitude,:households,:source) ON CONFLICT(asset_id) DO UPDATE SET kind=excluded.kind,name=excluded.name,latitude=excluded.latitude,longitude=excluded.longitude,households=excluded.households,source=excluded.source'''),p.model_dump())
        return {'status':'REGISTERED','asset_id':p.asset_id,'operational_use':False}
    @app.get('/api/v1/telemetry/gas-history',dependencies=[Depends(ui)])
    def gas_history(node_id:str|None=None,hours:int=Query(24,ge=1,le=24),limit:int=Query(1000,ge=1,le=5000)):
        sql='SELECT event_id,ts,node_id,gas_json FROM telemetry_gas_logs WHERE ts>=:since '+('AND node_id=:node ' if node_id else '')+'ORDER BY ts DESC,event_id DESC LIMIT :n'
        with db.engine.connect() as c:rows=[dict(r) for r in c.execute(text(sql),{'since':int(time.time())-hours*3600,'node':node_id,'n':limit}).mappings()]
        return [dict(event_id=r['event_id'],timestamp=r['ts'],node_id=r['node_id'],**json.loads(r['gas_json'])) for r in rows]
    @app.get('/api/v1/telemetry/gaps',dependencies=[Depends(hardware)])
    def gaps(node_id:str,boot_id:str,start:int=Query(ge=0),end:int=Query(ge=0,le=2**63-1)):
        if end<start or end-start>=10000:raise HTTPException(422,'Window must contain 1–10000 sequence numbers')
        with db.engine.connect() as c:present=set(c.execute(text('SELECT seq FROM telemetry WHERE node_id=:node AND boot_id=:boot AND seq BETWEEN :a AND :b'),{'node':node_id,'boot':boot_id,'a':start,'b':end}).scalars())
        missing=[]
        for seq in range(start,end+1):
            if seq not in present:
                if missing and missing[-1][1]+1==seq:missing[-1][1]=seq
                else:missing.append([seq,seq])
        return {'node_id':node_id,'boot_id':boot_id,'received':len(present),'missing_count':end-start+1-len(present),'missing_ranges':missing,'note':'Only this explicit sequence window; not a guarantee of end-to-end delivery'}
    @app.get('/api/v1/camera/ptz/commands',dependencies=[Depends(ui)])
    def ptz_history(limit:int=Query(100,ge=1,le=500)):
        with db.engine.connect() as c:return [json.loads(r) for r in c.execute(text('SELECT payload FROM ptz_commands ORDER BY created DESC LIMIT :n'),{'n':limit}).scalars()]
    @app.get('/api/v1/dispatch/history',dependencies=[Depends(ui)])
    def dispatch_history(limit:int=Query(100,ge=1,le=500)):
        with db.engine.connect() as c:return [json.loads(r['payload'])|{'status':r['status'],'created':r['created']} for r in c.execute(text('SELECT payload,status,created FROM dispatch_log ORDER BY created DESC LIMIT :n'),{'n':limit}).mappings()]
    @app.get('/api/v1/dispatch/relay-candidates',dependencies=[Depends(ui)])
    def relay_candidates(latitude:float=Query(ge=-90,le=90),longitude:float=Query(ge=-180,le=180)):
        if not db.postgres:raise HTTPException(503,'PostGIS required')
        with db.engine.connect() as c:rows=[dict(r) for r in c.execute(text("SELECT asset_id,name,source,ST_Distance(location::geography,ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography) AS distance_m FROM wui_assets WHERE kind='relay' AND ST_DWithin(location::geography,ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography,1000) ORDER BY distance_m LIMIT 1000"),{'lat':latitude,'lon':longitude}).mappings()]
        return {'candidates':rows,'radius_m':1000,'status':'SIMULATED_NOT_SENT','operational_use':False}
    @app.get('/api/v1/storage/node-cache/{node_id}',dependencies=[Depends(ui)])
    async def cache(node_id:str):
        if not bus.redis:raise HTTPException(503,'Redis unavailable')
        try:raw=await bus.redis.hget('node:status:'+node_id,'payload');ttl=await bus.redis.ttl('node:status:'+node_id)
        except Exception:raise HTTPException(503,'Redis unavailable')
        if not raw or ttl<=0:raise HTTPException(404,'No current cached observation')
        return {'event':json.loads(raw),'ttl_seconds':ttl}
    @app.post('/api/v1/prediction/diffusion/from-event/{event_id}',dependencies=[Depends(ui)])
    async def event_forecast(event_id:str,input_time:str=Query(min_length=16,max_length=20)):
        # Explicit operator research request; never automatically declare a fire.
        import asyncio
        e=await asyncio.to_thread(db.get,event_id)
        if not e:raise HTTPException(404,'Event missing')
        if e['latitude'] is None or e['longitude'] is None:raise HTTPException(422,'Event coordinates missing')
        payload={'region':'map','latitude':e['latitude'],'longitude':e['longitude'],'input_time':input_time}
        result=await aux_json('/forecast',method='POST',payload=payload)
        if not isinstance(result,dict) or result.get('type')!='FeatureCollection' or not isinstance(result.get('features'),list):raise HTTPException(502,'Invalid forecast format')
        result.setdefault('metadata',{}).update(event_id=event_id,operational_use=False,weather_kind='AI auxiliary historical weather; not live sensor weather')
        fid=await asyncio.to_thread(db.record_forecast,result)
        await bus.publish({'event_type':'forecast','forecast_id':fid,'forecast':result,'operational_use':False})
        return result|{'forecast_id':fid}
