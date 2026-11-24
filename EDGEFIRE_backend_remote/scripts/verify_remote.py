"""Read-only remote health check; optional explicit synthetic POST."""
import argparse,os,time,uuid,json,httpx
p=argparse.ArgumentParser();p.add_argument('--demo',action='store_true');a=p.parse_args()
base=os.environ.get('EDGEFIRE_BACKEND_URL','').rstrip('/')
if not base:raise SystemExit('Set EDGEFIRE_BACKEND_URL')
with httpx.Client(base_url=base,timeout=10,trust_env=False) as c:
 r=c.get('/health');r.raise_for_status();print('Health:',r.json())
 if a.demo:
  key=os.environ.get('HARDWARE_API_TOKEN','');assert key,'Set HARDWARE_API_TOKEN'
  r=c.post('/api/v1/telemetry/multimodal',headers={'X-API-Key':key},json={'node_id':'DEMO_VERIFY','boot_id':'BOOT_'+uuid.uuid4().hex,'sequence_no':1,'timestamp':int(time.time()),'source':'demo','gas_unit':'ppm','gas_data':{'CO':45}});r.raise_for_status();print('Synthetic POST:',r.json())
 if os.environ.get('LOCAL_API_TOKEN'):
  r=c.get('/api/v1/storage/telemetry?limit=3',headers={'X-API-Key':os.environ['LOCAL_API_TOKEN']});r.raise_for_status();print('History count:',len(r.json()))
