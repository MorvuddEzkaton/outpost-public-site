import { test, expect } from "@playwright/test";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const siteRoot = path.join(repoRoot, "site");
const artifactRoot = path.join(repoRoot, "browser-keyboard-artifacts");
const origin = "http://127.0.0.1:4174";

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
  const paths = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)]
    .map((match) => new URL(match[1].trim()).pathname || "/");
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
    const nested = path.join(siteRoot, clean, "index.html");
    if (fs.existsSync(nested) && fs.statSync(nested).isFile()) return nested;
  }
  return null;
}

function slugFor(pagePath) {
  return pagePath === "/" ? "home" : pagePath.replace(/^\//, "").replace(/[^a-zA-Z0-9_-]+/g, "-");
}

let server;

test.beforeAll(async () => {
  fs.rmSync(artifactRoot, { recursive: true, force: true });
  fs.mkdirSync(artifactRoot, { recursive: true });
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

    res.writeHead(200, {
      "content-type": mime.get(path.extname(target).toLowerCase()) || "application/octet-stream",
      "cache-control": "no-store",
    });
    if (req.method === "HEAD") res.end();
    else res.end(fs.readFileSync(target));
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(4174, "127.0.0.1", resolve);
  });
});

test.afterAll(async () => {
  if (server) await new Promise((resolve) => server.close(resolve));
});

async function checkSkipLink(page, pagePath, failures) {
  await page.keyboard.press("Tab");
  const firstFocus = await page.evaluate(() => {
    const active = document.activeElement;
    if (!(active instanceof HTMLElement)) return null;
    const rect = active.getBoundingClientRect();
    const style = getComputedStyle(active);
    return {
      isSkip: active.matches(".skip-link"),
      text: active.textContent?.trim() || "",
      visible: style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < innerHeight,
    };
  });

  if (!firstFocus?.isSkip) {
    failures.push(`${pagePath}: first Tab does not focus .skip-link (got ${firstFocus?.text || "<none>"})`);
    return;
  }
  if (!firstFocus.visible) failures.push(`${pagePath}: skip-link is not visible when focused`);

  await page.keyboard.press("Enter");
  await page.waitForTimeout(40);
  if ((await page.evaluate(() => location.hash)) !== "#main") {
    failures.push(`${pagePath}: activating skip-link does not navigate to #main`);
    return;
  }

  await page.keyboard.press("Tab");
  const inMain = await page.evaluate(() => {
    const main = document.querySelector("#main");
    return Boolean(main && (document.activeElement === main || main.contains(document.activeElement)));
  });
  if (!inMain) failures.push(`${pagePath}: Tab after skip-link does not continue inside #main`);
}

async function reachMobileToggle(page) {
  for (let presses = 1; presses <= 10; presses += 1) {
    await page.keyboard.press("Tab");
    const state = await page.evaluate(() => {
      const active = document.activeElement;
      return {
        toggle: active instanceof Element && active.matches("[data-nav-toggle]"),
        label: active instanceof HTMLElement ? (active.getAttribute("aria-label") || active.textContent || active.tagName).trim().replace(/\s+/g, " ").slice(0, 80) : "<none>",
      };
    });
    if (state.toggle) return { reached: true, presses, label: state.label };
  }
  return { reached: false, presses: 10, label: "" };
}

async function mobileNavState(page) {
  return page.evaluate(() => {
    const toggles = [...document.querySelectorAll("[data-nav-toggle]")];
    const navs = [...document.querySelectorAll("[data-nav]")];
    const nav = navs[0] || null;
    const toggle = toggles[0] || null;
    const active = document.activeElement;
    const style = nav ? getComputedStyle(nav) : null;
    const rect = nav?.getBoundingClientRect();
    const visible = Boolean(nav && style && rect && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0.01 && rect.width > 0 && rect.height > 0);
    return {
      visible,
      expanded: toggle?.getAttribute("aria-expanded") || null,
      activeExpanded: active instanceof Element ? active.getAttribute("aria-expanded") : null,
      activeIsToggle: active === toggle,
      activeInsideNav: Boolean(nav && active && nav.contains(active)),
      activeText: active instanceof HTMLElement ? (active.getAttribute("aria-label") || active.textContent || active.tagName).trim().replace(/\s+/g, " ").slice(0, 80) : "<none>",
      toggleCount: toggles.length,
      navCount: navs.length,
      navClass: nav?.className || "",
      bodyNavOpen: document.body.classList.contains("nav-open"),
      traceClicks: Number(window.__outpostKeyboardTraceClicks || 0),
    };
  });
}

for (const viewport of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 430, height: 900 },
]) {
  test(`${viewport.name}: all sitemap pages keep keyboard navigation contracts`, async ({ browser }) => {
    test.setTimeout(180_000);
    const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } });
    const page = await context.newPage();
    const failures = [];

    for (const pagePath of sitemapPaths()) {
      const response = await page.goto(`${origin}${pagePath}`, { waitUntil: "domcontentloaded", timeout: 20_000 });
      if (!response?.ok()) {
        failures.push(`${pagePath}: HTTP ${response?.status() ?? "no response"}`);
        continue;
      }
      await page.waitForTimeout(80);

      await checkSkipLink(page, pagePath, failures);

      if (viewport.name === "mobile") {
        await page.goto(`${origin}${pagePath}`, { waitUntil: "domcontentloaded", timeout: 20_000 });
        await page.waitForTimeout(80);

        const toggle = page.locator("[data-nav-toggle]");
        if (!(await toggle.count()) || !(await toggle.isVisible())) {
          failures.push(`${pagePath}: mobile nav toggle is not visible/reachable`);
        } else {
          const reached = await reachMobileToggle(page);
          if (!reached.reached) {
            failures.push(`${pagePath}: nav toggle is not reachable within first 10 Tab presses`);
          } else {
            await page.keyboard.press("Enter");
            await page.waitForTimeout(40);
            let state = await mobileNavState(page);
            if (state.expanded !== "true" || !state.visible) {
              failures.push(`${pagePath}: Enter on focused mobile toggle does not visibly open nav`);
            } else {
              await page.keyboard.press("Tab");
              state = await mobileNavState(page);
              if (!state.activeInsideNav) {
                failures.push(`${pagePath}: Tab after opening mobile nav does not enter nav (focus=${state.activeText})`);
              }

              await page.keyboard.press("Escape");
              await page.waitForTimeout(260);
              state = await mobileNavState(page);
              if (state.expanded !== "false" || state.visible) failures.push(`${pagePath}: Escape does not close mobile nav`);
              if (!state.activeIsToggle) failures.push(`${pagePath}: Escape leaves focus away from mobile toggle (focus=${state.activeText})`);

              if (state.activeIsToggle) {
                await page.evaluate(() => {
                  window.__outpostKeyboardTraceClicks = 0;
                  const active = document.activeElement;
                  if (active instanceof HTMLElement) {
                    active.addEventListener("click", () => { window.__outpostKeyboardTraceClicks += 1; }, { capture: true });
                  }
                });
                await page.keyboard.press("Space");
                await page.waitForTimeout(260);
                state = await mobileNavState(page);
                if (state.expanded !== "true" || !state.visible) {
                  failures.push(`${pagePath}: Space on focused mobile toggle does not visibly open nav (expanded=${state.expanded}, activeExpanded=${state.activeExpanded}, visible=${state.visible}, focusToggle=${state.activeIsToggle}, clicks=${state.traceClicks}, toggles=${state.toggleCount}, navs=${state.navCount}, navClass=${state.navClass}, bodyNavOpen=${state.bodyNavOpen}, focus=${state.activeText})`);
                }
                await page.keyboard.press("Escape");
              }
            }
          }
        }
      }

      const pageFailures = failures.filter((item) => item.startsWith(`${pagePath}:`));
      if (pageFailures.length) {
        await page.screenshot({ path: path.join(artifactRoot, `${viewport.name}-${slugFor(pagePath)}.png`), fullPage: false });
      }
    }

    await context.close();
    expect(failures, failures.join("\n")).toEqual([]);
  });
}
