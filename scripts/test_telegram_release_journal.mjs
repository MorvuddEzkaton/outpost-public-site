// Real in-memory SQLite, real production journal SQL, synthetic HTTP only.
import { DatabaseSync } from 'node:sqlite';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { confirmRelease, pumpReleaseJournal, releaseJournalStatus, handleReleaseDispatch,
  verifyConfirmedReleaseLive, sendJournalMessage, validateRelease, deliveryPolicy, handleReleasePilot } from '../site/_telegram-release-journal.js';
import {pilotCredentialRole} from '../site/_telegram-pilot-credentials.js';
import { maybeNotifyTelegramRelease, handleTelegramWebhook } from '../site/_telegram-support.js';
import worker from '../site/_worker.js';
import { pumpConfirmedReleases } from './telegram_release_scheduler.mjs';
const originalFetch=globalThis.fetch;
globalThis.fetch=async()=>{throw Error('Unexpected real network request forbidden in offline test');};
const cases=[];let assertions=0;
const check=(value,message)=>{assertions++;assert(value,message);};
const same=(a,b)=>{assertions++;assert.deepEqual(a,b);};
const scenario=async(name,fn)=>{await fn();cases.push(name);};
class Statement {
  constructor(db,sql,values=[]){this.db=db;this.sql=sql;this.values=values;}
  bind(...values){return new Statement(this.db,this.sql,values);}
  run(){this.db.queries++;if(this.db.failAck && this.sql.includes('SET state=?') && this.values[0]==='sent')throw Error('Synthetic lost D1 ack write');if(this.db.failUnsubscribe && this.sql.includes('DELETE FROM telegram_update_subscribers'))throw Error('Synthetic unsubscribe storage failure');const r=this.db.sql.prepare(this.sql).run(...this.values);return {success:true,meta:{changes:Number(r.changes)}};}
  async all(){this.db.queries++;return {success:true,results:this.db.sql.prepare(this.sql).all(...this.values)};}
  async first(){this.db.queries++;return this.db.sql.prepare(this.sql).get(...this.values)||null;}
}
class D1 {
  constructor(){this.sql=new DatabaseSync(':memory:');this.queries=0;this.sql.exec(`CREATE TABLE telegram_update_subscribers(chat_id TEXT PRIMARY KEY,subscribed_at TEXT,updated_at TEXT,last_notified_version TEXT)`);}
  prepare(sql){return new Statement(this,sql);}
  withSession(mode){same(mode,'first-primary');return this;}
  async batch(statements){this.sql.exec('BEGIN');try{const rows=[];for(const s of statements)rows.push(s.run());this.sql.exec('COMMIT');return rows;}catch(e){this.sql.exec('ROLLBACK');throw e;}}
  row(chat='101'){return this.sql.prepare('SELECT * FROM telegram_update_subscribers WHERE chat_id=?').get(chat);}
  delivery(product='outpost',chat='101'){return this.sql.prepare('SELECT * FROM telegram_release_deliveries WHERE product=? AND chat_id=? ORDER BY version DESC').get(product,chat);}
  subscribe(chat='101',cursor={outpost:'0.25.0',accounting:'1.0.2'},at=0){this.sql.prepare('INSERT OR REPLACE INTO telegram_update_subscribers VALUES(?,?,?,?)').run(chat,new Date(at).toISOString(),new Date(at).toISOString(),typeof cursor==='string'?cursor:JSON.stringify(cursor));}
}
function fixture(){
  const db=new D1();let now=100000;const versions={outpost:'0.25.1',accounting:'1.0.3'};
  const sent=[];const fetched=[];let response=()=>new Response(JSON.stringify({ok:true,result:{message_id:sent.length+1}}));
  const bytes=Buffer.alloc(2048,7);bytes[0]=77;bytes[1]=90;
  const hash=createHash('sha256').update(bytes).digest('hex').toUpperCase();
  const html=()=>Object.entries(versions).map(([p,v])=>`<a href="/downloads/OutPOSt-${p==='accounting'?'Accounting-':''}Setup-v${v}.exe">Demo</a>`).join('');
  const env={ANALYTICS_DB:db,TELEGRAM_BOT_TOKEN:'synthetic-not-a-bot-token',TELEGRAM_CONFIRMED_RELEASES_ENABLED:'1',TELEGRAM_PUBLIC_ENABLED:'1',
    TELEGRAM_RELEASE_CONFIRM_KEY:'demo-confirm-key-'.padEnd(40,'x'),TELEGRAM_RELEASE_PUMP_KEY:'demo-pump-key-'.padEnd(40,'y'),
    TELEGRAM_WEBHOOK_SECRET:'demo-webhook',TELEGRAM_RELEASE_DELIVERY_MODE:'subscribers',ASSETS:{fetch:async()=>new Response(html())}};
  const release=product=>validateRelease({product,version:versions[product],sha256:hash,size_bytes:bytes.length,source_sha:'a'.repeat(40)});
  const live=async(url,init)=>{
    fetched.push(String(url));same(init.redirect,'manual');check(String(url).startsWith('https://outpost.com.ua/'),'Verifier escaped canonical origin');
    const path=new URL(url).pathname;
    if(path==='/download.html')return new Response(html());
    if(path.endsWith('.sha256.txt'))return new Response(hash+' *'+path.split('/').at(-1).replace('.sha256.txt','.exe'));
    return new Response(bytes);
  };
  const sender=async(env,payload)=>sendJournalMessage(env,payload,async(url,init)=>{check(String(url).startsWith('https://api.telegram.org/bot'),'Unexpected synthetic sender target');sent.push(JSON.parse(init.body));return response();});
  const deps={now:()=>now,verifyLive:(env,r)=>verifyConfirmedReleaseLive(env,r,live),send:sender};
  return {db,env,versions,sent,fetched,release,deps,advance(ms){now+=ms;},setResponse(fn){response=fn;},confirm(p='outpost'){return confirmRelease(env,release(p),deps);},pump(){return pumpReleaseJournal(env,deps);}};
}
function pilotFixture(){
 const f=fixture();delete f.env.TELEGRAM_RELEASE_DELIVERY_MODE;f.env.TELEGRAM_ADMIN_CHAT_ID='101';
 const confirmKey='C'.repeat(43),pumpKey='P'.repeat(43);
 const verifiers={schema:1,expires_at:new Date(200000).toISOString(),confirm_sha256:createHash('sha256').update(confirmKey).digest('hex'),pump_sha256:createHash('sha256').update(pumpKey).digest('hex')};
 const call=(body,key=pumpKey,url='https://outpost.com.ua/api/telegram/releases/pilot')=>handleReleasePilot(new Request(url,{method:'POST',headers:{'x-outpost-release-key':key},body:JSON.stringify(body)}),f.env,{...f.deps,verifiers});
 const {installer,...release}=f.release('outpost');
 return {...f,call,confirmKey,pumpKey,verifiers,body:{...release,action:'confirm',expected_admin_chat_id:'101'}};
}
try{
 await scenario('public pilot verifier is not a credential; keys expire and roles are distinct',async()=>{
  const f=pilotFixture();same(await pilotCredentialRole(f.confirmKey,f.verifiers,100000),'confirm');same(await pilotCredentialRole(f.pumpKey,f.verifiers,100000),'pump');
  for(const key of [f.verifiers.confirm_sha256,f.verifiers.pump_sha256,'wrong',''])same(await pilotCredentialRole(key,f.verifiers,100000),null);
  same(await pilotCredentialRole(f.confirmKey,f.verifiers,200000),null);
  same(await pilotCredentialRole(f.confirmKey,{...f.verifiers,pump_sha256:f.verifiers.confirm_sha256},100000),null);
 });
 await scenario('pilot capability route rejects wrong role, recipient selectors and assertions before SQL',async()=>{
  const f=pilotFixture();same((await f.call(f.body)).status,401);same((await f.call({action:'status',expected_admin_chat_id:'101'},f.confirmKey)).status,401);
  for(const assertion of [undefined,'202',101])same((await f.call({...f.body,expected_admin_chat_id:assertion},f.confirmKey)).status,409);
  for(const extra of [{audience:'subscribers'},{chat_id:'202'},{recipients:['202']}])same((await f.call({...f.body,...extra},f.confirmKey)).status,400);
  same(f.db.queries,0);same(f.sent.length,0);
 });
 await scenario('fixed capability pilot works with normal mode OFF and leaves subscribers untouched',async()=>{
  const f=pilotFixture();f.db.subscribe();f.db.subscribe('202');const before=f.db.sql.prepare('SELECT * FROM telegram_update_subscribers ORDER BY chat_id').all();
  const confirmation=await (await f.call(f.body,f.confirmKey)).json();check(confirmation.ok&&confirmation.audience==='pilot'&&confirmation.recipient_verified);
  const tick=await (await f.call({action:'tick',expected_admin_chat_id:'101'})).json();same(tick.sent,1);check(tick.recipient_verified);same(f.sent[0].chat_id,'101');
  await f.call(f.body,f.confirmKey);await f.call({action:'tick',expected_admin_chat_id:'101'});same(f.sent.length,1);
  const status=await (await f.call({action:'status',expected_admin_chat_id:'101'})).json();check(status.recipient_verified);check(!JSON.stringify(status).includes('chat_id'));check(!JSON.stringify(status).includes('101'));
  same(f.db.sql.prepare('SELECT * FROM telegram_update_subscribers ORDER BY chat_id').all(),before);same(f.db.sql.prepare("SELECT COUNT(*) AS n FROM sqlite_master WHERE name='telegram_release_events'").get().n,0);
  same(f.env.TELEGRAM_RELEASE_DELIVERY_MODE,undefined);
 });
 await scenario('capability pilot cannot inherit a subscriber audience or normal route keys',async()=>{
  const f=pilotFixture();f.env.TELEGRAM_RELEASE_DELIVERY_MODE='subscribers';f.db.subscribe('202');await f.call(f.body,f.confirmKey);await f.call({action:'tick',expected_admin_chat_id:'101'});same(f.sent.length,1);same(f.sent[0].chat_id,'101');
  same((await f.call(f.body,f.env.TELEGRAM_RELEASE_CONFIRM_KEY)).status,401);same(f.env.TELEGRAM_RELEASE_DELIVERY_MODE,'subscribers');same(f.db.sql.prepare("SELECT COUNT(*) AS n FROM sqlite_master WHERE name='telegram_release_deliveries'").get().n,0);
 });
 await scenario('capability preview, HTTP and expired authority never reach SQL',async()=>{
  const f=pilotFixture();same((await f.call(f.body,f.confirmKey,'http://outpost.com.ua/api/telegram/releases/pilot')).status,503);
  const r=await worker.fetch(new Request('https://preview.example.pages.dev/api/telegram/releases/pilot',{method:'POST',headers:{'x-outpost-release-key':f.confirmKey},body:JSON.stringify(f.body)}),f.env,{waitUntil(){throw Error('No preview effects');}});same(r.status,403);
  f.env.OUTPOST_PREVIEW_ONLY='1';same((await f.call(f.body,f.confirmKey)).status,503);delete f.env.OUTPOST_PREVIEW_ONLY;f.verifiers.expires_at=new Date(50000).toISOString();same((await f.call(f.body,f.confirmKey)).status,401);same(f.db.queries,0);
 });
 await scenario('authenticated capability requests retain the 8 KiB body limit',async()=>{
  const f=pilotFixture();same((await f.call({...f.body,extra:'x'.repeat(9000)},f.confirmKey)).status,400);same(f.db.queries,0);same(f.sent.length,0);
 });
 await scenario('capability uncertainty is visible without blind replay or cursor changes',async()=>{
  const f=pilotFixture();await f.call(f.body,f.confirmKey);f.setResponse(()=>{throw Error('Possible delivered pilot');});await f.call({action:'tick',expected_admin_chat_id:'101'});await f.call(f.body,f.confirmKey);await f.call({action:'tick',expected_admin_chat_id:'101'});same(f.sent.length,1);check((await (await f.call({action:'status',expected_admin_chat_id:'101'})).json()).reconciliation_required);
 });
 await scenario('delivery mode defaults OFF before SQL or live requests',async()=>{
  for(const mode of ['', 'off', 'all', 'true', '1']){
   const f=fixture();f.env.TELEGRAM_RELEASE_DELIVERY_MODE=mode;await assert.rejects(f.confirm(),/release_delivery_disabled/);await assert.rejects(f.pump(),/release_delivery_disabled/);await assert.rejects(releaseJournalStatus(f.env),/release_delivery_disabled/);same(f.db.queries,0);same(f.fetched.length,0);same(f.sent.length,0);
  }
 });
 await scenario('pilot rejects absent, group or unsafe recipient before SQL',async()=>{
  for(const chat of ['', '-101','0','101,202','9007199254740992','00101']){
   const f=fixture();f.env.TELEGRAM_RELEASE_DELIVERY_MODE='pilot';f.env.TELEGRAM_ADMIN_CHAT_ID=chat;assert.throws(()=>deliveryPolicy(f.env),/pilot_recipient_invalid/);await assert.rejects(f.confirm());same(f.db.queries,0);same(f.sent.length,0);
  }
 });
 await scenario('authenticated off mode and request-selected audience are blocked before SQL',async()=>{
  const f=fixture();const call=body=>handleReleaseDispatch(new Request('https://outpost.com.ua/api/telegram/releases/dispatch',{method:'POST',headers:{'x-outpost-release-key':f.env.TELEGRAM_RELEASE_PUMP_KEY},body:JSON.stringify(body)}),f.env);
  delete f.env.TELEGRAM_RELEASE_DELIVERY_MODE;same((await call({action:'tick'})).status,503);
  f.env.TELEGRAM_RELEASE_DELIVERY_MODE='pilot';f.env.TELEGRAM_ADMIN_CHAT_ID='101';
  for(const extra of [{audience:'subscribers'},{chat_id:'202'},{recipients:['202']},{mode:'subscribers'}])same((await call({action:'tick',...extra})).status,400);
  same(f.db.queries,0);same(f.sent.length,0);
 });
 await scenario('pilot uses only private administrator and never touches subscriber cursors',async()=>{
  const f=fixture();f.db.subscribe();f.db.subscribe('202');f.db.subscribe('303',f.versions);const before=f.db.sql.prepare('SELECT * FROM telegram_update_subscribers ORDER BY chat_id').all();
  f.env.TELEGRAM_RELEASE_DELIVERY_MODE='pilot';f.env.TELEGRAM_ADMIN_CHAT_ID='303';
  same((await f.confirm()).audience,'pilot');same(f.sent.length,0);same((await f.pump()).sent,1);same(f.sent[0].chat_id,'303');check(f.sent[0].text.startsWith('🧪'));await f.confirm();await Promise.all([f.pump(),f.pump()]);same(f.sent.length,1);
  same(f.db.sql.prepare('SELECT * FROM telegram_update_subscribers ORDER BY chat_id').all(),before);
  same(f.db.sql.prepare("SELECT COUNT(*) AS n FROM sqlite_master WHERE name='telegram_release_events'").get().n,0);
  const status=await releaseJournalStatus(f.env);same(status.audience,'pilot');check(!JSON.stringify(status).includes('chat_id'));
 });
 await scenario('pilot does not require or recreate a subscription',async()=>{
  const f=fixture();f.env.TELEGRAM_RELEASE_DELIVERY_MODE='pilot';f.env.TELEGRAM_ADMIN_CHAT_ID='101';await f.confirm();await f.pump();same(f.sent.length,1);check(!f.db.row());
 });
 await scenario('pilot confirmation cannot seed subscriber delivery or cursor suppression',async()=>{
  const f=fixture();f.db.subscribe();f.db.subscribe('202');f.env.TELEGRAM_RELEASE_DELIVERY_MODE='pilot';f.env.TELEGRAM_ADMIN_CHAT_ID='101';await f.confirm();await f.pump();
  f.env.TELEGRAM_RELEASE_DELIVERY_MODE='subscribers';same((await f.pump()).sent,0);await f.confirm();same((await f.pump()).sent,2);same(f.sent.length,3);check(!f.sent.at(-1).text.startsWith('🧪'));
  f.env.TELEGRAM_RELEASE_DELIVERY_MODE='pilot';same((await f.pump()).sent,0);
 });
 await scenario('pilot administrator change cannot deliver old queued recipients',async()=>{
  const f=fixture();f.env.TELEGRAM_RELEASE_DELIVERY_MODE='pilot';f.env.TELEGRAM_ADMIN_CHAT_ID='101';await f.confirm();f.env.TELEGRAM_ADMIN_CHAT_ID='202';same((await f.pump()).cancelled,1);same(f.sent.length,0);
 });
 await scenario('pilot uncertainty stays quarantined and reported, never repeated',async()=>{
  const f=fixture();f.env.TELEGRAM_RELEASE_DELIVERY_MODE='pilot';f.env.TELEGRAM_ADMIN_CHAT_ID='101';await f.confirm();f.setResponse(()=>{throw Error('Possible delivered test');});await f.pump();f.advance(86400000);await f.confirm();await f.pump();same(f.sent.length,1);const status=await releaseJournalStatus(f.env);check(status.reconciliation_required);same(status.deliveries[0].state,'unknown');
 });
 await scenario('pilot uses same acknowledged-send and lost-ack protection as subscribers',async()=>{
  const f=fixture();f.env.TELEGRAM_RELEASE_DELIVERY_MODE='pilot';f.env.TELEGRAM_ADMIN_CHAT_ID='101';await f.confirm();f.db.failAck=true;await assert.rejects(f.pump());f.db.failAck=false;f.advance(180000);await f.pump();same(f.sent.length,1);check((await releaseJournalStatus(f.env)).reconciliation_required);
 });
 await scenario('disabled journal has no DB/network effects',async()=>{
  const f=fixture();f.env.TELEGRAM_CONFIRMED_RELEASES_ENABLED='0';await assert.rejects(f.confirm(),/disabled/);same(f.db.queries,0);same(f.sent.length,0);
 });
 await scenario('preview poison blocks new dispatch path',async()=>{
  const f=fixture();const r=await worker.fetch(new Request('https://preview.example.pages.dev/api/telegram/releases/dispatch',{method:'POST',body:'{}'}),f.env,{waitUntil(){throw Error('Preview scheduled job');}});same(r.status,403);same(f.db.queries,0);
 });
 await scenario('confirmed flag disables legacy sender even when called directly',async()=>{const f=fixture();const r=await maybeNotifyTelegramRelease(f.env);check(r.skipped);same(f.db.queries,0);});
 await scenario('auth separates confirm and pump; rejects replay/extra input',async()=>{
  const f=fixture();const call=(body,key,url='https://outpost.com.ua/api/telegram/releases/dispatch')=>handleReleaseDispatch(new Request(url,{method:'POST',headers:{'x-outpost-release-key':key},body:JSON.stringify(body)}),f.env);
  same((await call({action:'confirm',...f.release('outpost')},f.env.TELEGRAM_RELEASE_PUMP_KEY)).status,401);
  same((await call({action:'tick'},f.env.TELEGRAM_RELEASE_CONFIRM_KEY)).status,401);
  same((await call({action:'tick',chat_id:'101'},f.env.TELEGRAM_RELEASE_PUMP_KEY)).status,400);
  same((await call({action:'tick'},'wrong')).status,401);
  same((await call({action:'tick'},f.env.TELEGRAM_RELEASE_PUMP_KEY,'http://outpost.com.ua/api/telegram/releases/dispatch')).status,503);
  same(f.db.queries,0);
 });
 await scenario('invalid release input rejected without writes',async()=>{
  const f=fixture();for(const input of [{...f.release('outpost'),product:'wrong'},{...f.release('outpost'),version:'999999999999999999999.1.2'},{...f.release('outpost'),size_bytes:1},{...f.release('outpost'),source_sha:'x'}])assert.throws(()=>validateRelease(input));same(f.db.queries,0);
 });
 await scenario('live verifier checks exact bytes, hashes and rejects redirects',async()=>{
  const f=fixture();await verifyConfirmedReleaseLive(f.env,f.release('outpost'),async()=>new Response('redirect',{status:302})).then(()=>assert.fail(),()=>{});
  await assert.rejects(verifyConfirmedReleaseLive(f.env,{...f.release('outpost'),sha256:'B'.repeat(64)},async(url)=>String(url).endsWith('.sha256.txt')?new Response('B'.repeat(64)+' *'+f.release('outpost').installer):String(url).endsWith('.exe')?new Response(Buffer.alloc(2048,1)):new Response(`<a href="/downloads/${f.release('outpost').installer}">demo</a>`)));
  same(f.db.queries,0);
 });
 await scenario('live failure creates no confirmation or queue',async()=>{const f=fixture();f.db.subscribe();await assert.rejects(confirmRelease(f.env,f.release('outpost'),{verifyLive:async()=>{throw Error('Not live');}}));same(f.db.sql.prepare("SELECT COUNT(*) AS n FROM sqlite_master WHERE name='telegram_release_events'").get().n,0);});
 await scenario('two products send separately; cursor advances only after ack',async()=>{
  const f=fixture();f.db.subscribe();const before=f.db.row().last_notified_version;
  await f.confirm();await f.confirm('accounting');same(f.db.row().last_notified_version,before);same(f.sent.length,0);
  f.setResponse(()=>{const product=f.sent.at(-1).text.includes('Бухгалтерія')?'accounting':'outpost';same(f.db.delivery(product).state,'sending');same(JSON.parse(f.db.row().last_notified_version)[product],product==='accounting'?'1.0.2':'0.25.0');return new Response(JSON.stringify({ok:true,result:{message_id:f.sent.length}}));});
  const r=await f.pump();same(r.sent,2);same(JSON.parse(f.db.row().last_notified_version),f.versions);
  check(f.sent.some(x=>x.text.includes('Бухгалтерія v1.0.3')));check(f.sent.some(x=>x.text.includes('OutPOSt v0.25.1')));
  check(f.sent.find(x=>x.text.includes('Бухгалтерія')).reply_markup.inline_keyboard.flat().some(x=>x.url?.endsWith('/buhgalteriya')));
 });
 await scenario('confirmation replay and repeated deploy never resend',async()=>{const f=fixture();f.db.subscribe();await f.confirm();await f.pump();await f.confirm();await f.pump();same(f.sent.length,1);same(f.db.delivery().state,'sent');});
 await scenario('same product/version artifact facts are immutable',async()=>{const f=fixture();f.db.subscribe();await f.confirm();await assert.rejects(confirmRelease(f.env,{...f.release('outpost'),sha256:'B'.repeat(64)},{...f.deps,verifyLive:async()=>({})}),/immutable_release_conflict/);same(f.db.sql.prepare('SELECT sha256 FROM telegram_release_events').get().sha256,f.release('outpost').sha256);same(f.sent.length,0);});
 await scenario('parallel pumps have exactly one successful SQL claim',async()=>{const f=fixture();f.db.subscribe();await f.confirm();await Promise.all([f.pump(),f.pump(),f.pump()]);same(f.sent.length,1);same(f.db.delivery().attempts,1);});
 await scenario('parallel product cursor CAS repair preserves both products',async()=>{const f=fixture();f.db.subscribe();await f.confirm();await f.confirm('accounting');await Promise.all([f.pump(),f.pump()]);await f.pump();await f.pump();same(f.sent.length,2);same(JSON.parse(f.db.row().last_notified_version),f.versions);});
 await scenario('429 respects persistent cooldown and eventual ack',async()=>{
  const f=fixture();f.db.subscribe();await f.confirm();f.setResponse(()=>new Response(JSON.stringify({ok:false,error_code:429,parameters:{retry_after:90}}),{status:429}));
  same((await f.pump()).retry,1);same(JSON.parse(f.db.row().last_notified_version).outpost,'0.25.0');same(f.db.delivery().state,'retry');
  check((await f.pump()).cooldown);same(f.sent.length,1);f.advance(100000);f.setResponse(()=>new Response(JSON.stringify({ok:true,result:{message_id:20}})));await f.pump();same(f.sent.length,2);same(f.db.delivery().state,'sent');
 });
 await scenario('explicit ok:false 5xx retries after backoff',async()=>{const f=fixture();f.db.subscribe();await f.confirm();f.setResponse(()=>new Response(JSON.stringify({ok:false,error_code:503}),{status:503}));await f.pump();same(f.db.delivery().state,'retry');await f.pump();same(f.sent.length,1);f.advance(3600000);f.setResponse(()=>new Response(JSON.stringify({ok:true,result:{message_id:2}})));await f.pump();same(f.db.delivery().state,'sent');});
 await scenario('bare 5xx is quarantined, never replayed',async()=>{const f=fixture();f.db.subscribe();await f.confirm();f.setResponse(()=>new Response('Gateway unavailable',{status:502}));await f.pump();same(f.db.delivery().state,'unknown');f.advance(86400000);await f.pump();same(f.sent.length,1);same(JSON.parse(f.db.row().last_notified_version).outpost,'0.25.0');});
 await scenario('transport uncertainty holds the message and cursor',async()=>{const f=fixture();f.db.subscribe();await f.confirm();f.setResponse(()=>{throw Error('Synthetic timeout after possible delivery');});await f.pump();same(f.db.delivery().state,'unknown');await f.pump();same(f.sent.length,1);});
 await scenario('acknowledged send plus failed D1 write is not sent again',async()=>{const f=fixture();f.db.subscribe();await f.confirm();f.db.failAck=true;await assert.rejects(f.pump());same(f.db.delivery().state,'sending');same(JSON.parse(f.db.row().last_notified_version).outpost,'0.25.0');f.db.failAck=false;f.advance(180000);await f.pump();same(f.db.delivery().state,'unknown');same(f.sent.length,1);});
 await scenario('cursor recovery does not resend acknowledged message',async()=>{const f=fixture();f.db.subscribe();await f.confirm();await f.pump();f.db.sql.prepare("UPDATE telegram_update_subscribers SET last_notified_version=? WHERE chat_id='101'").run(JSON.stringify({outpost:'0.25.0',accounting:'1.0.2'}));f.db.sql.exec("UPDATE telegram_release_deliveries SET cursor_synced=0");await f.pump();same(JSON.parse(f.db.row().last_notified_version).outpost,'0.25.1');same(f.sent.length,1);});
 await scenario('unsubscribe before delivery cancels without recreating subscriber',async()=>{const f=fixture();f.db.subscribe();await f.confirm();f.db.sql.exec("DELETE FROM telegram_update_subscribers");await f.pump();same(f.sent.length,0);same(f.db.delivery().state,'cancelled');check(!f.db.row());});
 await scenario('actual unsubscribe callback purges delivery identifiers',async()=>{
  const f=fixture();f.db.subscribe();await f.confirm();globalThis.fetch=async()=>new Response(JSON.stringify({ok:true,result:{message_id:1}}));
  const r=await handleTelegramWebhook(new Request('https://outpost.com.ua/api/telegram/webhook',{method:'POST',headers:{'x-telegram-bot-api-secret-token':f.env.TELEGRAM_WEBHOOK_SECRET},body:JSON.stringify({callback_query:{id:'demo',data:'updates:unsubscribe',message:{chat:{id:101}}}})}),f.env);
  same(r.status,200);check(!f.db.row());check(!f.db.delivery());globalThis.fetch=async()=>{throw Error('Real network forbidden');};
 });
 await scenario('failed unsubscribe does not falsely announce success',async()=>{
  const f=fixture();f.db.subscribe();f.db.failUnsubscribe=true;const replies=[];globalThis.fetch=async(url,init)=>{replies.push(JSON.parse(init.body));return new Response(JSON.stringify({ok:true,result:{message_id:1}}));};
  await handleTelegramWebhook(new Request('https://outpost.com.ua/api/telegram/webhook',{method:'POST',headers:{'x-telegram-bot-api-secret-token':f.env.TELEGRAM_WEBHOOK_SECRET},body:JSON.stringify({callback_query:{id:'demo',data:'updates:unsubscribe',message:{chat:{id:101}}}})}),f.env);
  check(f.db.row());check(replies.some(x=>x.text?.includes('Не вдалося вимкнути підписку')));check(!replies.some(x=>x.text?.includes('вимкнено.')));globalThis.fetch=async()=>{throw Error('Real network forbidden');};
 });
 await scenario('new subscriber after confirmation gets no historical queue',async()=>{const f=fixture();f.db.subscribe();await f.confirm();f.db.subscribe('202',f.versions,200000);await f.confirm();await f.pump();same(f.sent.filter(x=>x.chat_id==='202').length,0);check(!f.db.delivery('outpost','202'));});
 await scenario('resubscription/current baseline suppresses old release',async()=>{const f=fixture();f.db.subscribe('101',f.versions);await f.confirm();await f.pump();same(f.sent.length,0);same(f.db.delivery().state,'cancelled');});
 await scenario('legacy one-product cursor is not retroactively notified for Accounting',async()=>{const f=fixture();f.db.subscribe('101','0.25.0');await f.confirm();await f.confirm('accounting');await f.pump();same(f.sent.length,1);check(!f.sent[0].text.includes('Бухгалтерія'));same(JSON.parse(f.db.row().last_notified_version),f.versions);});
 await scenario('rollback blocks forward-event delivery',async()=>{const f=fixture();f.db.subscribe();await f.confirm();f.versions.outpost='0.25.0';same((await f.pump()).blocked,1);same(f.sent.length,0);same(f.db.delivery().state,'pending');});
 await scenario('superseded queues do not starve current release',async()=>{const f=fixture();f.db.subscribe();await f.confirm();f.versions.outpost='0.25.2';await f.confirm();await f.pump();same(f.sent.length,1);check(f.sent[0].text.includes('0.25.2'));same(f.db.sql.prepare("SELECT state FROM telegram_release_deliveries WHERE version='0.25.1'").get().state,'cancelled');});
 await scenario('permanent rejection never advances cursor',async()=>{const f=fixture();f.db.subscribe();await f.confirm();f.setResponse(()=>new Response(JSON.stringify({ok:false,error_code:403}),{status:403}));await f.pump();same(f.db.delivery().state,'failed');await f.pump();same(f.sent.length,1);same(JSON.parse(f.db.row().last_notified_version).outpost,'0.25.0');});
 await scenario('finite retry budget prevents loops',async()=>{const f=fixture();f.db.subscribe();await f.confirm();f.setResponse(()=>new Response(JSON.stringify({ok:false,error_code:500}),{status:500}));for(let n=0;n<9;n++){await f.pump();f.advance(7200000);}same(f.sent.length,8);same(f.db.delivery().state,'failed');});
 await scenario('status exposes aggregates only, no recipient identifiers',async()=>{const f=fixture();f.db.subscribe();await f.confirm();const r=await releaseJournalStatus(f.env);check(!JSON.stringify(r).includes('101'));check(!JSON.stringify(r).includes('chat_id'));});
 await scenario('small batch stays within conservative Free query budget',async()=>{const f=fixture();for(const id of ['101','102','103'])f.db.subscribe(id);await f.confirm();f.db.queries=0;await f.pump();check(f.db.queries+f.fetched.length+f.sent.length<50,'Unbounded Free subrequests');same(f.sent.length,3);});
 await scenario('cron defaults disabled and preview blocked',async()=>{same((await pumpConfirmedReleases({})).skipped,true);same((await pumpConfirmedReleases({OUTPOST_RELEASE_SCHEDULER_ENABLED:'1',OUTPOST_PREVIEW_ONLY:'1'})).skipped,true);same((await pumpConfirmedReleases({OUTPOST_RELEASE_SCHEDULER_ENABLED:'1'})).error,'scheduler_not_configured');});
 await scenario('cron is a fixed scoped tick, never confirmation/broadcast API',async()=>{let calls=0;globalThis.fetch=async(url,init)=>{calls++;same(url,'https://outpost.com.ua/api/telegram/releases/dispatch');same(JSON.parse(init.body),{action:'tick'});same(init.redirect,'error');return new Response(JSON.stringify({ok:true,sent:1}));};same((await pumpConfirmedReleases({OUTPOST_RELEASE_SCHEDULER_ENABLED:'1',TELEGRAM_RELEASE_PUMP_KEY:'demo-pump'.padEnd(40,'x')})).sent,1);same(calls,1);globalThis.fetch=async()=>{throw Error('Real network forbidden');};});
 console.log(JSON.stringify({pass:true,cases:cases.length,assertions,real_network_calls:0,sqlite:'real in-memory engine',scenarios:cases}));
}finally{globalThis.fetch=originalFetch;}
