"""Optional read-only/forecast API on AI PC; uses existing AI source + local assets."""
import argparse,json,os,re,secrets,sys,time
from pathlib import Path
from fastapi import FastAPI,Header,HTTPException,Depends
from fastapi.responses import FileResponse
import uvicorn

def make_app(source,storage,weather,air,examples,training,token):
    sys.path.insert(0,str(Path(source).resolve()))
    storage,weather,air,examples,training=map(Path,(storage,weather,air,examples,training))
    def auth(x_api_key:str|None=Header(None)):
        if not x_api_key or not secrets.compare_digest(x_api_key,token):raise HTTPException(401,'AI auxiliary key required')
    app=FastAPI(title='EDGE-FIRE AI auxiliary bridge',dependencies=[Depends(auth)])
    @app.get('/models')
    def models():
        from multi_model_storage import model_status
        try:return model_status(storage)
        except (ValueError,OSError):raise HTTPException(503,'Model registry unavailable or invalid')
    @app.get('/model-examples')
    def model_examples():
        from multi_model_storage import reference_examples
        try:return reference_examples(storage)
        except (ValueError,OSError):raise HTTPException(503,'Model reference assets unavailable')
    @app.post('/validate-assessment')
    def validate_assessment(payload:dict):
        from multi_model_storage import validate_request
        try:validate_request(payload);return {'ok':True}
        except (ValueError,TypeError):raise HTTPException(422,'Invalid assessment payload')
    @app.get('/forecast/regions')
    def forecast_regions():
        from fire_forecast.service import regions
        return regions(weather)
    @app.get('/forecast')
    def forecast():
        p=weather/'spread_estimate.geojson'
        if not p.is_file():raise HTTPException(404,'Historical forecast unavailable')
        return json.loads(p.read_text(encoding='utf-8'))
    @app.post('/forecast')
    def calculate(payload:dict):
        from fire_forecast.service import calculate as run
        try:return run(weather,payload)
        except (ValueError,TypeError) as e:raise HTTPException(422,str(e))
        except OSError:raise HTTPException(503,'Weather assets unavailable')
    @app.get('/air-quality/stations')
    def stations():
        from air_quality_service import stations as run
        return run(air)
    @app.get('/air-quality/series')
    def series(station:str,end:str|None=None):
        from air_quality_service import series as run
        try:return run(air,station,end)
        except ValueError as e:raise HTTPException(422,str(e))
        except OSError:raise HTTPException(503,'Air quality assets unavailable')
    @app.get('/vision-examples')
    def vision_examples():
        path=examples/'manifest.json'
        if not path.is_file():return {'status':'PREPARING','cases':[]}
        data=json.loads(path.read_text(encoding='utf-8')); data['cases']=[{k:v for k,v in item.items() if k not in ('annotations','detections')} for item in data['cases']];return dict(data,status='READY')
    @app.get('/vision-examples/{case}/{variant}')
    def vision_example_image(case:str,variant:str):
        if not re.fullmatch(r'[a-f0-9]{16,64}',case) or variant not in ('original','ground-truth','prediction'):raise HTTPException(404,'Unknown image')
        manifest=vision_examples()
        if not any(item['id']==case for item in manifest['cases']):raise HTTPException(404,'Unknown example')
        p=examples/case/{'original':'original.jpg','ground-truth':'ground_truth.jpg','prediction':'prediction.jpg'}[variant]
        if not p.is_file():raise HTTPException(404,'Example image unavailable')
        return FileResponse(p,media_type='image/jpeg')
    @app.get('/training-status')
    def training_status():
        if not training.is_file():return {'available':False}
        try:
            d=json.loads(training.read_text(encoding='utf-8'));age=max(0,time.time()-training.stat().st_mtime);phase=d.get('phase','unknown')
            return {'available':True,'phase':'unknown' if age>180 and phase=='training' else phase,'stale':age>180,'worker_alive':None,'epoch':d.get('epoch_index',-1)+1 if 'epoch_index' in d else d.get('epoch'),'epochs':d.get('config',{}).get('epochs',d.get('epochs')),'epoch_cursor':d.get('epoch_cursor'),'train_images_per_epoch':d.get('train_images_per_epoch'),'gpu_name':d.get('gpu_name'),'updated_local':d.get('updated_local'),'status_source':'local_status_file_not_process_verification'}
        except (OSError,ValueError,TypeError):return {'available':False}
    return app

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--ai-source',required=True);p.add_argument('--storage-root',required=True);p.add_argument('--weather-root',required=True);p.add_argument('--air-root',required=True);p.add_argument('--examples-root',required=True);p.add_argument('--training-status',required=True);p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8301);a=p.parse_args()
    key=os.environ.get('AI_AUX_TOKEN','')
    if len(key)<24:raise SystemExit('Set AI_AUX_TOKEN')
    if not (Path(a.ai_source)/'fire_forecast'/'service.py').is_file():raise SystemExit('Wrong --ai-source path')
    uvicorn.run(make_app(a.ai_source,a.storage_root,a.weather_root,a.air_root,a.examples_root,a.training_status,key),host=a.host,port=a.port)
if __name__=='__main__':main()
