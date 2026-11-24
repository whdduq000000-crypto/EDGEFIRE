"""Synthetic API pipeline: no real sensor, camera, model, or external dispatch."""
from test_backend import client,U,H,W,packet,upload,claim,jpeg
import json,time
from unittest.mock import patch
import httpx

def test_end_to_end_synthetic(client):
    now=int(time.time())-5
    for i,co in enumerate((10,30,55),1):
        r=client.post('/api/v1/telemetry/multimodal',headers=H,json=packet(sequence_no=i,timestamp=now+i,gas_data={'CO':co,'H2':5}));assert r.status_code==202
    e=r.json()['event_id'];assert r.json()['assessment']['stage']==1
    assert r.json()['assessment']['ensemble']['rates_per_second']['CO']==25
    ptz=client.post('/api/v1/camera/ptz/command',headers=U,json={'action':'auto','camera':{'latitude':37.4,'longitude':127},'target':{'latitude':37.5,'longitude':127}}).json()
    assert ptz['status']=='SIMULATED_NOT_SENT'
    j=upload(client,telemetry_event_id=e).json();job=claim(client)
    r=client.post('/api/v1/worker/jobs/'+j['id']+'/complete',headers=W,data={'claim_token':job['claim_token'],'result_json':json.dumps({'model_id':'fixture','model_sha256':'0'*64,'detections':[{'class_name':'fixture','score':.7}]})},files={'annotated':('test.jpg',jpeg(),'image/jpeg')});assert r.status_code==200
    assert r.json()['result']['operational_use'] is False
    result={'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'Polygon','coordinates':[[[127,37],[128,37],[128,38],[127,37]]]},'properties':{'minutes':m}} for m in (10,20,30)],'metadata':{'operational_use':False}}
    # Record fixture directly, since remote AI weather assets are not available.
    fid=client.app.state.db.record_forecast(result)
    assert len(client.get('/api/v1/prediction/diffusion',headers=U,params={'forecast_id':fid}).json()['features'])==3
    for channel in ('119','forest','relay','cbs','alimtalk'):
        assert client.post('/api/v1/dispatch/simulate',headers=U,json={'channel':channel,'event_id':e}).json()['status']=='SIMULATED_NOT_SENT'
    assert len(client.get('/api/v1/dispatch/history',headers=U).json())==5
