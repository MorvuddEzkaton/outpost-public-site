// Actual edge-runtime regression, intercepted synthetic Telegram responses only.
// Uses the already lockfile-pinned publisher tool; never installs dependencies.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
const root=fileURLToPath(new URL('../',import.meta.url));
const cli=process.env.OUTPOST_WRANGLER_JS||'';
assert(path.isAbsolute(cli)&&path.basename(cli)==='wrangler.js','Pinned publisher runtime required');
assert.equal(JSON.parse(fs.readFileSync(path.resolve(path.dirname(cli),'../package.json'),'utf8')).version,'4.142.0');
const require=createRequire(cli);
const {Miniflare,convertV4MiniflareOptions}=require('miniflare');
const {build}=require('esbuild');
const compatibilityDate=JSON.parse(fs.readFileSync(path.join(root,'wrangler.jsonc'),'utf8')).compatibility_date;
const requests=[];
const outbound=async request=>{
 const host=new URL(request.url).hostname;requests.push({host,method:request.method});
 if(host==='outpost.com.ua'){
  assert.equal(request.url,'https://outpost.com.ua/api/telegram/releases/dispatch');
  assert.equal(request.method,'POST');assert.deepEqual(await request.json(),{action:'tick'});
  assert.equal(request.headers.get('user-agent'),'OutPOSt-Release-Scheduler/1.0 (+https://outpost.com.ua)');
  assert.equal(request.headers.get('accept'),'application/json');
  const key=request.headers.get('x-outpost-release-key');
  assert(key.startsWith('synthetic-pump-'));
  if(key.includes('redirect'))return new Response(null,{status:302,headers:{Location:'https://forbidden.invalid/never-follow'}});
  if(key.includes('oversize'))return new Response(' '.repeat(8193));
  if(key.includes('malformed'))return new Response('{');
  if(key.includes('network'))throw Error('Synthetic network failure; never replay');
  if(key.includes('cooldown'))return Response.json({ok:true,audience:'subscribers',sent:0,cooldown:true});
  return Response.json({ok:true,audience:'subscribers',sent:key.includes('unknown')?0:1,unknown:key.includes('unknown')?1:0});
 }
 assert.equal(host,'api.telegram.org','Redirect must never receive the synthetic credential');
 assert.equal(request.method,'POST');
 const body=await request.json();
 if(body.text==='redirect-case')return new Response(null,{status:302,headers:{Location:'https://forbidden.invalid/never-follow'}});
 return Response.json({ok:true,result:{message_id:123}});
};
const entry=`import {sendJournalMessage} from './site/_telegram-release-journal.js';
import {pumpConfirmedReleases} from './scripts/telegram_release_scheduler.mjs';
export default {async fetch(){const env={TELEGRAM_BOT_TOKEN:'synthetic-not-a-real-token'};
const ack=await sendJournalMessage(env,{chat_id:'synthetic',text:'ack-case'});
const redirected=await sendJournalMessage(env,{chat_id:'synthetic',text:'redirect-case'});
const relay={};
relay.off=await pumpConfirmedReleases({});
relay.preview=await pumpConfirmedReleases({OUTPOST_RELEASE_SCHEDULER_ENABLED:'1',OUTPOST_PREVIEW_ONLY:'1'});
for(const name of ['ack','redirect','oversize','malformed','unknown','cooldown','network']){
 relay[name]=await pumpConfirmedReleases({OUTPOST_RELEASE_SCHEDULER_ENABLED:'1',TELEGRAM_RELEASE_PUMP_KEY:('synthetic-pump-'+name).padEnd(40,'x')});
}
return Response.json({ack,redirected,relay});}};`;
const bundled=await build({stdin:{contents:entry,resolveDir:root,sourcefile:'offline-telegram-workerd.js'},bundle:true,write:false,platform:'browser',format:'esm'});
let runtime;
try{
 const options=convertV4MiniflareOptions({modules:true,script:bundled.outputFiles[0].text,compatibilityDate,outboundService:outbound,cf:false});
 options.telemetry={enabled:false};
 runtime=new Miniflare(options);
 const response=await runtime.dispatchFetch('https://offline.invalid/test');
 assert.equal(response.status,200);
 const result=await response.json();
 assert.deepEqual(result.ack,{kind:'sent',message_id:123});
 assert.deepEqual(result.redirected,{kind:'unknown',error:'redirect_unconfirmed'});
 assert.deepEqual(result.relay.off,{ok:true,skipped:true});
 assert.deepEqual(result.relay.preview,{ok:true,skipped:true});
 assert.equal(result.relay.ack.ok,true);assert.equal(result.relay.ack.sent,1);
 for(const name of ['redirect','oversize','malformed','network'])assert.deepEqual(result.relay[name],{ok:false,error:'pump_unavailable'});
 assert.equal(result.relay.unknown.ok,false);assert.equal(result.relay.unknown.error,'delivery_attention_required');assert.equal(result.relay.unknown.unknown,1);
 assert.equal(result.relay.cooldown.ok,true);assert.equal(result.relay.cooldown.cooldown,true);
 assert.equal(requests.length,9);
 assert.equal(requests.filter(row=>row.host==='api.telegram.org').length,2);
 assert.equal(requests.filter(row=>row.host==='outpost.com.ua').length,7);
 assert(requests.every(row=>['api.telegram.org','outpost.com.ua'].includes(row.host)&&row.method==='POST'));
 console.log(JSON.stringify({pass:true,runtime:'actual local workerd',cases:11,relay_cases:9,remote_network_requests:0,real_telegram_requests:0,database_requests:0}));
}finally{await runtime?.dispose();}
