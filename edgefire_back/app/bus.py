import asyncio,json,logging
LOG=logging.getLogger('edgefire.bus')
class Bus:
    def __init__(self,url): self.url=url; self.redis=None; self.task=None; self.clients=set(); self.connected=False
    async def start(self):
        if self.url:
            import redis.asyncio as redis
            self.redis=redis.from_url(self.url,decode_responses=True,socket_connect_timeout=2,socket_timeout=3)
            self.task=asyncio.create_task(self.listen())
    async def close(self):
        if self.task:
            self.task.cancel(); await asyncio.gather(self.task,return_exceptions=True)
        if self.redis: await self.redis.aclose()
    def dispatch(self,event):
        for q in list(self.clients):
            if q.full():
                try:q.get_nowait()
                except asyncio.QueueEmpty:pass
            q.put_nowait(event)
    async def listen(self):
        while True:
            try:
                async with self.redis.pubsub() as ps:
                    await ps.subscribe('edgefire.events'); self.connected=True
                    while True:
                        item=await ps.get_message(ignore_subscribe_messages=True,timeout=1)
                        if item: self.dispatch(json.loads(item['data']))
                        else: await asyncio.sleep(.02)
            except asyncio.CancelledError: raise
            except Exception as e:
                self.connected=False; LOG.warning('Redis unavailable, retrying: %s',type(e).__name__); await asyncio.sleep(2)
    async def publish(self,event):
        if self.redis and self.connected:
            try:
                listeners=await self.redis.publish('edgefire.events',json.dumps(event,allow_nan=False))
                if listeners: return
            except Exception: self.connected=False
        # Single-process degraded mode; REST history remains authoritative.
        self.dispatch(event)

    async def cache_node(self,event):
        if not self.redis:return
        # Only the most recent observation wins; late replay must not replace it.
        key='node:status:'+event['node_id']
        script="""local t=redis.call('HGET',KEYS[1],'timestamp'); if not t or tonumber(t)<=tonumber(ARGV[1]) then redis.call('HSET',KEYS[1],'timestamp',ARGV[1],'payload',ARGV[2]); redis.call('EXPIRE',KEYS[1],60); return 1 end; return 0"""
        try:await self.redis.eval(script,1,key,event['timestamp'],json.dumps(event,allow_nan=False))
        except Exception:LOG.warning('Redis node cache unavailable')
