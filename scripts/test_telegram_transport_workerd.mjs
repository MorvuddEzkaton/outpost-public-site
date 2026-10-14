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
 assert.equal(host,'api.telegram.org','Redirect must never receive the synthetic credential');
 assert.equal(request.method,'POST');
 const body=await request.json();
 if(body.text==='redirect-case')return new Response(null,{status:302,headers:{Location:'https://forbidden.invalid/never-follow'}});
 return Response.json({ok:true,result:{message_id:123}});
};
const entry=`import {sendJournalMessage} from './site/_telegram-release-journal.js';
export default {async fetch(){const env={TELEGRAM_BOT_TOKEN:'synthetic-not-a-real-token'};
const ack=await sendJournalMessage(env,{chat_id:'synthetic',text:'ack-case'});
const redirected=await sendJournalMessage(env,{chat_id:'synthetic',text:'redirect-case'});
return Response.json({ack,redirected});}};`;
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
 assert.equal(requests.length,2);
 assert(requests.every(row=>row.host==='api.telegram.org'&&row.method==='POST'));
 console.log(JSON.stringify({pass:true,runtime:'actual local workerd',cases:2,remote_network_requests:0,real_telegram_requests:0,database_requests:0}));
}finally{await runtime?.dispose();}
