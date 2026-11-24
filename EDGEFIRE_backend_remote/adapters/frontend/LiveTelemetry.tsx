"use client";
import {useEffect,useMemo,useRef,useState} from 'react';
import {ResponsiveContainer,LineChart,Line,XAxis,YAxis,Tooltip,CartesianGrid,Legend} from 'recharts';
import GasChart from './GasChart';
export type Packet={node_id:string;sequence_no:number;timestamp:number;source?:string;gas_unit?:string;gas_data?:Record<string,number|null>;raw_data?:Record<string,number>;environment?:Record<string,number>;thermal?:Record<string,number|boolean>;latitude?:number;longitude?:number;assessment?:{risk_level:number|null;status:string;stage?:number|null};event_id:string;received_at?:number;boot_id?:string};
export type Review={event_type:string;job_id:string;telemetry_event_id?:string;node_id?:string;stage?:number;result?:{detections?:unknown[];model_id?:string}};
const labels=['판정 대기','정상','관심','주의','경계','심각'];
const colors=['#94a3b8','#22c55e','#60a5fa','#eab308','#f97316','#ef4444'];
function normalize(row:any):Packet{return {...row.payload,event_id:row.id,assessment:row.result,received_at:row.created};}
function merge(a:Packet[],b:Packet[]){const m=new Map<string,Packet>();[...a,...b].forEach(p=>m.set(p.event_id,p));return [...m.values()].sort((x,y)=>x.timestamp-y.timestamp||(x.received_at||0)-(y.received_at||0)).slice(-1000);}
function fmt(v:number){return new Date(v*1000).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul'});}
export default function LiveTelemetry({selectedSensorId,onNode,onPackets,onReview,allowHistorical=true}:{selectedSensorId:string;onNode:(id:string)=>void;onPackets:(items:Packet[])=>void;onReview:(review:Review)=>void;allowHistorical?:boolean}){
 const [packets,setPackets]=useState<Packet[]>([]),[connected,setConnected]=useState(false),[historical,setHistorical]=useState(false),[err,setErr]=useState(''),[clock,setClock]=useState(Date.now());
 const callbacks=useRef({onPackets,onReview});callbacks.current={onPackets,onReview};
 useEffect(()=>{let active=true;let timer:ReturnType<typeof setTimeout>|undefined;let ws:WebSocket|undefined;let failures=0;
  async function history(){try{const response=await fetch('/api/edgefire/telemetry?limit=1000',{cache:'no-store'});if(!response.ok)throw Error('센서 이력 조회 실패');const rows=await response.json();if(active)setPackets(old=>merge(old,rows.map(normalize)));}catch(e){if(active)setErr(String(e));}}
  async function connect(){if(!active)return;try{const response=await fetch('/api/edgefire/ws-ticket',{cache:'no-store'});if(!response.ok)throw Error('WS 인증 실패');const {ticket}=await response.json();if(!active)return;const target=process.env.NEXT_PUBLIC_EDGEFIRE_WS_URL;if(!target)throw Error('NEXT_PUBLIC_EDGEFIRE_WS_URL 미설정');ws=new WebSocket(target,['edgefire.v1','ticket.'+ticket]);ws.onopen=()=>{if(!active)return;failures=0;setConnected(true);setErr('');void history();};ws.onmessage=e=>{try{const data=JSON.parse(e.data);if(data.event_type==='telemetry')setPackets(old=>merge(old,[data]));if(data.event_type==='vision_review')callbacks.current.onReview(data);}catch{/* heartbeat or invalid message ignored */}};ws.onerror=()=>{if(active)setErr('WebSocket 연결 오류');};ws.onclose=()=>{if(!active)return;setConnected(false);timer=setTimeout(connect,Math.min(10000,1000*2**Math.min(failures++,4)));};}catch(e){if(!active)return;setConnected(false);setErr(String(e));timer=setTimeout(connect,Math.min(10000,1000*2**Math.min(failures++,4)));}}
  void history();void connect();const poll=setInterval(history,10000);const tick=setInterval(()=>setClock(Date.now()),5000);return()=>{active=false;if(timer)clearTimeout(timer);clearInterval(poll);clearInterval(tick);ws?.close();};
 },[]);
 const latest=useMemo(()=>{const nodes=new Map<string,Packet>();for(const p of packets)nodes.set(p.node_id,p);return [...nodes.values()];},[packets]);
 useEffect(()=>{callbacks.current.onPackets(latest);},[latest]);
 const current=latest.find(p=>p.node_id===selectedSensorId)||latest[0];const rows=packets.filter(p=>p.node_id===current?.node_id&&p.source===current?.source&&p.gas_unit===current?.gas_unit).slice(-40);
 const gasKeys=['CO','H2','VOC'].filter(k=>rows.some(p=>typeof p.gas_data?.[k]==='number'));const rawKeys=[...new Set(rows.flatMap(p=>Object.keys(p.raw_data||{})))].slice(0,6);
 const chart=rows.map(p=>({time:fmt(p.timestamp),...Object.fromEntries(gasKeys.map(k=>[k,p.gas_data?.[k]??null])),...Object.fromEntries(rawKeys.map(k=>['raw:'+k,p.raw_data?.[k]??null]))}));
 const risk=current?.assessment?.risk_level??0;const stale=current?clock/1000-(current.received_at||current.timestamp)>30:true;
 return <div className="h-full min-h-0 flex flex-col gap-1 text-xs overflow-auto">
 <div className="flex justify-between items-center gap-1">{allowHistorical&&<button className="bg-gray-700 rounded px-1" onClick={()=>setHistorical(v=>!v)}>{historical?'실시간 센서 보기':'과거 대기자료 보기'}</button>}<span className={connected?'text-green-300':'text-yellow-300'}>{connected?'WS 연결':'재연결 중'}</span></div>
 {historical?<GasChart selectedSensorId={selectedSensorId}/>:<>
 {err&&<p role="status" className="text-yellow-300">{err}</p>}
 <select aria-label="실시간 센서" className="bg-gray-900 rounded p-1" value={current?.node_id||''} onChange={e=>onNode(e.target.value)}>{!latest.length&&<option value="">수신 대기</option>}{latest.map(n=><option key={n.node_id} value={n.node_id}>{n.node_id} ({n.source==='measured'?'실측':n.source==='demo'?'시연':'출처 미확인'})</option>)}</select>
 {current?<><div className="flex flex-wrap gap-1"><span style={{color:colors[risk]}}>{risk?`${risk}단계 ${labels[risk]} · 연구 규칙`:'판정 대기'}</span><span className="text-gray-300">{stale?'최신 수신 지연':'최근 수신'} {fmt(current.received_at||current.timestamp)}</span></div>
 <p>측정 시각 {fmt(current.timestamp)} · {current.source==='measured'?'실측 입력':current.source==='demo'?'시연 입력':'출처 미확인'}</p>
 <p>{gasKeys.map(k=>`${k}: ${current.gas_data?.[k]??'—'} ${current.gas_unit==='ppm'?'ppm':current.gas_unit==='index'?'index':'(단위 미확인)'}`).join(' · ')}</p>
 <p>{Object.entries(current.raw_data||{}).map(([k,v])=>`${k}: ${v}`).join(' · ')}</p>
 <p>{Object.entries(current.environment||{}).map(([k,v])=>`${k}: ${v}`).join(' · ')}</p>
 {current.thermal&&<p>열화상 최고 {current.thermal.max_c??'—'} °C · 평균 {current.thermal.mean_c??'—'} °C</p>}
 {chart.length>0&&(gasKeys.length>0||rawKeys.length>0)&&<div className="flex-1 min-h-[100px]"><ResponsiveContainer width="100%" height="100%"><LineChart data={chart}><CartesianGrid strokeDasharray="3 3" stroke="#374151"/><XAxis dataKey="time" minTickGap={24}/><YAxis yAxisId="gas" width={35}/>{rawKeys.length>0&&<YAxis yAxisId="raw" orientation="right" width={42}/>}<Tooltip contentStyle={{background:'#111827'}}/><Legend/>{gasKeys.map((k,i)=><Line yAxisId="gas" key={k} dataKey={k} stroke={colors[i+2]} dot={false} isAnimationActive={false}/>)}{rawKeys.map((k,i)=><Line yAxisId="raw" key={k} dataKey={'raw:'+k} stroke={colors[(i+1)%colors.length]} dot={false} isAnimationActive={false}/>)}</LineChart></ResponsiveContainer></div>}
 </>:<p className="text-gray-400">센서 패킷 수신 대기 중. 예시값을 표시하지 않습니다.</p>}
 </>}
 </div>;
}
