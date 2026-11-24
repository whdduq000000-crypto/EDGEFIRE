"""Optional MQTT JSON bridge. Uses existing HTTP sender contract; requires paho-mqtt."""
import os, json, argparse, sys, subprocess
from pathlib import Path

def main():
    import paho.mqtt.client as mqtt
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--port',type=int,default=8883);p.add_argument('--topic',default='edgefire/+/telemetry');p.add_argument('--ca',required=True);p.add_argument('--backend',required=True);a=p.parse_args()
    import httpx
    key=os.environ['HARDWARE_API_TOKEN']; spool=Path('mqtt_pending.jsonl')
    def connect(c,u,f,rc,properties):
        if rc==0:c.subscribe(a.topic,qos=1)
    def message(c,u,m):
        try:
            packet=json.loads(m.payload); assert isinstance(packet,dict)
            r=httpx.post(a.backend.rstrip('/')+'/api/v1/telemetry/multimodal',json=packet,headers={'X-API-Key':key},timeout=10);r.raise_for_status()
        except Exception:
            with spool.open('ab') as f:f.write(m.payload.replace(b'\n',b' ')+b'\n')
    c=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2);c.username_pw_set(os.environ['MQTT_USERNAME'],os.environ['MQTT_PASSWORD']);c.tls_set(ca_certs=a.ca);c.on_connect=connect;c.on_message=message;c.connect(a.host,a.port);c.loop_forever()
if __name__=='__main__':main()
