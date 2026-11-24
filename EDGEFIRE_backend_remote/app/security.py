import base64,hmac,hashlib,json,time,secrets
from fastapi import Header,HTTPException

def check(supplied,expected): return bool(supplied and expected and secrets.compare_digest(supplied,expected))
def signer(secret):
    def issue():
        raw=base64.urlsafe_b64encode(json.dumps({'exp':int(time.time())+90,'nonce':secrets.token_hex(8)},separators=(',',':')).encode()).decode().rstrip('=')
        return raw+'.'+hmac.new(secret.encode(),raw.encode(),hashlib.sha256).hexdigest()
    def verify(ticket):
        try:
            raw,sig=ticket.split('.',1)
            if not check(sig,hmac.new(secret.encode(),raw.encode(),hashlib.sha256).hexdigest()):return False
            return time.time()<=json.loads(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))['exp']
        except Exception:return False
    return issue,verify
