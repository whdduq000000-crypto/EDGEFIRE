"""Apply on a COPY of AI branch edgefire_front. Refuses mismatched source anchors."""
import argparse,re,shutil
from pathlib import Path

def replace_once(s,old,new):
    if s.count(old)!=1:raise ValueError('Source anchor not unique: '+old[:100])
    return s.replace(old,new,1)

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--front',type=Path,required=True);a=p.parse_args();root=a.front.resolve();app=root/'app';page=app/'page.tsx';cesium=app/'CesiumMap.js';proxy=app/'api'/'edgefire'/'[...path]'/'route.ts';src=Path(__file__).parent
    if not all(x.is_file() for x in [page,cesium,proxy,app/'GasChart.tsx']):raise SystemExit('Use AI integration branch edgefire_front, not original main.')
    s=page.read_text(encoding='utf-8');m=cesium.read_text(encoding='utf-8');r=proxy.read_text(encoding='utf-8')
    if 'import LiveTelemetry' in s:raise SystemExit('Already patched. Use fresh copy for reapplication.')
    if 'ImageComparison' not in s or 'storageJob' not in s:raise SystemExit('Not the supported AI-integrated main page.')
    s=replace_once(s,'import GasChart from "./GasChart";','import LiveTelemetry, { type Packet, type Review } from "./LiveTelemetry";')
    s=replace_once(s,'import { RISK_LEVELS, type RiskLevel } from "./riskLevels";','')
    start=s.index('  // 센서별 위험 단계');end=s.index('  const [storageJob',start)
    s=s[:start]+'''  const [liveNodes,setLiveNodes] = useState<Packet[]>([]);
  const [lastReview,setLastReview] = useState<Review|null>(null);
  const [linkPhoto,setLinkPhoto] = useState(false);
  const riskNames = ['판정 대기','정상','관심','주의','경계','심각'];
  function acceptPackets(items:Packet[]) {setLiveNodes(items);mapRef.current?.updateLiveSensors(items);}
  function selectLive(id:string){setSelectedSensorId(id);mapRef.current?.flyToLiveSensor(id);}
  const liveNode=liveNodes.find(n=>n.node_id===selectedSensorId);
  useEffect(()=>{const t=setInterval(()=>mapRef.current?.updateLiveSensors(liveNodes),2000);return()=>clearInterval(t);},[liveNodes]);

'''+s[end:]
    s=s.replace('● 시스템 상태: 정상','● 시스템 상태: 관제 대기')
    s=s.replace(' · 센서 시연',' · 원격 센서 관제')
    start=s.index('          <ul className="text-sm space-y-2 text-gray-300">');end=s.index('          </ul>',start)+len('          </ul>')
    s=s[:start]+'''          <ul className="text-sm space-y-2 text-gray-300 max-h-[40%] overflow-auto">
            {!liveNodes.length && <li className="text-xs text-gray-400">실제 수신 노드 없음</li>}
            {liveNodes.map(n=><li key={n.node_id}><button type="button" onClick={()=>selectLive(n.node_id)} className="w-full text-left p-2 bg-gray-700 rounded">
              {n.node_id} · {n.source==='measured'?'실측':n.source==='demo'?'시연':'미확인'}<br/>
              <span className="text-xs">{riskNames[n.assessment?.risk_level??0]} {n.assessment?.risk_level?'· 연구 규칙':''}</span></button></li>)}
            <li><button type="button" onClick={()=>handleSensorClick('CAM-PTZ-01')} className="p-2 bg-gray-700 w-full text-left rounded">사진 AI 분석 결과</button></li>
          </ul>
          {lastReview && <p className="text-xs text-yellow-300">영상 검토 결과 수신 · {lastReview.result?.detections?.length??0}개 검출 · 화재 확증 아님</p>}
'''+s[end:]
    s=replace_once(s,'<span>■ 과거 대기측정 농도 · 2026년</span>','<span>■ 원격 센서 / 과거 관측</span>')
    s=replace_once(s,'<span className="text-xs text-yellow-400">관측소 자료</span>','<span className="text-xs text-yellow-400">출처 구분</span>')
    s=replace_once(s,'<GasChart selectedSensorId={selectedSensorId} />','<LiveTelemetry selectedSensorId={selectedSensorId} onNode={selectLive} onPackets={acceptPackets} onReview={setLastReview} />')
    s=replace_once(s,"const body = new FormData();body.append('image',file);body.append('region_id',region);","const body = new FormData();body.append('image',file);body.append('region_id',region);if(linkPhoto && liveNode){body.append('node_id',liveNode.node_id);body.append('telemetry_event_id',liveNode.event_id);}")
    anchor='            <div className="flex gap-2 text-[10px] pt-1">'
    s=replace_once(s,anchor,'''            <label className="text-[10px]"><input type="checkbox" checked={linkPhoto} disabled={!liveNode} onChange={e=>setLinkPhoto(e.target.checked)}/> 선택 센서 이벤트와 수동 연결 (GPS/자동촬영 아님)</label>
'''+anchor)
    # Mark existing comparison panel as explicitly illustrative; replace camera label if fixed.
    s=s.replace('🔎 1차·2차 감지 비교 보기','🔎 1차·2차 감지 비교 예시')
    # Map: remove mock markers on integrated main, add actual packet markers without fallback coordinates.
    anchor='    flyToSensor: (sensorId) => {'
    m=replace_once(m,anchor,'''    updateLiveSensors: (items) => {
      const viewer=viewerRef.current, C=window.Cesium;
      if(!viewer||!C||viewer.isDestroyed())return;
      const colors=[C.Color.GRAY,C.Color.GREEN,C.Color.DODGERBLUE,C.Color.YELLOW,C.Color.ORANGE,C.Color.RED];
      for(const item of items){
        const id='live-'+item.node_id;
        if(!Number.isFinite(item.latitude)||!Number.isFinite(item.longitude)){viewer.entities.removeById(id);continue;}
        const color=colors[item.assessment?.risk_level??0]||C.Color.GRAY;
        const pos=C.Cartesian3.fromDegrees(item.longitude,item.latitude,30);
        let entity=viewer.entities.getById(id);
        const label=item.node_id+' · '+(item.source==='measured'?'실측':item.source==='demo'?'시연':'미확인');
        if(!entity){entity=viewer.entities.add({id,name:label,position:pos,point:{pixelSize:12,color,outlineColor:C.Color.WHITE,outlineWidth:2},label:{text:label,font:'12px sans-serif',showBackground:true,pixelOffset:new C.Cartesian2(0,-20)}});}
        else{entity.position=pos;entity.point.color=color;entity.label.text=label;}
      }
    },
    flyToLiveSensor: (sensorId) => {
      const viewer=viewerRef.current,C=window.Cesium;
      const entity=viewer?.entities.getById('live-'+sensorId);
      if(entity&&C)viewer.flyTo(entity);
    },
'''+anchor)
    m=m.replace('MOCK_SENSORS.forEach((sensor) => {','(props.enableForecast ? [] : MOCK_SENSORS).forEach((sensor) => {')
    # Never show default mock popup on integrated dashboard.
    m=m.replace('const sensor = MOCK_SENSORS.find((s) => s.id === sensorId) || MOCK_SENSORS[0];','const sensor = props.enableForecast ? null : MOCK_SENSORS.find((s) => s.id === sensorId) || MOCK_SENSORS[0];')
    # Existing exact allowlist; append four new paths, not arbitrary proxy.
    r=replace_once(r,'^(config|training-status|','^(telemetry|nodes|nodes\\.geojson|ws-ticket|alerts(?:\\/ALT_[a-f0-9]{32}\\/ack)?|config|training-status|')
    backups=root.parent/(root.name+'_remote_patch_backup');backups.mkdir(exist_ok=False)
    for f,content in [(page,s),(cesium,m),(proxy,r)]:
        relative=f.relative_to(root);backup=backups/relative;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,backup);f.write_text(content,encoding='utf-8')
    shutil.copy2(src/'LiveTelemetry.tsx',app/'LiveTelemetry.tsx')
    print('Patched AI-integrated frontend. Backups:',backups)
    print('Set .env.local (see docs/REMOTE_SETUP.md) then npm ci / npm run build / npm run dev -- --hostname 127.0.0.1 --port 3200')
if __name__=='__main__':main()
