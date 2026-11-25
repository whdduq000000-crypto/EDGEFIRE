from test_backend import client,U,H,W,packet
from app.wbs import bearing,pelco
import time

def test_spatial_and_history(client):
    assert client.get('/api/v1/zones',headers=U).json()['features']==[]
    assert client.get('/api/v1/zones/missing',headers=U).status_code==404
    assert client.get('/api/v1/sensors/nearby?latitude=37&longitude=127',headers=U).status_code==503
    t=int(time.time())-10
    for i in range(3):assert client.post('/api/v1/telemetry',headers=H,json=packet(sequence_no=i,timestamp=t+i)).status_code==202
    assert len(client.get('/api/v1/telemetry/history?hours=1',headers=U).json())==3
    a=client.get('/api/v1/storage/sync?limit=2',headers=U).json();assert a['has_more'] and len(a['rows'])==2
    b=client.get('/api/v1/storage/sync',params=a['cursor'],headers=U).json();assert len(b['rows'])==1 and not b['has_more']
    assert len(client.get('/api/v1/sensors',headers=U).json())==1

def test_rate_and_ratio(client):
    t=int(time.time())-10
    client.post('/api/v1/telemetry',headers=H,json=packet(timestamp=t,gas_data={'CO':20,'H2':2}))
    a=client.post('/api/v1/telemetry',headers=H,json=packet(sequence_no=2,timestamp=t+5,gas_data={'CO':40,'H2':4})).json()['assessment']['ensemble']
    assert a['rates_per_second']=={'CO':4,'H2':.4};assert a['CO_H2_ratio']==10 and not a['operational_use']
    assert client.post('/api/v1/telemetry?queued=true',headers=H,json=packet(sequence_no=3)).status_code==503

def test_ptz_vision_dispatch(client):
    assert bearing(0,0,0,1)==90
    assert pelco(1,'right',16)=='FF010002100013'
    p=client.post('/api/v1/camera/ptz/command',headers=U,json={'action':'right'}).json();assert p['status']=='SIMULATED_NOT_SENT'
    assert client.post('/api/v1/camera/ptz/command',headers=U,json={'action':'auto'}).status_code==422
    v={'node_id':'N1','model_id':'fixture','timestamp':int(time.time()),'detections':[{'class_name':'smoke_fixture','score':.5,'bbox_xyxy':[0,0,10,20]}]}
    assert client.post('/api/v1/vision/metadata',headers=H,json=v).json()['operational_use'] is False
    assert len(client.get('/api/v1/vision/metadata',headers=U).json())==1
    e=client.post('/api/v1/telemetry',headers=H,json=packet()).json()['event_id']
    d=client.post('/api/v1/dispatch/simulate',headers=U,json={'channel':'119','event_id':e}).json();assert d['status']=='SIMULATED_NOT_SENT'
    assert client.get('/api/v1/dispatch/stats',headers=U).json()['counts'][0]['count']==1

def test_forecast_db_roundtrip(client):
    result={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'minutes':30},'geometry':{'type':'Polygon','coordinates':[[[127,37],[128,37],[128,38],[127,37]]]}}],'metadata':{'operational_use':False}}
    fid=client.app.state.db.record_forecast(result)
    assert client.get('/api/v1/prediction/diffusion',headers=U).json()['metadata']['forecast_id']==fid
    assert client.get('/api/v1/prediction/diffusion/'+fid+'/impact',headers=U).status_code==503
