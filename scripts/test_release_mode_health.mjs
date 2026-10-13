// Safe health diagnostics: never expose credentials or call external APIs/D1.
import {handleTelegramHealth} from '../site/_telegram-support.js';
import worker from '../site/_worker.js';
import fs from 'node:fs';
const check=(ok,message)=>{if(!ok)throw Error(message);};
const env={TELEGRAM_BOT_TOKEN:'demo-not-a-real-token',TELEGRAM_WEBHOOK_SECRET:'demo-not-a-real-webhook',TELEGRAM_ADMIN_CHAT_ID:'demo-only',TELEGRAM_PUBLIC_ENABLED:'1'};
let calls=0;const original=globalThis.fetch;globalThis.fetch=async()=>{calls++;throw Error('Health must not call external APIs');};
try{
 for(const mode of ['', '0', '1', 'true']){
  const payload=await (handleTelegramHealth(new Request('https://outpost.com.ua/api/telegram/health'),{...env,TELEGRAM_CONFIRMED_RELEASES_ENABLED:mode})).json();
  check(payload.release_mode_schema===1&&payload.enabled===true,'Health schema/enabled changed');
  check(payload.confirmed_releases_enabled===(mode==='1')&&payload.legacy_release_notifications_enabled===(mode!=='1'),'Release engines must be mutually exclusive');
  check(!JSON.stringify(payload).includes('demo-'),'No credentials or chat IDs in health');
 }
 const disabled=await handleTelegramHealth(new Request('https://outpost.com.ua/api/telegram/health'),{...env,TELEGRAM_PUBLIC_ENABLED:'0',TELEGRAM_CONFIRMED_RELEASES_ENABLED:'1'}).json();
 check(!disabled.enabled&&!disabled.confirmed_releases_enabled&&!disabled.legacy_release_notifications_enabled,'Disabled health cannot claim safe activation');
 const preview=await worker.fetch(new Request('https://example.pages.dev/api/telegram/health'),{...env,TELEGRAM_CONFIRMED_RELEASES_ENABLED:'1'},{waitUntil(){throw Error('Health cannot enqueue work');}});
 const p=await preview.json();check(p.release_mode_schema===1&&p.integrations_disabled&&!p.confirmed_releases_enabled&&!p.legacy_release_notifications_enabled,'Preview must disable both engines');
 const config=JSON.parse(fs.readFileSync(new URL('../wrangler.jsonc',import.meta.url),'utf8'));
 check(JSON.stringify(config.vars)===JSON.stringify({TELEGRAM_CONFIRMED_RELEASES_ENABLED:'1'}),'Production flag must come from reviewed configuration, not just project metadata');
 check(config.env.preview.vars&&Object.keys(config.env.preview.vars).length===0,'Preview vars must explicitly prevent production inheritance');
 const productionEnv={...env,...config.vars};
 const productionHealth=await (await worker.fetch(new Request('https://outpost.com.ua/api/telegram/health'),productionEnv,{waitUntil(){throw Error('Health cannot enqueue work');}})).json();
 check(productionHealth.confirmed_releases_enabled&&!productionHealth.legacy_release_notifications_enabled,'Declared production flag must reach real worker health');
 let assets=0;const blockedDB={prepare(){throw Error('Mode probe must not access SQL');},withSession(){throw Error('Mode probe must not access SQL');}};
 const declaredEnv={...productionEnv,ANALYTICS_DB:blockedDB,ASSETS:{fetch(){assets++;return new Response('SYNTHETIC ONLY');}}};
 for(const path of ['/', '/download', '/download.html']){
  const response=await worker.fetch(new Request('https://outpost.com.ua'+path),declaredEnv,{waitUntil(){throw Error('Declared mode must suppress legacy background sender');}});
  check(response.status===200,'Synthetic asset path failed');
 }
 for(const action of ['status','tick','confirm']){
  const response=await worker.fetch(new Request('https://outpost.com.ua/api/telegram/releases/dispatch',{method:'POST',headers:{'Content-Type':'application/json','x-outpost-release-key':'SYNTHETIC-NOT-AN-OPERATIONAL-KEY'},body:JSON.stringify({action})}),declaredEnv,{waitUntil(){throw Error('No key must not enqueue work');}});
  check(response.status===401,'Configured mode without operational keys must reject before SQL or delivery');
 }
 const previewEnv={...env,...config.env.preview.vars};
 for(const origin of ['https://example.pages.dev','https://outpost.com.ua']){
  const response=await worker.fetch(new Request(origin+'/api/telegram/health'),origin.includes('pages.dev')?previewEnv:{...productionEnv,OUTPOST_PREVIEW_ONLY:'1'},{waitUntil(){throw Error('Preview health cannot enqueue work');}});
  const payload=await response.json();check(payload.integrations_disabled&&!payload.enabled&&!payload.confirmed_releases_enabled&&!payload.legacy_release_notifications_enabled,'Preview environment cannot inherit operational mode');
 }
 check(assets===3,'Declared-mode asset requests missing');
 check(calls===0,'Unexpected outbound health request');console.log('Release mode health: PASS; read-only, credential-free, mutually exclusive engines and blocked preview');
}finally{globalThis.fetch=original;}
