import sys,os
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));os.chdir(root)
from app.settings import env
import uvicorn
if __name__=='__main__':uvicorn.run('main:app',host=env('BIND_HOST','127.0.0.1'),port=int(env('PORT','8200')),workers=1)
