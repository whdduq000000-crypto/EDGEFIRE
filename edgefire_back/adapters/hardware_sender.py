"""Run on Pi/gateway. JSON lines in, authenticated HTTP + durable local retry queue out.
No pin/ADC assumptions. Hardware team must supply their actual sensor reader."""
import argparse,json,os,sqlite3,sys,time,uuid,threading,math,logging
from pathlib import Path
import urllib.request,urllib.error
from contextlib import contextmanager
LOG=logging.getLogger('edgefire.hw')

def main():
    p=argparse.ArgumentParser(__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--demo',action='store_true');g.add_argument('--stdin',action='store_true');g.add_argument('--file',type=Path);g.add_argument('--serial',help='Optional gateway serial device, e.g. /dev/ttyUSB0');g.add_argument('--drain',action='store_true',help='Resend previously queued samples only');p.add_argument('--baud',type=int,default=115200);p.add_argument('--node-id',default='NODE_WUI_0102');p.add_argument('--interval',type=float,default=2);p.add_argument('--count',type=int,default=5);p.add_argument('--spool',type=Path,default=Path('edgefire_spool.sqlite'));p.add_argument('--drain-timeout',type=float,default=25);args=p.parse_args()
    url=os.environ.get('EDGEFIRE_BACKEND_URL','').rstrip('/');key=os.environ.get('HARDWARE_API_TOKEN','')
    if not url or len(key)<24:raise SystemExit('Set EDGEFIRE_BACKEND_URL and HARDWARE_API_TOKEN')
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    args.spool.parent.mkdir(parents=True,exist_ok=True);lock=threading.Lock();stop=threading.Event();boot='BOOT_'+uuid.uuid4().hex;seq=0
    @contextmanager
    def connect():
        c=sqlite3.connect(args.spool,timeout=10)
        try:
            with c:yield c
        finally:c.close()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with connect() as c:c.execute('CREATE TABLE IF NOT EXISTS spool(id INTEGER PRIMARY KEY AUTOINCREMENT,payload TEXT NOT NULL,state TEXT NOT NULL DEFAULT \'PENDING\',error TEXT)')
    def enqueue(data):
        nonlocal seq
        if not isinstance(data,dict):raise ValueError('Expected JSON object')
        seq+=1;data=dict(data);data.setdefault('node_id',args.node_id);data.setdefault('sequence_no',seq);data.setdefault('boot_id',boot);data.setdefault('timestamp',int(time.time()));data['source']='demo' if args.demo else data.get('source','measured');data.setdefault('gas_unit','unknown')
        with lock,connect() as c:c.execute('INSERT INTO spool(payload) VALUES(?)',(json.dumps(data,allow_nan=False,ensure_ascii=False),))
    def send_loop():
        delay=1
        while not stop.is_set():
            with lock,connect() as c:row=c.execute("SELECT id,payload FROM spool WHERE state='PENDING' ORDER BY id LIMIT 1").fetchone()
            if not row:stop.wait(.25);continue
            rid,payload=row
            req=urllib.request.Request(url+'/api/v1/telemetry/multimodal',data=payload.encode(),headers={'Content-Type':'application/json','X-API-Key':key},method='POST')
            try:
                with opener.open(req,timeout=10) as r:body=json.loads(r.read());LOG.info('%s %s',body.get('status'),body.get('event_id'))
                with lock,connect() as c:c.execute('DELETE FROM spool WHERE id=?',(rid,));delay=1
            except urllib.error.HTTPError as e:
                if e.code in (400,409,413,422):
                    with lock,connect() as c:c.execute("UPDATE spool SET state='REJECTED',error=? WHERE id=?",(str(e.code)+' '+e.read(1000).decode(errors='replace'),rid));LOG.error('Rejected packet %s; retained in spool',rid)
                else:LOG.warning('HTTP %s; retain packet and retry',e.code);stop.wait(delay);delay=min(15,delay*2)
            except (OSError,ValueError) as e:LOG.warning('Network unavailable; retaining data (%s)',type(e).__name__);stop.wait(delay);delay=min(15,delay*2)
    thread=threading.Thread(target=send_loop,daemon=True);thread.start()
    try:
        if args.demo:
            for i in range(args.count):enqueue({'gas_data':{'CO':float(5+15*i),'H2':None,'VOC':None},'gas_unit':'ppm','environment':{'temperature':24.0,'humidity_percent':50.0}});time.sleep(args.interval)
        elif args.file or args.stdin or args.serial:
            if args.serial:
                import serial
                stream=serial.Serial(args.serial,args.baud,timeout=1)
            elif args.file:stream=args.file.open(encoding='utf-8')
            else:stream=sys.stdin
            try:
                if args.serial:
                    while True:
                        line=stream.readline()
                        if not line:continue
                        try:enqueue(json.loads(line))
                        except (ValueError,TypeError) as e:LOG.error('Invalid JSON line: %s',e)
                else:
                    for line in stream:
                        if not line.strip():continue
                        try:enqueue(json.loads(line))
                        except (ValueError,TypeError) as e:LOG.error('Invalid JSON line: %s',e)
            finally:
                if stream is not sys.stdin:stream.close()
        deadline=time.time()+args.drain_timeout
        while time.time()<deadline:
            with lock,connect() as c:n=c.execute("SELECT COUNT(*) FROM spool WHERE state='PENDING'").fetchone()[0]
            if not n:break
            time.sleep(.25)
    except KeyboardInterrupt:pass
    finally:
        stop.set();thread.join(timeout=12)
        with lock,connect() as c:print('Remaining packets:',c.execute('SELECT state,COUNT(*) FROM spool GROUP BY state').fetchall())
if __name__=='__main__':main()
