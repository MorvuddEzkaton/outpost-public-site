#!/usr/bin/env node
// Deterministic, fail-closed page-scoped CSS prototype. No runtime dependencies.
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import crypto from "node:crypto";
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
export function buildScopedCss(source){
  const legacy=/^(?:body)?\.(?:design-v16|veteran-v16|design-v17)(?=[\s.:[>#~+]|$)/;
  let removed=0;
  function scan(s,start,stops){
    let quote="",parens=0,brackets=0,braces=0;
    for(let i=start;i<s.length;i++){
      const c=s[i],next=s[i+1];
      if(quote){if(c==="\\"){i++;continue}if(c===quote)quote="";continue}
      if(c==="/"&&next==="*"){const end=s.indexOf("*/",i+2);if(end<0)throw Error("Unclosed CSS comment");i=end+1;continue}
      if(c==="'"||c==='"'){quote=c;continue}
      if(c==="\\"){i++;continue}
      if(c==="(")parens++;
      else if(c===")")parens--;
      else if(c==="[")brackets++;
      else if(c==="]")brackets--;
      else if(!parens&&!brackets){
        if(!braces&&stops.includes(c))return i;
        if(c==="{")braces++;
        else if(c==="}")braces--;
      }
      if(parens<0||brackets<0||braces<0)throw Error("Unbalanced CSS");
    }
    if(quote||parens||brackets||braces)throw Error("Unbalanced CSS at EOF");
    return s.length;
  }
  function rewrite(s){
    let out="",i=0;
    while(i<s.length){
      const prefix=s.slice(i).match(/^(?:\s+|\/\*[\s\S]*?\*\/)*/)[0];out+=prefix;i+=prefix.length;if(i===s.length)break;
      const end=scan(s,i,"{;}");
      if(end===s.length||s[end]==="}")throw Error("Unexpected rule ending");
      if(s[end]===";"){out+=s.slice(i,end+1);i=end+1;continue}
      const close=scan(s,end+1,"}");
      if(close===s.length)throw Error("Unclosed CSS block");
      const header=s.slice(i,end),body=s.slice(end+1,close);
      if(/^@media\b/i.test(header))out+=header+"{"+rewrite(body)+"}";
      else if(!header.startsWith("@")&&header.split(",").every(sel=>legacy.test(sel.trim()))){removed++;}
      else out+=s.slice(i,close+1);
      i=close+1;
    }
    return out;
  }
  const css=rewrite(source);
  return {css,removed};
}
const sourcePath=path.join(root,"site/assets/site.css");
const targetPath=path.join(root,"site/assets/site-modern-scope.css");
export function expectedScopedCss(source){
  const {css,removed}=buildScopedCss(source);
  if(!removed)throw Error("No removable scoped rules; review generator");
  const sha=crypto.createHash("sha256").update(source,"utf8").digest("hex");
  return {css:"/* Generated from site.css; SHA256 "+sha+"; removed "+removed+" legacy-scoped rules. Do not edit. */\n"+css,removed};
}
if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const source=fs.readFileSync(sourcePath,"utf8");
  const {css,removed}=expectedScopedCss(source);
  if(process.argv.length===3 && process.argv[2]==="--check"){
    if(fs.readFileSync(targetPath,"utf8")!==css)throw Error("Scoped stylesheet stale; regenerate and review");
  }else if(process.argv.length===3 && process.argv[2]==="--write"){
    fs.writeFileSync(targetPath,css,"utf8");
  }else throw Error("Use --check or --write");
  console.log(JSON.stringify({removed,sourceBytes:Buffer.byteLength(source),generatedBytes:Buffer.byteLength(css)}));
}
