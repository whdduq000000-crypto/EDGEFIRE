import io,json,time,hashlib,os
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.main import create_app
from app.settings import Settings
UI='u'*32;HW='h'*32;WORK='w'*32;ORIGIN='http://127.0.0.1:3200'
U={'X-API-Key':UI};H={'X-API-Key':HW};W={'X-API-Key':WORK}
@pytest.fixture
def client(tmp_path,monkeypatch):
    for k,v in {'DATABASE_URL':'sqlite:///'+str(tmp_path/'db.sqlite'),'REDIS_URL':'','STORAGE_ROOT':str(tmp_path/'files'),'LOCAL_API_TOKEN':UI,'HARDWARE_API_TOKEN':HW,'WORKER_API_TOKEN':WORK,'WS_SIGNING_KEY':'s'*32,'ALLOWED_ORIGINS':ORIGIN,'AI_AUX_URL':'','RISK_RULES_JSON':'{"demo":{"gas_data.CO":[10,20,40,80]}}'}.items():monkeypatch.setenv(k,v)
    app=create_app(Settings())
    with TestClient(app) as c:yield c

def packet(**kw):return {'node_id':'NODE_WUI_0102','sequence_no':1,'boot_id':'boot-1','timestamp':1795510000,'source':'demo','gas_unit':'ppm','gas_data':{'CO':45,'H2':None,'VOC':None},'latitude':37.5,'longitude':127.0}|kw

def jpeg():
    stream=io.BytesIO();Image.new('RGB',(32,24),(200,30,30)).save(stream,format='JPEG');return stream.getvalue()

def upload(client,**fields):return client.post('/api/v1/storage/jobs',headers=U,files={'image':('input.jpg',jpeg(),'image/jpeg')},data={'region_id':'seoul'}|fields)

def claim(client):return client.post('/api/v1/worker/claim',headers=W,json={'worker_id':'worker-01','model_id':'test-fixture'}).json()['job']

def test_health_auth_docs(client):
    assert client.get('/').json()['status']=='ONLINE';assert client.get('/health').json()['database']=='sqlite-test-mode';assert client.get('/docs').status_code==200;assert client.get('/openapi.json').status_code==200
    assert client.get('/api/v1/storage/telemetry').status_code==401
    assert client.post('/api/v1/telemetry/multimodal',headers=U,json=packet()).status_code==401
    assert client.get('/api/v1/storage/models',headers=U).json()['status']=='TRAINING_OR_NOT_REGISTERED'

def test_sensor_store_duplicate_and_conflict(client):
    r=client.post('/api/v1/telemetry/multimodal',headers=H,json=packet());assert r.status_code==202,r.text;v=r.json();assert v['assessment']['risk_level']==4;assert v['assessment']['stage']==1
    r=client.post('/api/v1/telemetry/multimodal',headers=H,json=packet());assert r.json()['status']=='DUPLICATE';assert r.json()['event_id']==v['event_id']
    assert client.post('/api/v1/telemetry/multimodal',headers=H,json=packet(gas_data={'CO':50})).status_code==409
    rows=client.get('/api/v1/storage/telemetry',headers=U).json();assert len(rows)==1;assert rows[0]['payload']['gas_data']['CO']==45
    alerts=client.get('/api/v1/storage/alerts',headers=U).json();assert len(alerts)==1
    assert client.post('/api/v1/storage/alerts/'+alerts[0]['id']+'/ack',headers=U).status_code==200
    geo=client.get('/api/v1/gis/nodes.geojson',headers=U).json();assert geo['features'][0]['geometry']['coordinates']==[127,37.5]
    assert client.get('/api/v1/gis/tiles/3/2/3.mvt',headers=U).status_code==503

def test_raw_and_validation(client):
    p=packet(sequence_no=2,source='measured',gas_data=None,gas_unit='unknown',raw_data={'MQ2_adc':12000},thermal={'max_c':32.5})
    r=client.post('/api/v1/telemetry',headers=H,json=p);assert r.status_code==202;assert r.json()['assessment']['risk_level'] is None
    assert client.post('/api/v1/telemetry',headers=H,json=packet(latitude=37,longitude=None)).status_code==422
    assert client.post('/api/v1/telemetry',headers=H,json=packet(gas_data=None,environment=None)).status_code==422
    assert client.post('/api/v1/telemetry',headers=H,json=packet(gas_data={'CO':'NaN'})).status_code==422

def test_websocket_and_remote_sensor(client):
    ticket=client.get('/api/v1/storage/ws-ticket',headers=U).json()['ticket']
    with client.websocket_connect('/api/v1/ws/hazard',headers={'Origin':ORIGIN},subprotocols=['edgefire.v1','ticket.'+ticket]) as ws:
        assert ws.accepted_subprotocol=='edgefire.v1'
        r=client.post('/api/v1/telemetry/multimodal',headers=H,json=packet());msg=ws.receive_json();assert msg['event_id']==r.json()['event_id'];assert msg['gas_data']['CO']==45
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/api/v1/ws/hazard',headers={'Origin':'http://wrong-origin'},subprotocols=['edgefire.v1','ticket.'+ticket]):pass

def test_remote_vision_flow(client):
    e=client.post('/api/v1/telemetry',headers=H,json=packet()).json()['event_id']
    r=upload(client,telemetry_event_id=e);assert r.status_code==202,r.text;j=r.json();jid=j['id'];assert j['status']=='PENDING';assert 'claim_token' not in j
    assert client.post('/api/v1/worker/claim',headers=U,json={'worker_id':'worker-01','model_id':'test-fixture'}).status_code==401
    job=claim(client);assert job['id']==jid;token=job['claim_token'];url='/api/v1/worker/jobs/'+jid
    assert client.get(url+'/input',headers=W|{'X-Claim-Token':'x'*32}).status_code==409
    raw=client.get(url+'/input',headers=W|{'X-Claim-Token':token}).content;assert hashlib.sha256(raw).hexdigest()==job['sha256']
    assert client.post(url+'/renew',headers=W,json={'claim_token':token}).status_code==200
    result={'model_id':'test-fixture','model_sha256':'0'*64,'detections':[{'class_name':'test_fixture_not_real_AI','score':0.5}],'operational_use':True}
    r=client.post(url+'/complete',headers=W,data={'claim_token':token,'result_json':json.dumps(result)},files={'annotated':('annotated.jpg',jpeg(),'image/jpeg')});assert r.status_code==200,r.text
    assert r.json()['status']=='COMPLETED';assert r.json()['result']['operational_use'] is False;assert r.json()['result']['input_sha256']==job['sha256']
    assert client.get('/api/v1/storage/jobs/'+jid+'/annotated',headers=U).content==jpeg()
    assert client.get('/api/v1/storage/jobs/'+jid+'/result',headers=U).json()['model_id']=='test-fixture'
    assert client.get('/api/v1/storage/jobs?region=seoul',headers=U).json()[0]['id']==jid
    assert client.post('/api/v1/storage/jobs/'+jid+'/retry',headers=U).status_code==409
    assert client.get('/api/v1/storage/config',headers=U).json()['worker_available'] is True

def test_retry_and_lease_fencing(client):
    j=upload(client).json();a=claim(client);jid=j['id'];path='/api/v1/worker/jobs/'+jid
    assert client.post(path+'/fail',headers=W,json={'claim_token':a['claim_token'],'error':'fixture failed'}).status_code==200
    assert client.post('/api/v1/storage/jobs/'+jid+'/retry',headers=U).status_code==202
    b=claim(client);assert b['claim_token']!=a['claim_token'];assert client.post(path+'/renew',headers=W,json={'claim_token':a['claim_token']}).status_code==409
    from sqlalchemy import text
    with client.app.state.db.engine.begin() as c:c.execute(text('UPDATE jobs SET lease_until=0 WHERE id=:id'),{'id':jid})
    d=claim(client);assert d['id']==jid and d['claim_token']!=b['claim_token'];assert client.post(path+'/fail',headers=W,json={'claim_token':b['claim_token'],'error':'late'}).status_code==409

def test_invalid_upload_region_and_optional_assets(client):
    assert client.post('/api/v1/storage/jobs',headers=U,files={'image':('x.jpg',b'not image','image/jpeg')}).status_code==422
    assert client.post('/api/v1/storage/jobs',headers=U,files={'image':('x.jpg',jpeg(),'image/jpeg')},data={'region_id':'bad'}).status_code==422
    assert client.get('/api/v1/storage/forecast/regions',headers=U).status_code==503
    assert client.post('/api/v1/storage/assessments',headers=U,json={}).status_code==409
    assert client.get('/api/v1/storage/vision-examples',headers=U).json()['status']=='PREPARING'
