"""Explicitly synthetic GIS fixture; never use for operational decisions."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.settings import Settings
from app.db import DB
from sqlalchemy import text

def main():
    db=DB(Settings());db.init()
    polygon={'type':'Polygon','coordinates':[[[127.75,37.87],[127.78,37.87],[127.78,37.90],[127.75,37.90],[127.75,37.87]]]}
    with db.engine.begin() as c:
        c.execute(text("INSERT INTO wui_zones(zone_id,name,geometry,source) VALUES('DEMO-WUI','Synthetic demo zone',:g,'demo') ON CONFLICT DO NOTHING"),{'g':json.dumps(polygon)})
        if db.postgres:c.execute(text("UPDATE wui_zones SET geom=ST_SetSRID(ST_GeomFromGeoJSON(geometry),4326) WHERE zone_id='DEMO-WUI'"))
        c.execute(text("INSERT INTO sensor_nodes(node_id,latitude,longitude,wui_zone_id,risk_level,kind,source,ts) VALUES('DEMO-CAM',37.88,127.76,'DEMO-WUI',0,'camera','demo',:ts) ON CONFLICT DO NOTHING"),{'ts':int(time.time())})
        c.execute(text("INSERT INTO wui_assets(asset_id,kind,name,latitude,longitude,households,source) VALUES('DEMO-VILLAGE','village','Synthetic village',37.881,127.761,3,'demo') ON CONFLICT DO NOTHING"))
    print('Synthetic zone/camera/village created. Not actual geography or household count.')
if __name__=='__main__':main()
