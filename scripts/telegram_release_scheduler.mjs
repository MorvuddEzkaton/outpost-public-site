// Separate Cron Worker relay. No D1, subscribers or Telegram bot token here.
// Deploy/cron/keys must be deliberately authorized AFTER migration gates.
const ENDPOINT="https://outpost.com.ua/api/telegram/releases/dispatch";
export async function pumpConfirmedReleases(env) {
  if(String(env?.OUTPOST_RELEASE_SCHEDULER_ENABLED||"")!=="1" || String(env?.OUTPOST_PREVIEW_ONLY||"")==="1")return {ok:true,skipped:true};
  if(typeof env.TELEGRAM_RELEASE_PUMP_KEY!=="string" || env.TELEGRAM_RELEASE_PUMP_KEY.length<32)return {ok:false,error:"scheduler_not_configured"};
  try {
    const r=await fetch(ENDPOINT,{method:"POST",redirect:"error",signal:AbortSignal.timeout(45000),headers:{"Content-Type":"application/json","X-OutPost-Release-Key":env.TELEGRAM_RELEASE_PUMP_KEY},body:JSON.stringify({action:"tick"})});
    if(!r.ok)return {ok:false,error:"pump_unavailable"};
    const result=await r.json();
    return {ok:result?.ok===true,sent:Number(result?.sent||0),unknown:Number(result?.unknown||0),retry:Number(result?.retry||0)};
  }catch{return {ok:false,error:"pump_unavailable"};}
}
export default {
  async scheduled(event,env,ctx){ctx.waitUntil(pumpConfirmedReleases(env).then(result=>{if(!result.ok)console.error(JSON.stringify({event:"release_scheduler_failed",error:result.error}));}));},
  async fetch(){return new Response("Not found",{status:404});}
};
