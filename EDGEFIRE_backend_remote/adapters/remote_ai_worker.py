"""Run on AI PC. Reuse exact existing VisionPredictor; never copy weights to BE."""
import argparse, hashlib, json, os, sys, time, uuid, threading, logging
from pathlib import Path
import httpx
LOG=logging.getLogger('edgefire.worker')

def main():
    p=argparse.ArgumentParser(__doc__); p.add_argument('--ai-source',type=Path,required=True,help='Directory containing storage_worker.py (edgefire_AI)');p.add_argument('--model',type=Path,required=True);p.add_argument('--model-id',required=True);p.add_argument('--registry-root',type=Path,help='Existing AI local storage root for optional registered multimodels');p.add_argument('--once',action='store_true');args=p.parse_args()
    base=os.environ.get('EDGEFIRE_BACKEND_URL','').rstrip('/');key=os.environ.get('WORKER_API_TOKEN','')
    if not base or len(key)<24:raise SystemExit('Set EDGEFIRE_BACKEND_URL and WORKER_API_TOKEN')
    if not (args.ai_source/'storage_worker.py').is_file() or not args.model.is_file():raise SystemExit('Existing AI source/model path not found')
    sys.path.insert(0,str(args.ai_source.resolve()))
    from storage_worker import VisionPredictor
    infer=VisionPredictor(args.model,args.model_id)
    worker_id='WORKER_'+uuid.uuid4().hex; stop=threading.Event(); headers={'X-API-Key':key}
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    def request(method,path,**kw):
        with httpx.Client(base_url=base,headers=headers,timeout=httpx.Timeout(60,connect=5),trust_env=False) as c:
            r=c.request(method,path,**kw);r.raise_for_status();return r
    def heartbeat():
        while not stop.is_set():
            try:request('POST','/api/v1/worker/heartbeat',json={'worker_id':worker_id,'model_id':args.model_id})
            except httpx.HTTPError:LOG.warning('Heartbeat unavailable; reconnecting')
            stop.wait(10)
    threading.Thread(target=heartbeat,daemon=True).start()
    try:
        while not stop.is_set():
            try:j=request('POST','/api/v1/worker/claim',json={'worker_id':worker_id,'model_id':args.model_id}).json()['job']
            except httpx.HTTPError as e:LOG.warning('Claim failed (%s)',type(e).__name__);stop.wait(3);continue
            if not j:
                if args.once:break
                stop.wait(1);continue
            jid=j['id'];token=j['claim_token'];root=f'/api/v1/worker/jobs/{jid}';renew_stop=threading.Event();lost=threading.Event()
            def renew():
                while not renew_stop.wait(20):
                    try:request('POST',root+'/renew',json={'claim_token':token})
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code==409:lost.set();return
                    except httpx.HTTPError:LOG.warning('Lease heartbeat unavailable')
            thread=threading.Thread(target=renew,daemon=True);thread.start()
            try:
                raw=request('GET',root+'/input',headers={'X-Claim-Token':token}).content
                if hashlib.sha256(raw).hexdigest()!=j['sha256']:raise ValueError('Input SHA256 mismatch')
                if j['kind']=='vision':result,annotated=infer(raw)
                elif j['kind']=='assessment':
                    if not args.registry_root:raise ValueError('Optional model registry not configured on AI PC')
                    from multi_model_storage import infer_assessment
                    item=json.loads(raw);payload=dict(item['payload']);payload.pop('vision_job_id',None)
                    result,_=infer_assessment(args.registry_root,json.dumps(payload,ensure_ascii=False).encode());annotated=None
                    if item.get('vision'):result['vision']=item['vision']
                else:raise ValueError('Unknown job kind')
                if lost.is_set():raise RuntimeError('Job lease lost')
                files={'annotated':('annotated.jpg',annotated,'image/jpeg')} if annotated else None
                request('POST',root+'/complete',data={'claim_token':token,'result_json':json.dumps(result,ensure_ascii=False,allow_nan=False)},files=files)
                LOG.info('COMPLETED %s (%s)',jid,j['kind'])
            except Exception as e:
                LOG.error('Job %s failed: %s',jid,type(e).__name__)
                try:request('POST',root+'/fail',json={'claim_token':token,'error':str(e)[:1000] or type(e).__name__})
                except httpx.HTTPError:pass
            finally:renew_stop.set();thread.join(timeout=2)
            if args.once:break
    except KeyboardInterrupt:pass
    finally:
        stop.set()
        try:request('POST','/api/v1/worker/heartbeat',json={'worker_id':worker_id,'model_id':args.model_id,'state':'STOPPED'})
        except httpx.HTTPError:pass
if __name__=='__main__':main()
