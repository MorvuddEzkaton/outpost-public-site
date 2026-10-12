// Offline only: no production requests, real credentials or subscriber records.
import worker from '../site/_worker.js';
const check=(condition,message)=>{if(!condition) throw new Error(message);};
const originalFetch=globalThis.fetch;
let outbound=[],databaseWrites=0,scheduled=0,checks=0;
globalThis.fetch=async (target,init)=>{
  outbound.push({url:String(target),init});
  return new Response('mock upstream', {status:202});
};
const poisonedPreviewEnv={
  TELEGRAM_BOT_TOKEN:'synthetic-not-a-token',
  TELEGRAM_WEBHOOK_SECRET:'synthetic-webhook',
  TELEGRAM_ADMIN_CHAT_ID:'synthetic-admin',
  TELEGRAM_SETUP_KEY:'synthetic-setup',
  TELEGRAM_PUBLIC_ENABLED:'1',
  ANALYTICS_DB:{prepare(){databaseWrites++;throw new Error('Preview touched analytics DB');}},
  ASSETS:{async fetch(request){
    const p=new URL(request.url).pathname;
    const type=p.endsWith('.exe')?'application/octet-stream':p==='/sitemap.xml'?'application/xml':'text/html; charset=utf-8';
    return new Response(p.endsWith('.exe')?'mock installer':'<!doctype html><title>Fixture</title>',{status:200,headers:{'Content-Type':type}});
  }}
};
const ctx={waitUntil(){scheduled++;}};
try {
  const previews=['https://outpost-public-preview.pages.dev','https://staging.outpost-web.pages.dev','http://localhost:8788','https://outpost.com.ua.example.invalid','http://outpost.com.ua','https://outpost.com.ua:444'];
  for(const origin of previews){
    for(const pathname of ['/api/public-question','/api/telegram/setup','/api/telegram/webhook','/api/telegram/unknown']){
      for(const method of ['GET','POST']){
        const r=await worker.fetch(new Request(origin+pathname,{method,body:method==='POST'?'demo request':undefined}),poisonedPreviewEnv,ctx);
        check(r.status===403,origin+pathname+' must be disabled');
        check((await r.json()).error==='preview_integration_disabled','Preview must not pretend a message was delivered');
        check(r.headers.get('Cache-Control')==='no-store','Disabled integration response must not cache');
        checks++;
      }
    }
    const health=await worker.fetch(new Request(origin+'/api/telegram/health'),poisonedPreviewEnv,ctx);
    const payload=await health.json();
    check(health.status===200 && payload.enabled===false && payload.integrations_disabled===true,'Preview health must explicitly disable Telegram');
    check(!('bot' in payload),'Preview health must not advertise a production bot');
    checks++;
    for(const pathname of ['/','/download','/download.html','/sitemap.xml','/downloads/OutPOSt-Setup-v0.24.39.exe']){
      const r=await worker.fetch(new Request(origin+pathname),poisonedPreviewEnv,ctx);
      check(r.status===200,'Preview must retain static pages/installers');
      if(!pathname.endsWith('.exe'))check(r.headers.get('X-Robots-Tag')==='noindex, nofollow','Preview HTML/XML must remain noindex');
      checks++;
    }
  }
  // Explicit fail-closed flag also protects a mistakenly attached canonical host.
  for(const pathname of ['/api/public-question','/api/telegram/setup','/api/telegram/webhook']){
    const r=await worker.fetch(new Request('https://outpost.com.ua'+pathname,{method:'POST',body:'demo'}),{...poisonedPreviewEnv,OUTPOST_PREVIEW_ONLY:'1'},ctx);
    check(r.status===403,'Explicit preview-only flag must block production integrations');checks++;
  }
  for(const pathname of ['/','/download','/downloads/OutPOSt-Setup-v0.24.39.exe']){
    const r=await worker.fetch(new Request('https://outpost.com.ua'+pathname),{...poisonedPreviewEnv,OUTPOST_PREVIEW_ONLY:'1'},ctx);
    check(r.status===200,'Preview-only static paths remain usable');checks++;
  }
  check(outbound.length===0 && databaseWrites===0 && scheduled===0,'Preview leaked outbound requests or analytics jobs');checks++;

  // Canonical production contract is checked against an in-memory upstream only.
  for(const origin of ['https://outpost.com.ua','https://www.outpost.com.ua']){
    const r=await worker.fetch(new Request(origin+'/api/public-question?fixture=1',{method:'POST',headers:{'Content-Type':'text/plain','Authorization':'do-not-forward','Cookie':'do-not-forward'},body:'synthetic'}),{},ctx);
    check(r.status===202,'Canonical production proxy must preserve upstream status');
    const last=outbound.at(-1);
    check(last.url==='https://cabinet.outpost.com.ua/api/public-question?fixture=1','Production target changed');
    check(last.init.headers.get('origin')==='https://outpost.com.ua','Canonical origin contract changed');
    check(!last.init.headers.has('authorization')&&!last.init.headers.has('cookie'),'Proxy must not forward privileged headers');checks++;
  }
  const health=await worker.fetch(new Request('https://outpost.com.ua/api/telegram/health'),poisonedPreviewEnv,ctx);
  check(health.status===200 && (await health.json()).enabled===true,'Canonical production health contract changed');checks++;
  console.log(JSON.stringify({checks,pass:true,preview_outbound_requests:0,preview_database_writes:0,production_requests:'mocked only'}));
} finally {globalThis.fetch=originalFetch;}
