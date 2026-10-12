// Safe health diagnostics: never expose credentials or call external APIs/D1.
import {handleTelegramHealth} from '../site/_telegram-support.js';
import worker from '../site/_worker.js';
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
 check(calls===0,'Unexpected outbound health request');console.log('Release mode health: PASS; read-only, credential-free, mutually exclusive engines and blocked preview');
}finally{globalThis.fetch=original;}
