// Credential-free locked dependency installation/bundling. Never run Pages deploy.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import cp from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const installed=process.argv.includes('--installed-only');
if(!installed&&process.env.GITHUB_ACTIONS!=='true'){
 console.log('Publisher toolchain: OFFLINE ONLY; no installation, Linux validation or deployment claimed');
}else{
 let stage='locked-toolchain';
 try{
  const env=Object.fromEntries(Object.entries(process.env).filter(([name])=>!name.startsWith('GIT_CONFIG_')&&!/TOKEN|SECRET|PASSWORD|KEY/i.test(name)));
  env.WRANGLER_SEND_METRICS='false';
  let directory;
  if(installed){
   directory=process.env.OUTPOST_TOOLCHAIN_ROOT;
   if(!directory||!path.isAbsolute(directory))throw Error('Installed toolchain directory missing');
  }else{
   if(process.platform!=='linux')throw Error('CI toolchain validation requires Linux');
   directory=fs.mkdtempSync(path.join(os.tmpdir(),'outpost-publisher-toolchain-'));
   for(const file of ['package.json','package-lock.json'])fs.copyFileSync(path.join(root,'scripts/publisher-tools',file),path.join(directory,file));
   const result=cp.spawnSync('npm',['ci','--ignore-scripts','--no-audit','--no-fund','--prefix',directory],{env,stdio:'pipe',timeout:180000});
   if(result.status!==0)throw Error('Locked credential-free installation failed');
  }
  const require=createRequire(path.join(directory,'package.json'));
  const wrangler=JSON.parse(fs.readFileSync(path.join(directory,'node_modules/wrangler/package.json'),'utf8'));
  if(wrangler.version!=='4.142.0')throw Error('Unexpected publisher tool version');
  const esbuild=require('esbuild');
  stage='worker-bundling';
  const bundle=esbuild.buildSync({entryPoints:[path.join(root,'site/_worker.js')],bundle:true,write:false,format:'esm',platform:'neutral',target:'es2022',logLevel:'silent'});
  if(bundle.outputFiles.length!==1||bundle.outputFiles[0].contents.length<1000)throw Error('Worker bundling not verified');
  const api=require('wrangler');
  const originalFetch=globalThis.fetch;let network=0,sql=0,background=0;
  globalThis.fetch=async()=>{network++;throw Error('Offline binding/worker probe must not make outbound calls');};
  try{
   stage='official-config-and-bindings';
   // Use the pinned official parser AND binding serializer, not a hand-injected
   // mode value from project metadata. CI repeats this after the locked install.
   const production=api.unstable_readConfig({config:path.join(root,'wrangler.jsonc'),env:'production'},{hideWarnings:true});
   const preview=api.unstable_readConfig({config:path.join(root,'wrangler.jsonc'),env:'preview'},{hideWarnings:true});
   const productionBindings=api.unstable_convertConfigBindingsToStartWorkerBindings(production);
   const previewBindings=api.unstable_convertConfigBindingsToStartWorkerBindings(preview);
   const flag=productionBindings.TELEGRAM_CONFIRMED_RELEASES_ENABLED;
   if(flag?.type!=='plain_text'||flag.value!=='1'||previewBindings.TELEGRAM_CONFIRMED_RELEASES_ENABLED!==undefined)throw Error('Official runtime binding serialization mismatch');
   if(JSON.stringify(production.vars)!==JSON.stringify({TELEGRAM_CONFIRMED_RELEASES_ENABLED:'1'})||Object.keys(preview.vars).length!==0)throw Error('Variable contract or preview inheritance changed');
   stage='compiled-worker-import';
   const worker=(await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].contents).toString('base64'))).default;
   const support={TELEGRAM_BOT_TOKEN:'SYNTHETIC-NOT-A-TOKEN',TELEGRAM_WEBHOOK_SECRET:'SYNTHETIC-ONLY',TELEGRAM_ADMIN_CHAT_ID:'SYNTHETIC-ONLY',TELEGRAM_PUBLIC_ENABLED:'1'};
   const db={prepare(){sql++;throw Error('No SQL allowed');},withSession(){sql++;throw Error('No SQL allowed');}};
   const context={waitUntil(){background++;throw Error('No background delivery allowed');}};
   const runtime={...support,TELEGRAM_CONFIRMED_RELEASES_ENABLED:flag.value,ANALYTICS_DB:db,ASSETS:{fetch(){return new Response('SYNTHETIC ONLY');}}};
   stage='compiled-worker-health';
   const health=await (await worker.fetch(new Request('https://outpost.com.ua/api/telegram/health'),runtime,context)).json();
   if(health.release_mode_schema!==1||!health.enabled||!health.confirmed_releases_enabled||health.legacy_release_notifications_enabled)throw Error('Compiled worker did not receive declared safe mode');
   stage='compiled-static-routes';
   for(const route of ['/', '/download', '/download.html'])if((await worker.fetch(new Request('https://outpost.com.ua'+route),runtime,context)).status!==200)throw Error('Compiled static route failed');
   stage='compiled-dispatch-auth';
   for(const action of ['status','confirm','tick']){
    const response=await worker.fetch(new Request('https://outpost.com.ua/api/telegram/releases/dispatch',{method:'POST',headers:{'Content-Type':'application/json','x-outpost-release-key':'SYNTHETIC-ONLY'},body:JSON.stringify({action})}),runtime,context);
    if(response.status!==401)throw Error('Missing operational key must reject before SQL/delivery');
   }
   stage='compiled-preview';
   const previewHealth=await (await worker.fetch(new Request('https://example.pages.dev/api/telegram/health'),{...support,...preview.vars},context)).json();
   if(!previewHealth.integrations_disabled||previewHealth.enabled||previewHealth.confirmed_releases_enabled||previewHealth.legacy_release_notifications_enabled)throw Error('Compiled preview is not isolated');
   if(network||sql||background)throw Error('Unexpected offline side effect');
   console.log(JSON.stringify({pass:true,platform:process.platform,locked_installation:!installed,worker_bundle_bytes:bundle.outputFiles[0].contents.length,wrangler_version:wrangler.version,
    official_parser_and_binding_serialization:true,production_mode:'1',preview_mode_absent:true,compiled_worker_mode_verified:true,network_calls:network,database_calls:sql,background_tasks:background,production_calls:0,
    live_deployment_acceptance:false}));
  }finally{globalThis.fetch=originalFetch;}
 }catch{
  console.error('Publisher toolchain: FAIL at '+stage+'; no deployment or secret values printed');process.exitCode=1;
 }
}
