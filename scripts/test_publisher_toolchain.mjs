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
  const bundle=esbuild.buildSync({entryPoints:[path.join(root,'site/_worker.js')],bundle:true,write:false,format:'esm',platform:'neutral',target:'es2022',logLevel:'silent'});
  if(bundle.outputFiles.length!==1||bundle.outputFiles[0].contents.length<1000)throw Error('Worker bundling not verified');
  console.log(JSON.stringify({pass:true,platform:process.platform,locked_installation:!installed,worker_bundle_bytes:bundle.outputFiles[0].contents.length,wrangler_version:wrangler.version,production_calls:0}));
 }catch{
  console.error('Publisher toolchain: FAIL; no deployment or secret values printed');process.exitCode=1;
 }
}
