"""Optional isolated performance test. Never run against live operational service."""
import os,time,uuid
from locust import HttpUser,task,between
class SensorLoad(HttpUser):
    wait_time=between(.05,.2)
    def on_start(self):
        self.boot='BOOT_'+uuid.uuid4().hex;self.seq=0
        self.key=os.environ['HARDWARE_API_TOKEN']
    @task
    def send(self):
        self.seq+=1
        self.client.post('/api/v1/telemetry/multimodal',headers={'X-API-Key':self.key},json={'node_id':'LOAD_'+self.boot[5:],'boot_id':self.boot,'sequence_no':self.seq,'timestamp':int(time.time()),'source':'demo','gas_unit':'unknown','raw_data':{'MQ2_adc':1000}})
