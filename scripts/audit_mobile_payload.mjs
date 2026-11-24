#!/usr/bin/env node
// Read-only Chromium resource measurement, not a Lighthouse or field CWV test.
// From repo root: npm install --no-save --no-package-lock @playwright/test@1.55.0
// npx playwright install chromium
// node scripts/audit_mobile_payload.mjs > mobile-payload.json
// Optional: --live uses public HTTPS pages instead of the local static server.
import { chromium } from "@playwright/test";
import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../site");
const live = process.argv.includes("--live");
const cssCoverage = process.argv.includes("--css-coverage");
const pages = ["/","/features","/modules","/download","/offline-programa-dlya-magazynu","/interfeis"];
const viewports = [{width:390,height:844},{width:1440,height:900}];
const types = new Map(Object.entries({
  ".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",
  ".js":"text/javascript; charset=utf-8",".mjs":"text/javascript; charset=utf-8",
  ".json":"application/json",".png":"image/png",".jpg":"image/jpeg",
  ".jpeg":"image/jpeg",".webp":"image/webp",".svg":"image/svg+xml",
  ".ico":"image/x-icon",".woff2":"font/woff2",".woff":"font/woff",
  ".avif":"image/avif",".gif":"image/gif"
}));
const isStatic = p => !p.startsWith("/api/") && !p.startsWith("/downloads/") &&
  !p.startsWith("/setup/") && !p.startsWith("/cabinet") &&
  (pages.includes(p) || (types.has(path.extname(p)) && path.extname(p) !== ".html"));
const server = http.createServer(async (req,res) => {
  try {
    const url = new URL(req.url,"http://localhost");
    if (req.method !== "GET" || !isStatic(url.pathname)) {res.writeHead(404).end();return;}
    const file = pages.includes(url.pathname)
      ? path.join(site,url.pathname === "/" ? "index.html" : url.pathname.slice(1)+".html")
      : path.resolve(site,"."+decodeURIComponent(url.pathname));
    if (!file.startsWith(site+path.sep)) {res.writeHead(403).end();return;}
    const data = await fs.readFile(file);
    res.writeHead(200,{"content-type":types.get(path.extname(file)),"cache-control":"no-store"});
    res.end(data);
  } catch {res.writeHead(404).end();}
});
let browser;
try {
  if (!live) await new Promise((resolve,reject) => {
    server.once("error",reject);
    server.listen(0,"127.0.0.1",resolve);
  });
  const origin = live ? "https://outpost.com.ua" : "http://127.0.0.1:"+server.address().port;
  browser = await chromium.launch();
  const results = [];
  for (const viewport of viewports) {
    for (const route of pages) {
      const context = await browser.newContext({viewport,serviceWorkers:"block"});
      const page = await context.newPage();
      const blocked = [];
      try {
        await context.route("**/*", async requestRoute => {
          const req = requestRoute.request();
          const url = new URL(req.url());
          if (url.origin !== origin || req.method() !== "GET" || !isStatic(url.pathname)) {
            blocked.push({origin:url.origin,path:url.pathname});
            await requestRoute.abort();
          } else await requestRoute.continue();
        });
        if (cssCoverage) await page.coverage.startCSSCoverage({resetOnNavigation:false});
        const response = await page.goto(origin+route,{waitUntil:"networkidle",timeout:30000});
        if (!response?.ok()) throw new Error("HTTP "+response?.status());
        await page.evaluate(async () => {await document.fonts.ready;});
        const metrics = await page.evaluate(() => {
          const nav = performance.getEntriesByType("navigation")[0];
          const records = performance.getEntriesByType("resource").map(e => ({
            path:new URL(e.name).pathname,initiator:e.initiatorType,
            transferBytes:e.transferSize,encodedBodyBytes:e.encodedBodySize,
            decodedBodyBytes:e.decodedBodySize,durationMs:Math.round(e.duration)
          }));
          const documentRecord = {path:location.pathname,initiator:"document",
            transferBytes:nav.transferSize,encodedBodyBytes:nav.encodedBodySize,
            decodedBodyBytes:nav.decodedBodySize,durationMs:Math.round(nav.duration)};
          const resources = [documentRecord,...records];
          const byType = {};
          for (const r of resources) {
            const kind = r.path.endsWith(".css")?"css":
              /\.(m?js)$/.test(r.path)?"js":
              /\.(png|jpe?g|webp|svg|ico|avif|gif)$/.test(r.path)?"image":
              /\.woff2?$/.test(r.path)?"font":r.initiator;
            const sum = byType[kind] ??= {requests:0,transferBytes:0,encodedBodyBytes:0,decodedBodyBytes:0};
            sum.requests++;
            for (const k of ["transferBytes","encodedBodyBytes","decodedBodyBytes"]) sum[k]+=r[k];
          }
          return {byType,resources,loadMs:Math.round(nav.loadEventEnd),
            horizontalOverflow:document.documentElement.scrollWidth-innerWidth};
        });
        const coverage = cssCoverage ? (await page.coverage.stopCSSCoverage()).filter(entry => {
          const url = new URL(entry.url, origin);
          return url.origin === origin && url.pathname.endsWith(".css");
        }).map(entry => {
          const ranges = entry.ranges;
          const totalBytes = Buffer.byteLength(entry.text, "utf8");
          const usedBytes = ranges.reduce((sum, range) =>
            sum + Buffer.byteLength(entry.text.slice(range.start, range.end), "utf8"), 0);
          return {path:new URL(entry.url,origin).pathname,totalBytes,usedBytes,
            unusedBytes:Math.max(0,totalBytes-usedBytes)};
        }) : undefined;
        results.push({route,viewport,...metrics,blocked,...(coverage ? {cssCoverage:coverage} : {})});
      } catch (error) {
        results.push({route,viewport,error:String(error),blocked});
      } finally {await context.close();}
    }
  }
  console.log(JSON.stringify({mode:live?"public-live":"local-static",browser:browser.version(),
    cssCoverageEnabled:cssCoverage,
    caveat:"Fresh browser contexts, no scrolling, external/API/installer requests blocked; resource timings include cache/encoding effects. CSS coverage is initial-render only, not proof unused styles can be deleted. No simulated slow network, no Lighthouse or field CWV scores.",results},null,2));
  if (results.some(r=>r.error)) process.exitCode=1;
} finally {
  if (browser) await browser.close();
  if (server.listening) await new Promise(resolve=>server.close(resolve));
}
