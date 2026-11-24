from test_backend import client,U,H,packet
import time

def test_registry_and_history(client):
    z={'zone_id':'zone1','name':'demo','source':'demo','coordinates':[[[127,37],[128,37],[128,38],[127,37]]]}
    assert client.post('/api/v1/zones',headers=U,json=z).status_code==200
    assert client.get('/api/v1/zones/zone1',headers=U).json()['properties']['zone_id']=='zone1'
    n={'node_id':'CAM1','kind':'camera','latitude':37,'longitude':127,'source':'demo','wui_zone_id':'zone1'}
    assert client.post('/api/v1/sensors/register',headers=H,json=n).status_code==401
    assert client.post('/api/v1/sensors/register',headers=U,json=n).status_code==200
    assert client.get('/api/v1/sensors/registry',headers=U).json()[0]['kind']=='camera'
    t=int(time.time())
    for i in (1,3):assert client.post('/api/v1/telemetry',headers=H,json=packet(sequence_no=i,timestamp=t)).status_code==202
    assert len(client.get('/api/v1/telemetry/gas-history?hours=1',headers=U).json())==2
    g=client.get('/api/v1/telemetry/gaps',headers=H,params={'node_id':'NODE_WUI_0102','boot_id':'boot-1','start':1,'end':4}).json()
    assert g['missing_ranges']==[[2,2],[4,4]] and g['missing_count']==2
    assert client.post('/api/v1/telemetry',headers=H,json=packet(sequence_no=2,timestamp=t)).status_code==202
    assert client.get('/api/v1/telemetry/gaps',headers=H,params={'node_id':'NODE_WUI_0102','boot_id':'boot-1','start':1,'end':3}).json()['missing_count']==0
    rows=client.get('/api/v1/storage/sync',headers=U).json()['rows'];assert [r['seq'] for r in rows]==[1,3,2]

def test_command_logs_and_limits(client):
    e=client.post('/api/v1/telemetry',headers=H,json=packet()).json()['event_id']
    assert client.post('/api/v1/camera/ptz/command',headers=U,json={'action':'stop'}).status_code==200
    assert client.get('/api/v1/camera/ptz/commands',headers=U).json()[0]['status']=='SIMULATED_NOT_SENT'
    assert client.post('/api/v1/dispatch/simulate',headers=U,json={'channel':'relay','event_id':e}).status_code==202
    assert client.get('/api/v1/dispatch/history',headers=U).json()[0]['status']=='SIMULATED_NOT_SENT'
    assert client.get('/api/v1/storage/node-cache/N1',headers=U).status_code==503
    assert client.post('/api/v1/prediction/diffusion/from-event/'+e,headers=U,params={'input_time':'2025-12-01T12:00'}).status_code==503
