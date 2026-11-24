import json,time,uuid,hashlib
from sqlalchemy import create_engine,text
from sqlalchemy.exc import IntegrityError
from .wbs import init_wbs, mirror_packet
class DB:
    def __init__(self, settings):
        self.postgres=settings.db_url.startswith('postgresql')
        settings.storage.mkdir(parents=True,exist_ok=True)
        self.engine=create_engine(settings.db_url,pool_pre_ping=True,connect_args={} if self.postgres else {'check_same_thread':False,'timeout':20})
    def init(self):
        with self.engine.begin() as c:
            if self.postgres: c.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
            c.execute(text('''CREATE TABLE IF NOT EXISTS telemetry (
            id VARCHAR(40) PRIMARY KEY, node_id VARCHAR(80) NOT NULL, boot_id VARCHAR(80) NOT NULL, seq BIGINT NOT NULL,
            ts BIGINT NOT NULL, created DOUBLE PRECISION NOT NULL, source VARCHAR(16) NOT NULL,
            latitude DOUBLE PRECISION, longitude DOUBLE PRECISION, payload TEXT NOT NULL, payload_hash VARCHAR(64) NOT NULL,
            assessment TEXT NOT NULL, UNIQUE(node_id,boot_id,seq))'''))
            c.execute(text('CREATE INDEX IF NOT EXISTS telemetry_node_ts ON telemetry(node_id,ts DESC,created DESC)'))
            c.execute(text('CREATE INDEX IF NOT EXISTS telemetry_created ON telemetry(created DESC)'))
            c.execute(text('''CREATE TABLE IF NOT EXISTS alerts (id VARCHAR(40) PRIMARY KEY, event_id VARCHAR(40) NOT NULL,
            created DOUBLE PRECISION NOT NULL, node_id VARCHAR(80) NOT NULL, kind VARCHAR(40) NOT NULL,
            payload TEXT NOT NULL, acknowledged DOUBLE PRECISION)'''))
            c.execute(text('CREATE INDEX IF NOT EXISTS alerts_created ON alerts(created DESC)'))
            c.execute(text('CREATE TABLE IF NOT EXISTS forecasts(id VARCHAR(40) PRIMARY KEY,created DOUBLE PRECISION NOT NULL,payload TEXT NOT NULL)'))
            if self.postgres:
                c.execute(text('ALTER TABLE telemetry ADD COLUMN IF NOT EXISTS geom geometry(Point,4326) GENERATED ALWAYS AS (CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN ST_SetSRID(ST_MakePoint(longitude,latitude),4326) END) STORED'))
                c.execute(text('CREATE INDEX IF NOT EXISTS telemetry_geom_gix ON telemetry USING GIST(geom)'))
                c.execute(text('CREATE INDEX IF NOT EXISTS telemetry_geography_gix ON telemetry USING GIST((geom::geography))'))
            init_wbs(self,c)
    @staticmethod
    def decode(r):
        v=dict(r); v['payload']=json.loads(v['payload']); v['result']=json.loads(v.pop('assessment')); v.pop('payload_hash',None); v.pop('geom',None); v.pop('rn',None); return v
    def save(self,payload,assessment):
        eid='EVT_'+uuid.uuid4().hex; canonical=json.dumps(payload,sort_keys=True,allow_nan=False,separators=(',',':')); digest=hashlib.sha256(canonical.encode()).hexdigest(); now=time.time()
        params=dict(id=eid,node_id=payload['node_id'],boot_id=payload['boot_id'],seq=payload['sequence_no'],ts=payload['timestamp'],created=now,source=payload['source'],latitude=payload.get('latitude'),longitude=payload.get('longitude'),payload=canonical,payload_hash=digest,assessment=json.dumps(assessment,allow_nan=False))
        with self.engine.begin() as c:
            if self.postgres:
                c.execute(text('SELECT pg_advisory_xact_lock(71242026)'))
                params['created']=c.execute(text('SELECT GREATEST(EXTRACT(EPOCH FROM clock_timestamp())::double precision, COALESCE(MAX(created),0)+0.000001) FROM telemetry')).scalar()
            else:
                c.execute(text('BEGIN IMMEDIATE'))
                params['created']=max(time.time(),(c.execute(text('SELECT MAX(created) FROM telemetry')).scalar() or 0)+0.000001)
            now=params['created']
            n=c.execute(text('''INSERT INTO telemetry(id,node_id,boot_id,seq,ts,created,source,latitude,longitude,payload,payload_hash,assessment)
              VALUES(:id,:node_id,:boot_id,:seq,:ts,:created,:source,:latitude,:longitude,:payload,:payload_hash,:assessment)
              ON CONFLICT(node_id,boot_id,seq) DO NOTHING'''),params).rowcount
            if not n:
                old=c.execute(text('SELECT * FROM telemetry WHERE node_id=:node_id AND boot_id=:boot_id AND seq=:seq'),params).mappings().one()
                if old['payload_hash']!=digest: raise ValueError('Sequence already used with a different payload')
                return self.decode(old),False
            mirror_packet(self,c,payload,eid,assessment)
            if assessment.get('risk_level') is not None and assessment['risk_level']>=3:
                c.execute(text('INSERT INTO alerts(id,event_id,created,node_id,kind,payload) VALUES(:id,:event_id,:created,:node_id,:kind,:payload)'),dict(id='ALT_'+uuid.uuid4().hex,event_id=eid,created=now,node_id=payload['node_id'],kind='prototype_gas_trigger',payload=json.dumps(assessment)))
        return self.get(eid),True
    def get(self,eid):
        with self.engine.connect() as c:
            row=c.execute(text('SELECT * FROM telemetry WHERE id=:id'),{'id':eid}).mappings().first()
            return self.decode(row) if row else None
    def history(self,node_id=None,limit=100):
        sql='SELECT * FROM telemetry '+('WHERE node_id=:node ' if node_id else '')+'ORDER BY ts DESC,created DESC LIMIT :limit'
        with self.engine.connect() as c: return [self.decode(r) for r in c.execute(text(sql),dict(node=node_id,limit=limit)).mappings()]
    def nodes(self):
        sql='''SELECT * FROM (SELECT t.*,ROW_NUMBER() OVER(PARTITION BY node_id ORDER BY ts DESC,created DESC) AS rn FROM telemetry t) x WHERE rn=1 ORDER BY node_id LIMIT 1000'''
        with self.engine.connect() as c: return [self.decode(r) for r in c.execute(text(sql)).mappings()]
    def geojson(self,west,south,east,north):
        # Latest sample per node, then bounds. PostGIS uses the actual geometry.
        if self.postgres:
            sql="""WITH latest AS (SELECT DISTINCT ON (node_id) * FROM telemetry ORDER BY node_id,ts DESC,created DESC) SELECT * FROM latest WHERE geom IS NOT NULL AND ST_Intersects(geom,ST_MakeEnvelope(:w,:s,:e,:n,4326)) ORDER BY node_id LIMIT 1000"""
            with self.engine.connect() as c:nodes=[self.decode(r) for r in c.execute(text(sql),dict(w=west,s=south,e=east,n=north)).mappings()]
        else:nodes=self.nodes()
        features=[]
        for n in nodes:
            lat,lon=n['latitude'],n['longitude']
            if lat is not None and west<=lon<=east and south<=lat<=north:
                features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[lon,lat]},'properties':{'node_id':n['node_id'],'source':n['source'],'timestamp':n['ts'],'risk_level':n['result'].get('risk_level')}})
        return {'type':'FeatureCollection','features':features}
    def mvt(self,z,x,y):
        if not self.postgres: raise NotImplementedError('PostGIS required')
        sql='''WITH bounds AS (SELECT ST_TileEnvelope(:z,:x,:y) AS b),
        latest AS (SELECT DISTINCT ON (node_id) node_id,source,ts,geom FROM telemetry ORDER BY node_id,ts DESC,created DESC),
        tile AS (SELECT node_id,source,ts,ST_AsMVTGeom(ST_Transform(geom,3857),b,4096,64,true) AS geom FROM latest,bounds WHERE geom IS NOT NULL AND ST_Intersects(geom,ST_Transform(b,4326))) SELECT ST_AsMVT(tile,'nodes',4096,'geom') FROM tile'''
        with self.engine.connect() as c: return bytes(c.execute(text(sql),dict(z=z,x=x,y=y)).scalar() or b'')
    def alerts(self,limit):
        with self.engine.connect() as c: return [dict(r)|{'payload':json.loads(r['payload'])} for r in c.execute(text('SELECT * FROM alerts ORDER BY created DESC LIMIT :limit'),{'limit':limit}).mappings()]
    def ack(self,aid):
        with self.engine.begin() as c: return c.execute(text('UPDATE alerts SET acknowledged=COALESCE(acknowledged,:now) WHERE id=:id'),{'now':time.time(),'id':aid}).rowcount==1

    def nearby(self,lat,lon,meters):
        if not self.postgres:raise NotImplementedError('PostGIS required')
        sql="""WITH latest AS (SELECT DISTINCT ON (node_id) node_id,source,ts,geom FROM telemetry ORDER BY node_id,ts DESC,created DESC) SELECT node_id,source,ts,ST_Distance(geom::geography,ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography) AS distance_m FROM latest WHERE geom IS NOT NULL AND ST_DWithin(geom::geography,ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography,:meters) ORDER BY distance_m LIMIT 1000"""
        with self.engine.connect() as c:return [dict(r) for r in c.execute(text(sql),dict(lat=lat,lon=lon,meters=meters)).mappings()]
    def record_forecast(self,result):
        ident='FC_'+uuid.uuid4().hex
        with self.engine.begin() as c:
            c.execute(text('INSERT INTO forecasts(id,created,payload) VALUES(:id,:now,:payload)'),dict(id=ident,now=time.time(),payload=json.dumps(result,allow_nan=False)))
            for i,f in enumerate(result.get('features',[])):
                g=f.get('geometry') or {}; minutes=(f.get('properties') or {}).get('minutes')
                if minutes not in (10,20,30) or g.get('type') not in ('Polygon','MultiPolygon'):continue
                params=dict(id=ident,no=i,m=minutes,g=json.dumps(g,allow_nan=False))
                c.execute(text('INSERT INTO forecast_polygons(forecast_id,feature_no,minutes,geometry) VALUES(:id,:no,:m,:g)'),params)
                if self.postgres:c.execute(text('UPDATE forecast_polygons SET geom=ST_SetSRID(ST_GeomFromGeoJSON(:g),4326) WHERE forecast_id=:id AND feature_no=:no'),params)
        return ident
