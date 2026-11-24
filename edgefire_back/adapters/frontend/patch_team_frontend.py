"""Add /remote to the original team frontend without modifying its existing pages."""
import argparse,shutil
from pathlib import Path

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--front',type=Path,required=True);a=p.parse_args();app=a.front.resolve()/'app';src=Path(__file__).parent
    m=(app/'CesiumMap.js').read_text(encoding='utf-8');anchor='    flyToSensor: (sensorId) => {'
    if m.count(anchor)!=1 or 'MOCK_SENSORS.forEach((sensor)' not in m:raise SystemExit('Expected original team CesiumMap.js, not AI branch.')
    m=m.replace('MOCK_SENSORS.forEach((sensor) => {','[].forEach((sensor) => {')
    m=m.replace(anchor,'''    updateLiveSensors: (items) => {
      const viewer=viewerRef.current,C=window.Cesium;if(!viewer||!C||viewer.isDestroyed())return;
      const colors=[C.Color.GRAY,C.Color.GREEN,C.Color.DODGERBLUE,C.Color.YELLOW,C.Color.ORANGE,C.Color.RED];
      for(const n of items){const id='live-'+n.node_id;if(!Number.isFinite(n.latitude)||!Number.isFinite(n.longitude)){viewer.entities.removeById(id);continue;}
        const pos=C.Cartesian3.fromDegrees(n.longitude,n.latitude,30),color=colors[n.assessment?.risk_level??0]||C.Color.GRAY,label=n.node_id+' · '+(n.source==='measured'?'실측':n.source==='demo'?'시연':'미확인');
        const entity=viewer.entities.getById(id);if(entity){entity.position=pos;entity.point.color=color;entity.label.text=label;}else viewer.entities.add({id,position:pos,point:{pixelSize:12,color,outlineColor:C.Color.WHITE,outlineWidth:2},label:{text:label,showBackground:true,pixelOffset:new C.Cartesian2(0,-20)}});
      }
    },
    flyToLiveSensor: (id) => {const v=viewerRef.current,e=v?.entities.getById('live-'+id);if(e)v.flyTo(e);},
'''+anchor)
    targets={app/'RemoteCesiumMap.js':m,app/'LiveTelemetry.tsx':(src/'LiveTelemetry.tsx').read_text(encoding='utf-8'),app/'remote'/'page.tsx':(src/'TeamRemotePage.tsx').read_text(encoding='utf-8'),app/'api'/'edgefire'/'[...path]'/'route.ts':(src/'team_proxy.ts').read_text(encoding='utf-8')}
    if any(x.exists() for x in targets):raise SystemExit('Destination exists; no file modified. Use clean team frontend copy.')
    for path,content in targets.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
    print('Added /remote. Original page, map and chart preserved. Set .env.local then run Next.js on port 3200.')
if __name__=='__main__':main()
