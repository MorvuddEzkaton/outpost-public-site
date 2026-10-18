import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const siteRoot = path.join(repoRoot, "site");
const origin = "http://127.0.0.1:4175";

const mime = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".xml", "application/xml; charset=utf-8"],
  [".txt", "text/plain; charset=utf-8"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".webp", "image/webp"],
  [".svg", "image/svg+xml"],
  [".ico", "image/x-icon"],
]);

function sitemapPaths() {
  const xml = fs.readFileSync(path.join(siteRoot, "sitemap.xml"), "utf8");
  const urls = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => new URL(match[1].trim()));
  const paths = urls.map((url) => url.pathname || "/");
  if (!paths.length) throw new Error("site/sitemap.xml contains no <loc> entries");
  if (new Set(paths).size !== paths.length) throw new Error("site/sitemap.xml contains duplicate paths");
  return paths;
}

function sourcePathForRequest(requestPath) {
  const clean = decodeURIComponent(requestPath.split("?")[0]).replace(/^\/+/, "");
  if (!clean) return path.join(siteRoot, "index.html");

  const direct = path.join(siteRoot, clean);
  if (fs.existsSync(direct) && fs.statSync(direct).isFile()) return direct;

  if (!path.extname(clean)) {
    const html = path.join(siteRoot, `${clean}.html`);
    if (fs.existsSync(html) && fs.statSync(html).isFile()) return html;
  }
  return null;
}

let server;

test.beforeAll(async () => {
  server = http.createServer((req, res) => {
    const requestUrl = new URL(req.url || "/", origin);
    if (requestUrl.pathname.startsWith("/api/")) {
      res.writeHead(404, { "content-type": "application/json; charset=utf-8" });
      res.end('{"ok":false}');
      return;
    }

    const target = sourcePathForRequest(requestUrl.pathname);
    if (!target || !target.startsWith(siteRoot)) {
      res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      res.end("Not found");
      return;
    }

    const type = mime.get(path.extname(target).toLowerCase()) || "application/octet-stream";
    res.writeHead(200, { "content-type": type, "cache-control": "no-store" });
    if (req.method === "HEAD") res.end();
    else res.end(fs.readFileSync(target));
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(4175, "127.0.0.1", resolve);
  });
});

test.afterAll(async () => {
  if (server) await new Promise((resolve) => server.close(resolve));
});

function formatViolation(pagePath, violation) {
  const nodes = violation.nodes.slice(0, 5).map((node) => {
    const target = node.target.join(" ");
    const html = node.html.replace(/\s+/g, " ").slice(0, 180);
    return `${target}: ${html}`;
  });
  const suffix = violation.nodes.length > 5 ? ` (+${violation.nodes.length - 5} more node(s))` : "";
  return `${pagePath}: [${violation.impact || "unknown"}] ${violation.id} — ${violation.help}; ${nodes.join(" | ")}${suffix}`;
}

test("all sitemap pages pass browser WCAG A/AA checks", async ({ browser }) => {
  test.setTimeout(180_000);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const failures = [];

  for (const pagePath of sitemapPaths()) {
    const response = await page.goto(`${origin}${pagePath}`, { waitUntil: "load", timeout: 20_000 });
    if (!response || !response.ok()) {
      failures.push(`${pagePath}: document load failed: HTTP ${response?.status() ?? "no response"}`);
      continue;
    }
    await page.waitForTimeout(150);

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    for (const violation of results.violations) failures.push(formatViolation(pagePath, violation));
  }

  await context.close();
  expect(failures, failures.join("\n")).toEqual([]);
});

test("modern demo sale, dashboard and settings pass WCAG checks in all themes", async ({page}) => {
  test.setTimeout(120_000);
  const failures = [];
  await page.setViewportSize({width:1280,height:960});
  await page.goto(origin + '/demo', {waitUntil:'load'});
  for (const theme of ['light','dark','contrast']) {
    await page.locator('.demo-nav[data-view="settings"]').click();
    await page.locator('#appearance-theme').selectOption(theme);
    await page.locator('#appearance-apply').click();
    for (const view of ['sale','home','settings']) {
      await page.locator(`.demo-nav[data-view="${view}"]`).click();
      const results = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
      for (const violation of results.violations) failures.push(formatViolation(`/demo ${theme}/${view}`,violation));
      if(view==='home'){
        await page.locator('#dashboard-configure').click();
        const dialogResults=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
        for(const violation of dialogResults.violations)failures.push(formatViolation(`/demo ${theme}/dashboard-layout`,violation));
        await page.keyboard.press('Escape');
      }
    }
  }
  expect(failures,failures.join('\n')).toEqual([]);
});
