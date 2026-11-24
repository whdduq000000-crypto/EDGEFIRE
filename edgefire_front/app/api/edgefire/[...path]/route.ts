import {NextRequest} from 'next/server';
export const runtime='nodejs';export const dynamic='force-dynamic';
async function proxy(req:NextRequest,ctx:{params:Promise<{path:string[]}>}){
 const rel=(await ctx.params).path.join('/');
 if(!/^(telemetry|nodes|nodes\.geojson|ws-ticket|sync|jobs(?:\/JOB_[a-f0-9]{32}(?:\/(?:image|annotated|result|retry|location))?)?)$/.test(rel))return Response.json({detail:'Unknown path'},{status:404});
 const base=process.env.BACKEND_BASE_URL,key=process.env.LOCAL_API_TOKEN;if(!base||!key)return Response.json({detail:'Backend configuration missing'},{status:503});
 if(req.method==='POST'&&req.headers.get('origin')!==(process.env.FRONTEND_BASE_URL||'http://127.0.0.1:3200'))return Response.json({detail:'Origin denied'},{status:403});
 try{const headers:Record<string,string>={'X-API-Key':key};const content=req.headers.get('content-type');if(content)headers['Content-Type']=content;let body:Uint8Array|undefined;if(req.method==='POST'){const reader=req.body?.getReader();const chunks:Uint8Array[]=[];let total=0;if(reader)while(true){const x=await reader.read();if(x.done)break;total+=x.value.byteLength;if(total>11*1024*1024){await reader.cancel();return Response.json({detail:'Image too large'},{status:413});}chunks.push(x.value);}body=Buffer.concat(chunks);}
 const res=await fetch(base+'/api/v1/storage/'+rel+req.nextUrl.search,{method:req.method,headers,body:body as BodyInit|undefined,cache:'no-store',signal:AbortSignal.timeout(60000)});return new Response(res.body,{status:res.status,headers:{'Content-Type':res.headers.get('content-type')||'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});}catch{return Response.json({detail:'Backend unavailable'},{status:502});}
}
export const GET=proxy;export const POST=proxy;
