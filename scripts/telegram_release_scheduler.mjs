// Separate Cron Worker relay. No D1, subscribers or Telegram bot token here.
// Deploy/cron/keys must be deliberately authorized AFTER migration gates.
const ENDPOINT="https://outpost.com.ua/api/telegram/releases/dispatch";
const CLIENT="OutPOSt-Release-Scheduler/1.0 (+https://outpost.com.ua)";
const COUNTERS=['sent','retry','unknown','failed','blocked','cancelled'];
async function boundedReply(response){
  if(response.status!==200){await response.body?.cancel();throw Error('unavailable');}
  const reader=response.body?.getReader();
  if(!reader)throw Error('empty');
  try{
    const chunks=[];let size=0;
    while(true){
      const {done,value}=await reader.read();if(done)break;
      size+=value.byteLength;
      if(size>8192)throw Error('oversize');
      chunks.push(value);
    }
    const bytes=new Uint8Array(size);let offset=0;
    for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
    return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
}
export async function pumpConfirmedReleases(env, fetcher=fetch) {
  if(String(env?.OUTPOST_RELEASE_SCHEDULER_ENABLED||"")!=="1" || String(env?.OUTPOST_PREVIEW_ONLY||"")==="1")return {ok:true,skipped:true};
  if(typeof env.TELEGRAM_RELEASE_PUMP_KEY!=="string" || env.TELEGRAM_RELEASE_PUMP_KEY.length<32)return {ok:false,error:"scheduler_not_configured"};
  try {
    // workerd supports manual, not error. Never follow a redirect with a key;
    // never repeat an ambiguous request: the dispatcher owns claim/ack/retry.
    const r=await fetcher(ENDPOINT,{method:"POST",redirect:"manual",signal:AbortSignal.timeout(45000),headers:{"Content-Type":"application/json","Accept":"application/json","User-Agent":CLIENT,"X-OutPost-Release-Key":env.TELEGRAM_RELEASE_PUMP_KEY},body:JSON.stringify({action:"tick"})});
    const result=await boundedReply(r);
    if(result?.ok!==true || result.audience!=='subscribers' || result.sent===undefined || (result.cooldown!==undefined && typeof result.cooldown!=='boolean'))throw Error('invalid');
    const counts=Object.fromEntries(COUNTERS.map(name=>[name,result[name]===undefined?0:result[name]]));
    if(!COUNTERS.every(name=>Number.isInteger(counts[name]) && counts[name]>=0 && counts[name]<=3) || Object.values(counts).reduce((sum,value)=>sum+value,0)>3)throw Error('invalid');
    const attention=counts.unknown+counts.failed+counts.blocked>0;
    return {ok:!attention,...(attention?{error:'delivery_attention_required'}:{}),...counts,cooldown:result.cooldown===true};
  }catch{return {ok:false,error:"pump_unavailable"};}
}
export default {
  async scheduled(event,env,ctx){ctx.waitUntil(pumpConfirmedReleases(env).then(result=>{if(!result.ok)console.error(JSON.stringify({event:"release_scheduler_failed",...result}));}));},
  async fetch(){return new Response("Not found",{status:404});}
};
