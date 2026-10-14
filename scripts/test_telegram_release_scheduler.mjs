// Offline relay tests only. No real bot, credentials, D1 or outbound requests.
import assert from 'node:assert/strict';
import scheduler, {pumpConfirmedReleases} from './telegram_release_scheduler.mjs';
globalThis.fetch=async()=>{throw Error('Real network forbidden in offline relay tests');};

const env={OUTPOST_RELEASE_SCHEDULER_ENABLED:'1',TELEGRAM_RELEASE_PUMP_KEY:'synthetic-pump-not-a-real-secret'.padEnd(40,'x')};
const ack={ok:true,audience:'subscribers',examined:1,sent:1,retry:0,unknown:0,failed:0,blocked:0,cancelled:0};
const unavailable={ok:false,error:'pump_unavailable'};
let cases=0;
async function test(name,run){await run();cases++;}
const reply=data=>Response.json(data);

await test('OFF and preview perform no request',async()=>{
 const never=async()=>{assert.fail('Disabled relay must not fetch');};
 assert.deepEqual(await pumpConfirmedReleases({},never),{ok:true,skipped:true});
 assert.deepEqual(await pumpConfirmedReleases({...env,OUTPOST_PREVIEW_ONLY:'1'},never),{ok:true,skipped:true});
});
await test('missing credential performs no request',async()=>{
 assert.deepEqual(await pumpConfirmedReleases({OUTPOST_RELEASE_SCHEDULER_ENABLED:'1'},async()=>assert.fail('No key')),{ok:false,error:'scheduler_not_configured'});
});
await test('one fixed scoped tick with honest identity, timeout and no redirects',async()=>{
 let calls=0;
 const result=await pumpConfirmedReleases(env,async(url,init)=>{
  calls++;assert.equal(url,'https://outpost.com.ua/api/telegram/releases/dispatch');
  assert.equal(init.method,'POST');assert.equal(init.redirect,'manual');
  assert.deepEqual(JSON.parse(init.body),{action:'tick'});
  const headers=new Headers(init.headers);
  assert.equal(headers.get('x-outpost-release-key'),env.TELEGRAM_RELEASE_PUMP_KEY);
  assert.equal(headers.get('user-agent'),'OutPOSt-Release-Scheduler/1.0 (+https://outpost.com.ua)');
  assert.equal(headers.get('accept'),'application/json');
  assert(init.signal instanceof AbortSignal);assert.equal(init.signal.aborted,false);
  return reply(ack);
 });
 assert.equal(calls,1);assert.deepEqual(result,{ok:true,sent:1,retry:0,unknown:0,failed:0,blocked:0,cancelled:0,cooldown:false});
});
await test('redirect is not followed or retried and no private destination escapes',async()=>{
 let calls=0;const result=await pumpConfirmedReleases(env,async()=>{calls++;return new Response(null,{status:302,headers:{Location:'https://forbidden.invalid/private'}});});
 assert.equal(calls,1);assert.deepEqual(result,unavailable);
});
await test('network failure has no retry or exception disclosure',async()=>{
 let calls=0;assert.deepEqual(await pumpConfirmedReleases(env,async()=>{calls++;throw Error('PRIVATE TOKEN');}),unavailable);assert.equal(calls,1);
});
await test('HTTP failure, HTML, malformed JSON, wrong audience and absent success fail closed',async()=>{
 for(const response of [new Response('PRIVATE',{status:503}),new Response('PRIVATE'),new Response('{'),reply(null),reply({ok:true,sent:0}),reply({ok:true,audience:'subscribers'}),reply({...ack,audience:'pilot'}),reply({...ack,ok:false})]){
  let calls=0;assert.deepEqual(await pumpConfirmedReleases(env,async()=>{calls++;return response;}),unavailable);assert.equal(calls,1);
 }
});
await test('response stream is bounded and cancelled before unbounded reading',async()=>{
 let cancelled=false,pulls=0;
 const body=new ReadableStream({pull(controller){pulls++;controller.enqueue(new Uint8Array(4096).fill(32));},cancel(){cancelled=true;}});
 assert.deepEqual(await pumpConfirmedReleases(env,async()=>new Response(body)),unavailable);
 assert.equal(cancelled,true);assert(pulls<=4);
});
await test('invalid counters never become a successful tick',async()=>{
 for(const patch of [{sent:'1'},{sent:4},{sent:-1},{unknown:0.5},{retry:null},{failed:true},{blocked:Infinity},{cancelled:4},{cooldown:'false'},{sent:2,retry:2}]){
  assert.deepEqual(await pumpConfirmedReleases(env,async()=>reply({...ack,...patch})),unavailable);
 }
});
await test('uncertainty and failed or integrity-blocked deliveries are visible',async()=>{
 for(const name of ['unknown','failed','blocked']){
  const result=await pumpConfirmedReleases(env,async()=>reply({...ack,sent:0,[name]:1}));
  assert.equal(result.ok,false);assert.equal(result.error,'delivery_attention_required');assert.equal(result[name],1);assert.equal(result.sent,0);
 }
});
await test('cooldown and explicit retry do not trigger immediate resubmission',async()=>{
 for(const response of [{ok:true,audience:'subscribers',sent:0,cooldown:true},{...ack,sent:0,retry:1}]){
  let calls=0;const result=await pumpConfirmedReleases(env,async()=>{calls++;return reply(response);});
  assert.equal(result.ok,true);assert.equal(calls,1);assert.equal(result.cooldown,response.cooldown===true);
 }
});
await test('scheduled handler awaits one attempt and logs only bounded safe fields',async()=>{
 const originalFetch=globalThis.fetch,originalError=console.error;
 const logs=[];let calls=0,pending;
 try{
  globalThis.fetch=async()=>{calls++;return reply({...ack,sent:0,unknown:1,private_debug:'PRIVATE'});};
  console.error=value=>logs.push(JSON.parse(value));
  await scheduler.scheduled({},env,{waitUntil(value){pending=value;}});await pending;
  assert.equal(calls,1);assert.equal(logs.length,1);assert.equal(logs[0].unknown,1);
  assert(!JSON.stringify(logs).includes('PRIVATE'));assert(!JSON.stringify(logs).includes(env.TELEGRAM_RELEASE_PUMP_KEY));
 }finally{globalThis.fetch=originalFetch;console.error=originalError;}
});
await test('no public manual trigger',async()=>{assert.equal((await scheduler.fetch()).status,404);});
console.log(JSON.stringify({pass:true,cases,real_network_requests:0,database_requests:0,real_telegram_requests:0}));
