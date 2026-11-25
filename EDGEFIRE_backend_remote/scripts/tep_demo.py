"""Synthetic TEP scenario over HTTP. Never initiate fire or real dispatch."""
import argparse,time,os,uuid,httpx
p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8200');a=p.parse_args();b=a.base.rstrip('/');h={'X-API-Key':os.environ['HARDWARE_API_TOKEN']};u={'X-API-Key':os.environ['LOCAL_API_TOKEN']};boot=uuid.uuid4().hex
with httpx.Client(timeout=20) as c:
    for seq,co,h2 in [(1,10,2),(2,30,4),(3,55,8)]:
        r=c.post(b+'/api/v1/telemetry/multimodal',headers=h,json={'node_id':'TEP-DEMO','boot_id':boot,'sequence_no':seq,'timestamp':int(time.time()),'source':'demo','gas_unit':'ppm','gas_data':{'CO':co,'H2':h2},'latitude':37.885,'longitude':127.766});r.raise_for_status();event=r.json();print(event);time.sleep(1.1)
    for path,payload in [('/api/v1/camera/ptz/command',{'action':'auto','camera':{'latitude':37.88,'longitude':127.76},'target':{'latitude':37.885,'longitude':127.766}}),('/api/v1/dispatch/simulate',{'channel':'119','event_id':event['event_id']})]:
        r=c.post(b+path,headers=u,json=payload);print(path,r.status_code,r.text);r.raise_for_status()
    print('Synthetic flow only; forecast and real AI/hardware still need separate test.')
