import { test, expect } from "@playwright/test";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const siteRoot = path.join(repoRoot, "site");
const artifactRoot = path.join(repoRoot, "browser-ui-artifacts");
const origin = "http://127.0.0.1:4173";

const viewports = [
  { name: "desktop-1440", width: 1440, height: 1000 },
  { name: "desktop-edge-1121", width: 1121, height: 900 },
  { name: "laptop-1024", width: 1024, height: 900 },
  { name: "tablet-780", width: 780, height: 900 },
  { name: "mobile-430", width: 430, height: 900 },
  { name: "mobile-360", width: 360, height: 800 },
];

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
  [".exe", "application/octet-stream"],
  [".sha256", "text/plain; charset=utf-8"],
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
    const nested = path.join(siteRoot, clean, "index.html");
    if (fs.existsSync(nested) && fs.statSync(nested).isFile()) return nested;
  }
  return null;
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
      const fallback = path.join(siteRoot, "404.html");
      res.writeHead(404, { "content-type": "text/html; charset=utf-8" });
      res.end(fs.existsSync(fallback) ? fs.readFileSync(fallback) : "Not found");
      return;
    }

    const type = mime.get(path.extname(target).toLowerCase()) || "application/octet-stream";
    res.writeHead(200, { "content-type": type, "cache-control": "no-store" });
    if (req.method === "HEAD") res.end();
    else res.end(fs.readFileSync(target));
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(4173, "127.0.0.1", resolve);
  });
});

test.afterAll(async () => {
  if (server) await new Promise((resolve) => server.close(resolve));
});

function slugFor(pagePath) {
  return pagePath === "/" ? "home" : pagePath.replace(/^\//, "").replace(/[^a-zA-Z0-9_-]+/g, "-");
}

function overlaps(a, b) {
  const x = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  return x > 1 && y > 1;
}

async function exerciseHamburger(page, pageErrors, viewportWidth, tolerance) {
  const toggle = page.locator("[data-nav-toggle]");
  if (!(await toggle.count()) || !(await toggle.isVisible())) {
    pageErrors.push("hamburger is expected but is not visibly actionable");
    return;
  }

  await toggle.click({ timeout: 2500 });
  await page.waitForTimeout(80);
  const openState = await page.evaluate(() => {
    const nav = document.querySelector("[data-nav]");
    const toggleElement = document.querySelector("[data-nav-toggle]");
    if (!nav || !toggleElement) return null;
    const style = getComputedStyle(nav);
    const r = nav.getBoundingClientRect();
    const visible = style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0.01 && r.width > 0 && r.height > 0;
    return {
      visible,
      expanded: toggleElement.getAttribute("aria-expanded"),
      left: r.left,
      right: r.right,
      height: r.height,
    };
  });

  if (!openState || !openState.visible || openState.expanded !== "true") pageErrors.push("hamburger does not open navigation visibly");
  else if (openState.left < -tolerance || openState.right > viewportWidth + tolerance) pageErrors.push("opened mobile navigation is clipped horizontally");

  await page.keyboard.press("Escape");
  await page.waitForTimeout(50);
  const closed = await toggle.getAttribute("aria-expanded");
  if (closed !== "false") pageErrors.push("Escape does not close mobile navigation");
}


test("changelog: hero copy and actions use styled responsive layout", async ({ browser }) => {
  for (const width of [1366, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 800 } });
    const page = await context.newPage();
    await page.goto(origin + "/changelog", { waitUntil: "domcontentloaded" });
    const hero = page.locator(".changelog-hero");
    const primary = hero.getByRole("link", { name: /^Завантажити v\d+\.\d+\.\d+$/ });
    const secondary = hero.getByRole("link", { name: "Усі можливості" });
    await expect(hero.getByRole("heading", { name: "Історія версій OutPOSt" })).toBeVisible();
    await expect(primary).toBeVisible();
    await expect(secondary).toBeVisible();
    const layout = await page.evaluate(() => {
      const hero = document.querySelector(".changelog-hero");
      const main = document.querySelector(".changelog-hero-inner");
      const firstButton = document.querySelector(".changelog-primary");
      const header = document.querySelector(".topbar");
      const bounds = node => node.getBoundingClientRect();
      return {
        heroBackground: getComputedStyle(hero).backgroundColor,
        buttonDisplay: getComputedStyle(firstButton).display,
        buttonColor: getComputedStyle(firstButton).color,
        paddingLeft: bounds(main).left,
        buttonLeft: bounds(firstButton).left,
        buttonRight: bounds(firstButton).right,
        headerHeight: bounds(header).height,
      };
    });
    expect(layout.heroBackground).not.toBe("rgba(0, 0, 0, 0)");
    expect(["flex", "inline-flex"]).toContain(layout.buttonDisplay);
    expect(layout.paddingLeft).toBeGreaterThanOrEqual(8);
    expect(layout.buttonLeft).toBeGreaterThanOrEqual(4);
    expect(layout.buttonRight).toBeLessThanOrEqual(width - 4);
    expect(layout.headerHeight).toBeLessThan(100);
    await context.close();
  }
});

test("visual tour: all 18 screenshots open in one keyboard-accessible gallery", async ({ browser }) => {
  for (const width of [1366, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 800 } });
    const page = await context.newPage();
    await page.goto(origin + "/interfeis", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("РЕАЛЬНІ ЕКРАНИ OUTPOST")).toBeVisible();
    await expect(page.getByText("РЕАЛЬНІ ЕКРАНИ ФУНКЦІЙ")).toBeVisible();
    await expect(page.locator(".tour-integrations a[href='/oblik-tovariv-u-magazyni']")).toHaveCount(1);
    await expect(page.locator(".tour-integrations a[href='/avtomatyzatsiya-zakupivel-i-skladu']")).toHaveCount(1);
    await expect(page.locator(".tour-integrations a[href='/avtomatyzatsiya-rozdribnoi-torgivli']")).toHaveCount(1);
    const pageOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(pageOverflow).toBeLessThanOrEqual(1);
    const links = page.locator("a[data-tour-gallery]");
    await expect(links).toHaveCount(18);
    expect(await links.evaluateAll(elements => elements.every(e => !e.hasAttribute("target")))).toBe(true);
    const first = links.first();
    await first.click();
    const lightbox = page.locator("[data-tour-lightbox]");
    await expect(lightbox).toBeVisible();
    await expect(page.locator("[data-tour-count]")).toHaveText("Скріншот 1 із 18");
    await page.getByRole("button", { name: "Наступний скріншот" }).click();
    await expect(page.locator("[data-tour-count]")).toHaveText("Скріншот 2 із 18");
    await page.keyboard.press("ArrowLeft");
    await expect(page.locator("[data-tour-count]")).toHaveText("Скріншот 1 із 18");
    await page.getByRole("button", { name: /^Показати 5:/ }).click();
    await expect(page.locator("[data-tour-count]")).toHaveText("Скріншот 5 із 18");
    const sizing = await lightbox.evaluate(element => {
      const r = element.getBoundingClientRect();
      return { left:r.left, right:r.right, top:r.top, bottom:r.bottom };
    });
    expect(sizing.left).toBeGreaterThanOrEqual(-2);
    expect(sizing.right).toBeLessThanOrEqual(width + 2);
    await page.keyboard.press("Escape");
    await expect(lightbox).not.toBeVisible();
    await expect(first).toBeFocused();
    await context.close();
  }
});

for (const viewport of viewports) {
  test(`${viewport.name}: all sitemap pages keep responsive layout contracts`, async ({ browser }) => {
    test.setTimeout(180_000);
    const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } });
    const page = await context.newPage();
    const failures = [];
    const paths = sitemapPaths();

    for (const pagePath of paths) {
      const pageErrors = [];
      const onPageError = (error) => pageErrors.push(`uncaught JS error: ${error.message}`);
      page.on("pageerror", onPageError);

      const response = await page.goto(`${origin}${pagePath}`, { waitUntil: "domcontentloaded", timeout: 20_000 });
      if (!response || !response.ok()) pageErrors.push(`HTTP ${response?.status() ?? "no response"}`);
      await page.waitForTimeout(120);

      const metrics = await page.evaluate(() => {
        const rect = (element) => {
          if (!element) return null;
          const r = element.getBoundingClientRect();
          return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
        };
        const visible = (element) => {
          if (!element) return false;
          const style = getComputedStyle(element);
          const r = element.getBoundingClientRect();
          return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0.01 && r.width > 0 && r.height > 0;
        };

        const header = document.querySelector("[data-header]");
        const nav = document.querySelector("[data-nav]");
        const navToggle = document.querySelector("[data-nav-toggle]");
        const brand = document.querySelector(".brand");
        const menu = document.querySelector(".nav-more-menu");
        const menuStyle = menu ? getComputedStyle(menu) : null;

        const controls = [...document.querySelectorAll(".button, .nav-download, [data-nav-toggle]")]
          .filter(visible)
          .map((element) => ({ label: (element.textContent || element.getAttribute("aria-label") || element.className).trim().slice(0, 80), box: rect(element) }));

        const images = [...document.images]
          .filter((img) => img.complete && img.naturalWidth === 0)
          .map((img) => img.getAttribute("src") || img.getAttribute("alt") || "<image>");

        const distortedImages = [...document.images]
          .filter((img) => visible(img) && img.complete && img.naturalWidth > 0 && img.naturalHeight > 0)
          .map((img) => {
            const naturalRatio = img.naturalWidth / img.naturalHeight;
            const renderedRatio = img.clientWidth / img.clientHeight;
            const drift = Math.abs(renderedRatio / naturalRatio - 1);
            return {
              src: img.getAttribute("src") || img.getAttribute("alt") || "<image>",
              natural: `${img.naturalWidth}x${img.naturalHeight}`,
              rendered: `${img.clientWidth}x${img.clientHeight}`,
              drift,
              objectFit: getComputedStyle(img).objectFit,
            };
          })
          .filter((img) => img.objectFit === "fill" && img.drift > 0.02);

        const desktopItems = nav && visible(nav)
          ? [...nav.children].filter(visible).map((element) => ({ label: (element.textContent || element.tagName).trim().replace(/\s+/g, " ").slice(0, 60), box: rect(element) }))
          : [];

        return {
          htmlScrollWidth: document.documentElement.scrollWidth,
          bodyScrollWidth: document.body.scrollWidth,
          header: rect(header),
          nav: rect(nav),
          navVisible: visible(nav),
          navToggleVisible: visible(navToggle),
          brand: rect(brand),
          menuPresent: Boolean(menu),
          menuVisibility: menuStyle?.visibility ?? null,
          menuOpacity: menuStyle ? Number(menuStyle.opacity) : null,
          controls,
          brokenImages: images,
          distortedImages,
          desktopItems,
        };
      });

      const tolerance = 2;
      if (metrics.htmlScrollWidth > viewport.width + tolerance || metrics.bodyScrollWidth > viewport.width + tolerance) {
        pageErrors.push(`horizontal overflow: html=${metrics.htmlScrollWidth}px body=${metrics.bodyScrollWidth}px viewport=${viewport.width}px`);
      }
      if (!metrics.header) pageErrors.push("site header missing");
      else {
        if (metrics.header.height > 100) pageErrors.push(`header too tall while closed: ${metrics.header.height.toFixed(1)}px`);
        if (metrics.header.left < -tolerance || metrics.header.right > viewport.width + tolerance) pageErrors.push("header extends beyond viewport");
      }
      if (!metrics.brand || metrics.brand.left < -tolerance || metrics.brand.right > viewport.width + tolerance) pageErrors.push("brand is clipped or missing");
      for (const control of metrics.controls) {
        if (!control.box) continue;
        if (control.box.left < -tolerance || control.box.right > viewport.width + tolerance) {
          pageErrors.push(`visible control clipped horizontally: ${control.label} (${control.box.left.toFixed(1)}..${control.box.right.toFixed(1)})`);
        }
      }
      if (metrics.brokenImages.length) pageErrors.push(`broken images: ${metrics.brokenImages.join(", ")}`);
      if (metrics.distortedImages.length) {
        pageErrors.push(
          `distorted images: ${metrics.distortedImages.map((img) => `${img.src} natural=${img.natural} rendered=${img.rendered} drift=${(img.drift * 100).toFixed(2)}%`).join(", ")}`
        );
      }

      if (viewport.width > 1120) {
        if (!metrics.navVisible) pageErrors.push("desktop navigation is not visibly available");
        if (metrics.navToggleVisible) pageErrors.push("hamburger is visible above desktop breakpoint");
        if (metrics.menuPresent && (metrics.menuVisibility !== "hidden" || (metrics.menuOpacity ?? 1) > 0.05)) {
          pageErrors.push(`desktop nav-more menu is visible while closed (visibility=${metrics.menuVisibility}, opacity=${metrics.menuOpacity})`);
        }
        if (metrics.brand && metrics.nav && overlaps(metrics.brand, metrics.nav)) pageErrors.push("brand overlaps desktop navigation");
        for (let i = 0; i < metrics.desktopItems.length; i += 1) {
          for (let j = i + 1; j < metrics.desktopItems.length; j += 1) {
            if (overlaps(metrics.desktopItems[i].box, metrics.desktopItems[j].box)) {
              pageErrors.push(`desktop nav items overlap: ${metrics.desktopItems[i].label} / ${metrics.desktopItems[j].label}`);
            }
          }
        }

        const more = page.locator("[data-nav-more]");
        if (await more.count()) {
          await more.hover();
          await page.waitForTimeout(240);
          const openMenu = await page.locator(".nav-more-menu").evaluate((element) => {
            const style = getComputedStyle(element);
            const r = element.getBoundingClientRect();
            return { visibility: style.visibility, opacity: Number(style.opacity), left: r.left, right: r.right, width: r.width, height: r.height };
          });
          if (openMenu.visibility === "hidden" || openMenu.opacity < 0.9 || openMenu.width <= 0 || openMenu.height <= 0) {
            pageErrors.push("desktop nav-more menu does not open on hover");
          }
          if (openMenu.left < -tolerance || openMenu.right > viewport.width + tolerance) {
            pageErrors.push(`desktop nav-more menu is clipped (${openMenu.left.toFixed(1)}..${openMenu.right.toFixed(1)} of ${viewport.width})`);
          }
          await page.mouse.move(1, viewport.height - 1);
          await page.waitForTimeout(220);
        }
      } else if (metrics.menuPresent) {
        // Pages using the shared nav-more contract switch to hamburger at <=1120px.
        if (!metrics.navToggleVisible) pageErrors.push("shared navigation hamburger is hidden at <=1120px");
        if (metrics.navVisible) pageErrors.push("shared mobile navigation is visibly open before hamburger activation");
        if (metrics.navToggleVisible) await exerciseHamburger(page, pageErrors, viewport.width, tolerance);
      } else {
        // A page may have its own narrower breakpoint (Support Center currently does).
        // Accept desktop navigation while it fits; once its hamburger becomes visible, require a genuinely closed nav.
        if (metrics.navToggleVisible) {
          if (metrics.navVisible) pageErrors.push("custom mobile navigation is visibly open before hamburger activation");
          await exerciseHamburger(page, pageErrors, viewport.width, tolerance);
        } else if (!metrics.navVisible) {
          pageErrors.push("neither desktop navigation nor a visible hamburger is available");
        }
      }

      if (pageErrors.length) {
        const screenshot = path.join(artifactRoot, `${viewport.name}-${slugFor(pagePath)}.png`);
        await page.screenshot({ path: screenshot, fullPage: true });
        failures.push(`${pagePath}: ${pageErrors.join("; ")}`);
      }
      page.off("pageerror", onPageError);
    }

    await context.close();
    expect(failures, failures.join("\n")).toEqual([]);
  });
}

test("interface page exposes eight real director and payroll screenshots", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/interfeis", {waitUntil:"load"});
    await expect(page.locator("#director-v02422")).toContainText("10 директорських розділів");
    await expect(page.locator("#payroll-v02422")).toContainText("600 грн");
    await expect(page.locator("#payroll-history-v02422")).toContainText("управлінський розрахунок винагороди");
    const directorShots = page.locator('a[data-tour-gallery][href*="/02422/director-payroll/"]');
    await expect(directorShots).toHaveCount(8);
    await expect(page.locator(".tour-lightbox-bar strong")).toHaveText("OutPOSt · Реальні скріншоти");
    const first = directorShots.first();
    await first.click();
    const dialog = page.locator("dialog.tour-lightbox");
    await expect(dialog).toBeVisible();
    await expect(dialog.locator("[data-tour-image]")).toHaveAttribute("src", /\/02422\/director-payroll\/01-ohliad-dyrektora\.webp$/);
    await dialog.locator("[data-tour-close]").click();
    await expect(dialog).toBeHidden();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("small-shop, FOP and offline pages reflect current batch capabilities", async ({page}) => {
  const cases = [
    {path:"/programa-dlya-nevelykogo-magazynu",expect:["FEFO-контроль","автоматично створити партію","59 українських тем"]},
    {path:"/programa-dlya-fop",expect:["партійний контур охоплює автооблік нових партій","повернення відновлює вихідні партії","списання конкретних партій підтримується","партійна інвентаризація конкретних партій поки потребує окремої звірки"]},
    {path:"/offline-programa-dlya-magazynu",expect:["FEFO-контролю","Автооблік нових партій","Модульна «Справка»","явні партійні переміщення та списання","потрібна повна звірка партій"]},
  ];
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    for (const item of cases) {
      await page.goto(origin + item.path, {waitUntil:"load"});
      for (const phrase of item.expect) await expect(page.locator("main")).toContainText(phrase);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(1);
    }
  }
});

test("cashier page documents current FEFO while keeping older base-sale screenshots explicit", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/programa-dlya-kasy-windows", {waitUntil:"load"});
    await expect(page.getByRole("heading",{name:"FEFO-контроль партій"})).toBeVisible();
    await expect(page.locator(".scenario-section").first()).toContainText("Прострочені партії не використовуються");
    await expect(page.locator(".scenario-section").first()).toContainText("Повернення відновлює саме ті вихідні партії");
    await expect(page.locator(".scenario-section").first()).toContainText("Переміщення та списання конкретних партій уже підтримуються");
    const tour = page.locator(".feature-tour");
    await expect(tour.locator(".tour-eyebrow")).toHaveText("БАЗОВИЙ КАСОВИЙ СЦЕНАРІЙ");
    await expect(tour).toContainText("Цей самий шлях також враховує акції, бонуси та FEFO-контроль");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("shared real screenshot carousels have equal-sized stages and same-page lightbox", async ({page}) => {
  const cases = [
    {path:"/modules",groups:[7,8]},
    {path:"/avtomatyzatsiya-magazynu",groups:[4,8]},
    {path:"/features",groups:[7]},
    {path:"/prodazh-v-borg",groups:[7,1]},
    {path:"/programa-dlya-fop",groups:[5]},
    {path:"/programa-dlya-nevelykogo-magazynu",groups:[6]},
    {path:"/offline-programa-dlya-magazynu",groups:[5]},
    {path:"/support",groups:[1]},
    {path:"/oblik-tovariv-u-magazyni",groups:[5,8,6]},
    {path:"/avtomatyzatsiya-zakupivel-i-skladu",groups:[6,6]},
    {path:"/avtomatyzatsiya-rozdribnoi-torgivli",groups:[6]},
    {path:"/programa-dlya-kasy-windows",groups:[6]},
    {path:"/mini-t400",groups:[3]},
    {path:"/prro",groups:[2]},
    {path:"/prro-checkbox",groups:[2]},
    {path:"/eakcyz",groups:[2]},
    {path:"/tsinnyky-ta-etyketky",groups:[3]},
    {path:"/bezkoshtovna-programa-dlya-magazynu",groups:[4]},
  ];
  await page.setViewportSize({width:1280,height:900});
  for (const item of cases) {
    await page.goto(origin + item.path, {waitUntil:"load"});
    const groups = page.locator(".feature-tour .live-shot-carousel");
    await expect(groups).toHaveCount(item.groups.length);
    for (const [groupIndex,n] of item.groups.entries()) {
      const carousel = groups.nth(groupIndex);
      const figures = carousel.locator("figure");
      await expect(figures).toHaveCount(n);
      await expect(figures.first()).toBeVisible();
      const box = await figures.first().boundingBox();
      expect(box?.height).toBeGreaterThanOrEqual(465);
      if (n > 1) {
        await carousel.locator(".live-shot-next").click();
        await expect(figures.nth(1)).toBeVisible();
        await expect(figures.first()).toBeHidden();
        const second = await figures.nth(1).boundingBox();
        expect(Math.abs(second.height - box.height), `${item.path} carousel ${groupIndex + 1}: first=${box.height}px second=${second.height}px`).toBeLessThanOrEqual(2);
        await expect(carousel.locator(".live-shot-counter")).toHaveText("Крок 2 із " + n);
      }
      const current = figures.nth(n > 1 ? 1 : 0);
      const opener = current.locator("a:has(img)").first();
      expect(await opener.getAttribute("target")).toBeNull();
      await opener.click();
      const dialog = page.locator("dialog.live-shot-dialog");
      await expect(dialog).toBeVisible();
      await expect(dialog.locator("img")).toHaveJSProperty("complete", true);
      await dialog.locator(".live-shot-dialog-close").click();
      await expect(dialog).toBeHidden();
      await expect(opener).toBeFocused();
    }
  }
});


test("veteran license page shows the full product without document imagery", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/bezkoshtovna-programa-dlya-magazynu", {waitUntil:"load"});
    const tour = page.locator(".feature-tour");
    await expect(tour).toHaveCount(1);
    await expect(tour).toContainText("Пільгова ліцензія відкриває той самий повний продукт");
    await expect(tour.locator("img")).toHaveCount(4);
    await expect(tour.locator("img[src='/assets/screenshots/02410/overview.webp']")).toHaveCount(1);
    await expect(tour.locator("img[src='/assets/screenshots/02410/sales.webp']")).toHaveCount(1);
    await expect(tour.locator("img[src='/assets/screenshots/02410/products.webp']")).toHaveCount(1);
    await expect(tour.locator("img[src='/assets/screenshots/02410/reports.webp']")).toHaveCount(1);
    await expect(tour).toContainText("немає документів для підтвердження пільги чи персональних даних");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("fiscal screenshots stay assigned to the correct provider", async ({page}) => {
  await page.setViewportSize({width:1280,height:900});

  await page.goto(origin + "/prro-checkbox", {waitUntil:"load"});
  await expect(page.locator(".feature-tour img[src='/assets/screenshots/02410/checkbox/01-settings-entry.webp']")).toHaveCount(1);
  await expect(page.locator(".feature-tour img[src='/assets/screenshots/02410/checkbox/02-control-center.webp']")).toHaveCount(1);
  await expect(page.locator(".feature-tour")).toContainText("Точка входу");
  await expect(page.locator(".feature-tour")).toContainText("CheckBox Control Center");
  await expect(page.locator(".feature-tour")).toContainText("станом касира");

  await page.goto(origin + "/prro", {waitUntil:"load"});
  await expect(page.locator(".feature-tour img[src='/assets/screenshots/02410/checkbox/02-control-center.webp']")).toHaveCount(0);
  await expect(page.locator(".feature-tour img[src='/assets/screenshots/02410/prro/01-control-center.webp']")).toHaveCount(0);
  await expect(page.locator(".feature-tour img[src='/assets/screenshots/02410/prro/02-routing.webp']")).toHaveCount(1);
  await expect(page.locator(".feature-tour img[src='/assets/screenshots/02410/prro/03-cashier-preflight.webp']")).toHaveCount(1);

  await page.goto(origin + "/features", {waitUntil:"load"});
  await expect(page.locator(".feature-tour img[src='/assets/screenshots/02410/prro/02-routing.webp']")).toHaveCount(1);
  await expect(page.locator(".feature-tour img[src='/assets/screenshots/02410/prro/01-control-center.webp']")).toHaveCount(0);
});

test("goods accounting page explains local multiwarehouse transfers without cloud overclaim", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/oblik-tovariv-u-magazyni", {waitUntil:"load"});
    const section = page.locator(".scenario-section").filter({hasText:"03 · КІЛЬКА ЛОКАЛЬНИХ СКЛАДІВ"});
    await expect(section).toHaveCount(1);
    await expect(section).toContainText("стан «у дорозі» й часткове приймання");
    await expect(section).toContainText("однієї локальної бази OutPOSt");
    await expect(section).toContainText("Чернетка без прихованого резерву");
    await expect(section).toContainText("Часткове приймання");
    await expect(section).toContainText("проведене відправлення не реверсується цим сценарієм");
    await expect(section).toContainText("для партійного переміщення конкретні партії вибираються явно");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("batch FEFO walkthrough keeps eight FEFO stages with current boundaries", async ({page}) => {
  await page.setViewportSize({width:1280,height:900});
  await page.goto(origin + "/oblik-tovariv-u-magazyni", {waitUntil:"load"});
  const tour = page.locator(".feature-tour.batch-expiry-slider");
  const slider = tour.locator(".live-shot-carousel");
  const figures = slider.locator("figure.tour-shot");
  await expect(figures).toHaveCount(8);
  await expect(slider.locator(".live-shot-dots")).toHaveCount(0);
  await expect(tour.getByText("Партії, FEFO-продаж і повернення — від закупівлі до історії")).toBeVisible();
  await expect(tour.locator(".tour-eyebrow")).toHaveText("РЕАЛЬНИЙ СЦЕНАРІЙ · ПАРТІЇ ТА FEFO");
  await expect(tour.locator(".tour-note")).toContainText("ідентифікація фізичної упаковки");
  await expect(tour.locator(".tour-note")).toContainText("явне переміщення");
  await expect(tour.locator(".tour-note")).toContainText("списання конкретних партій");
  await expect(tour.locator(".tour-note")).toContainText("інвентаризація конкретних партій");
  const heights = [];
  for (let i=0;i<8;i++) {
    if (i) await slider.locator(".live-shot-next").click();
    await expect(figures.nth(i)).toBeVisible();
    await expect(slider.locator(".live-shot-counter")).toHaveText("Крок " + (i + 1) + " із 8");
    const figBox = await figures.nth(i).boundingBox();
    const imageBox = await figures.nth(i).locator("a:has(img)").boundingBox();
    const captionBox = await figures.nth(i).locator("figcaption").boundingBox();
    expect(captionBox.y).toBeGreaterThanOrEqual(imageBox.y + imageBox.height - 2);
    expect(await figures.nth(i).locator("figcaption").evaluate(el => getComputedStyle(el).textAlign)).toBe("center");
    heights.push(figBox.height);
    const opener = figures.nth(i).locator("a:has(img)");
    expect(await opener.getAttribute("target")).toBeNull();
    await opener.click({position:{x:Math.round(imageBox.width/2),y:Math.round(imageBox.height/2)}});
    const viewer = page.locator("dialog.live-shot-dialog");
    await expect(viewer).toBeVisible();
    await expect(viewer.locator("img")).toHaveAttribute("src", new RegExp("/02423/batch-fefo/"));
    await viewer.locator(".live-shot-dialog-close").click();
    await expect(viewer).toBeHidden();
  }
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(3);
  await expect(slider.locator(".live-shot-next")).toBeDisabled();
});

test("writeoff walkthrough shows six real batch stages and same-page lightbox", async ({page}) => {
  await page.setViewportSize({width:1280,height:900});
  await page.goto(origin + "/oblik-tovariv-u-magazyni", {waitUntil:"load"});
  const tour = page.locator(".feature-tour.writeoff-batch-slider");
  const slider = tour.locator(".live-shot-carousel");
  const figures = slider.locator("figure.tour-shot");
  await expect(figures).toHaveCount(6);
  await expect(slider.locator(".live-shot-dots")).toHaveCount(0);
  await expect(tour.getByText("Списання конкретних партій — від документа до контрольованого скасування")).toBeVisible();
  await expect(tour.locator(".tour-eyebrow")).toHaveText("РЕАЛЬНИЙ СЦЕНАРІЙ · СПИСАННЯ ПАРТІЙ");
  await expect(tour.locator(".tour-note")).toContainText("явний вибір конкретних партій");
  await expect(tour.locator(".tour-note")).toContainText("Cabinet, D1 і хмарна статистика не використовувалися");
  const heights = [];
  for (let i=0;i<6;i++) {
    if (i) await slider.locator(".live-shot-next").click();
    await expect(figures.nth(i)).toBeVisible();
    await expect(slider.locator(".live-shot-counter")).toHaveText("Крок " + (i + 1) + " із 6");
    const figBox = await figures.nth(i).boundingBox();
    const imageBox = await figures.nth(i).locator("a:has(img)").boundingBox();
    const captionBox = await figures.nth(i).locator("figcaption").boundingBox();
    expect(captionBox.y).toBeGreaterThanOrEqual(imageBox.y + imageBox.height - 2);
    expect(await figures.nth(i).locator("figcaption").evaluate(el => getComputedStyle(el).textAlign)).toBe("center");
    heights.push(figBox.height);
    const opener = figures.nth(i).locator("a:has(img)");
    expect(await opener.getAttribute("target")).toBeNull();
    await opener.click({position:{x:Math.round(imageBox.width/2),y:Math.round(imageBox.height/2)}});
    const viewer = page.locator("dialog.live-shot-dialog");
    await expect(viewer).toBeVisible();
    await expect(viewer.locator("img")).toHaveAttribute("src", new RegExp("/02426/writeoff/"));
    await viewer.locator(".live-shot-dialog-close").click();
    await expect(viewer).toBeHidden();
  }
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(3);
  await expect(slider.locator(".live-shot-next")).toBeDisabled();
});

test("purchasing workflow shows six real stages in the finalized single-stage carousel", async ({page}) => {
  await page.setViewportSize({width:1280,height:900});
  await page.goto(origin + "/avtomatyzatsiya-zakupivel-i-skladu", {waitUntil:"load"});
  const tour = page.locator(".feature-tour.purchasing-single-slider");
  const slider = tour.locator(".live-shot-carousel");
  const figures = slider.locator("figure.tour-shot");
  await expect(figures).toHaveCount(6);
  await expect(slider.locator(".live-shot-dots")).toHaveCount(0);
  await expect(tour.getByText("Від плану поповнення до часткового приймання")).toBeVisible();
  await expect(tour.locator(".tour-eyebrow")).toHaveText("РЕАЛЬНИЙ СЦЕНАРІЙ · ЗАКУПІВЛІ ТА ПРИЙМАННЯ");
  const heights = [];
  for (let i=0;i<6;i++) {
    if (i) await slider.locator(".live-shot-next").click();
    await expect(figures.nth(i)).toBeVisible();
    await expect(slider.locator(".live-shot-counter")).toHaveText("Крок " + (i + 1) + " із 6");
    const figBox = await figures.nth(i).boundingBox();
    const imageBox = await figures.nth(i).locator("a:has(img)").boundingBox();
    const captionBox = await figures.nth(i).locator("figcaption").boundingBox();
    expect(captionBox.y).toBeGreaterThanOrEqual(imageBox.y + imageBox.height - 2);
    expect(await figures.nth(i).locator("figcaption").evaluate(el => getComputedStyle(el).textAlign)).toBe("center");
    heights.push(figBox.height);
    const opener = figures.nth(i).locator("a:has(img)");
    await opener.click({position:{x:Math.round(imageBox.width/2),y:Math.round(imageBox.height/2)}});
    const viewer = page.locator("dialog.live-shot-dialog");
    await expect(viewer).toBeVisible();
    await expect(viewer.locator("img")).toHaveAttribute("src", new RegExp("/02418/purchasing/"));
    await viewer.locator(".live-shot-dialog-close").click();
    await expect(viewer).toBeHidden();
  }
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(3);
  await expect(slider.locator(".live-shot-next")).toBeDisabled();
});

test("store automation page reflects current director and batch capabilities", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/avtomatyzatsiya-magazynu", {waitUntil:"load"});
    await expect(page.locator("main")).toContainText("Кабінет директора працює локально");
    await expect(page.locator("main")).toContainText("Управлінська зарплатня");
    await expect(page.locator("main")).toContainText("8 модульних напрямків");
    await expect(page.locator("main")).toContainText("Замовлення постачальникам.");
    await expect(page.locator("main")).toContainText("Автопоповнення.");
    await expect(page.locator("main")).toContainText("Вебкабінет і мережевий read-only контур");
    await expect(page.locator("main")).toContainText("Read-only вебкабінет — окремий local-first мережевий контур");
    await expect(page.locator("main")).toContainText("8 модульних напрямків");
    await expect(page.locator("main")).toContainText("FEFO-контроль продажів і повернень");
    await expect(page.locator("main")).toContainText("Партії, строки придатності та FEFO-контроль");
    await expect(page.locator("main")).toContainText("59 тем у 14 категоріях");
    await expect(page.locator("main")).toContainText("явні переміщення та списання конкретних партій");
    const directorTour = page.locator("#director-payroll-tour");
    await expect(directorTour.getByRole("heading",{name:"Від огляду магазину до контрольованої виплати зарплатні"})).toBeVisible();
    await expect(directorTour.locator("figure.tour-shot")).toHaveCount(8);
    await expect(directorTour).toContainText("v0.24.22");
    await expect(directorTour).toContainText("Це управлінський розрахунок винагороди, а не податкова або кадрова звітність");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("small-shop and offline pages separate local director from web cabinet", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});

    await page.goto(origin + "/programa-dlya-nevelykogo-magazynu", {waitUntil:"load"});
    await expect(page.locator("main")).toContainText("Локальний Кабінет директора");
    await expect(page.locator("main")).toContainText("управлінська зарплатня");
    await expect(page.locator("main")).toContainText("web/network контур");

    await page.goto(origin + "/offline-programa-dlya-magazynu", {waitUntil:"load"});
    await expect(page.locator("main")).toContainText("Локальний Кабінет директора та управлінська зарплатня");
    await expect(page.locator("main")).toContainText("Read-only вебкабінет власника та мережевий контур");
    await expect(page.locator("main")).not.toContainText("Онлайн — тільки за потреби: CheckBox / Native ПРРО, Кабінет директора");

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("FOP page presents director and payroll as management features", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/programa-dlya-fop", {waitUntil:"load"});
    await expect(page.locator("main")).toContainText("Локальний Кабінет директора");
    await expect(page.locator("main")).toContainText("10 розділів");
    await expect(page.locator("main")).toContainText("Управлінська зарплатня");
    await expect(page.locator("main")).toContainText("не заявляється як регламентований кадровий або податковий облік");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("homepage surfaces the current store-management capabilities", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/", {waitUntil:"load"});
    await expect(page.locator(".hero-copy")).toContainText("Кабінет директора");
    await expect(page.locator(".hero-copy")).toContainText("автопоповнення");
    await expect(page.locator(".hero-copy")).toContainText("FEFO-продаж і повернення");
    await expect(page.locator(".hero-copy")).toContainText("явні переміщення та списання конкретних партій");
    await expect(page.locator("#capabilities")).toContainText("акції, промокоди та бонуси");
    await expect(page.locator("#capabilities")).toContainText("кілька складів, переміщення");
    await expect(page.locator("#capabilities")).toContainText("часткове приймання");
    await expect(page.locator(".operations-strip")).toContainText("РОЗШИРЕНА АНАЛІТИКА");
    await expect(page.locator(".operations-strip")).toContainText("10 розділів і управлінська зарплатня");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("cashier and debt pages reflect the loyalty contract", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});

    await page.goto(origin + "/programa-dlya-kasy-windows", {waitUntil:"load"});
    await expect(page.locator("main")).toContainText("Акції та бонуси");
    await expect(page.locator("main")).toContainText("одна найвигідніша акція або ручна знижка");
    await expect(page.locator("main")).toContainText("1 бонус = 1 грн знижки");
    await expect(page.locator("main")).toContainText("це не окремий спосіб оплати");

    await page.goto(origin + "/prodazh-v-borg", {waitUntil:"load"});
    await expect(page.locator("main")).toContainText("Борг і бонусна програма");
    await expect(page.locator("main")).toContainText("лише на фактично оплачену частину чека");
    await expect(page.locator("main")).toContainText("Подальше погашення старого боргу також не нараховує бонуси");
    await expect(page.locator("main")).toContainText("Бонуси залишаються знижкою, а не способом оплати");

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("online demo is clearly separated from the full desktop product", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/demo", {waitUntil:"load"});
    await expect(page.locator(".demo-stability-notice")).toContainText("не відтворює всі можливості та зовнішній вигляд повної Windows-версії");
    await expect(page.locator(".demo-stability-notice")).toContainText("окремим приблизним preview");
    await expect(page.locator(".demo-webbar")).toContainText("preview, не версія Windows");
    await expect(page.locator(".app-version").first()).toHaveText("web demo · preview");
    await expect(page.getByText("OutPOSt v0.24.6")).toHaveCount(0);
    await expect(page.locator(".about-panel")).toContainText("Повна Windows-версія:");
    await expect(page.locator(".about-panel")).toContainText("окрема настільна програма");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("features page presents current inventory, FEFO, analytics and director workflows", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/features", {waitUntil:"load"});
    await expect(page.locator("#purchases")).toContainText("Замовлення постачальникам і автопоповнення");
    await expect(page.locator("#stock")).toContainText("Скасовану інвентаризацію можна повернути в чернетку");
    await expect(page.locator("#stock")).toContainText("Кілька локальних складів");
    await expect(page.locator("#stock")).toContainText("До 30 збережених наборів звіту");
    await expect(page.locator("#stock")).toContainText("FEFO");
    await expect(page.locator("#stock")).toContainText("Повернення відновлює саме початкові партії");
    await expect(page.locator("#management")).toContainText("10 розділів");
    await expect(page.locator("#management")).toContainText("Управлінська зарплатня");
    await expect(page.locator("#management")).toContainText("управлінський розрахунок");
    await expect(page.locator("#management")).toContainText("59 тем у 14 категоріях");
    await expect(page.locator("#management")).toContainText("кнопку «Справка»");
    await expect(page.locator("#modules")).toContainText("Вісім робочих модулів для щоденних задач магазину");
    await expect(page.locator("#modules")).toContainText("Партії, строки та FEFO");
    const featureTour = page.locator(".feature-tour");
    await expect(featureTour.locator("figure.tour-shot")).toHaveCount(7);
    await expect(featureTour.locator("img[src='/assets/screenshots/02422/director-payroll/01-ohliad-dyrektora.webp']")).toHaveCount(1);
    await expect(featureTour.locator("a[href='/interfeis#director-v02422']")).toHaveText("Повний директорський сценарій →");
    await expect(featureTour).toContainText("Локальний огляд, динаміка, результати продавців і управлінська зарплатня");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("modules page presents current module capabilities without milestone history", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/modules", {waitUntil:"load"});
    await expect(page.locator(".modules-grid .module-card")).toHaveCount(8);
    await expect(page.locator(".modules-detail .module-section")).toHaveCount(8);
    await expect(page.getByText("8 мають робочий контур")).toBeVisible();
    await expect(page.getByRole("link",{name:"Публічне завантаження"})).toHaveCount(2);
    await expect(page.getByText("7 напрямків продовжують розвиватися")).toHaveCount(0);
    await expect(page.getByText("Опис відповідає поточним можливостям програми")).toBeVisible();
    await expect(page.locator("#advanced-analytics .module-badge")).toHaveText("Робочий сценарій");
    await expect(page.locator("#batch-expiry .module-badge")).toHaveText("Робочий сценарій");
    await expect(page.locator("#batch-expiry")).toContainText("автоматичне створення партій");
    await expect(page.locator("#batch-expiry")).toContainText("FEFO під час продажу");
    await expect(page.locator("#batch-expiry")).toContainText("Повернення відновлює саме початкові партії");
    await expect(page.locator("#batch-expiry")).toContainText("переміщення та списання конкретних партій");
    await expect(page.locator("#promotions-loyalty .module-badge")).toHaveText("Робочий сценарій");
    await expect(page.locator("#multi-location-transfers .module-badge")).toHaveText("Робочий сценарій");
    await expect(page.locator("#director-network")).toContainText("ВЕБКАБІНЕТ І МЕРЕЖЕВИЙ КОНТУР");
    await expect(page.locator("#director-network")).toContainText("директорський workspace працює всередині Windows-програми");
    await expect(page.locator(".modules-hero")).toContainText("МОДУЛЬНИЙ ЦЕНТР");
    await expect(page.locator("#purchase-orders a[href='/avtomatyzatsiya-zakupivel-i-skladu']")).toHaveCount(1);
    await expect(page.locator("#promotions-loyalty a[href='/avtomatyzatsiya-rozdribnoi-torgivli']")).toHaveCount(1);
    await expect(page.locator("#batch-expiry a[href='#batch-registry-tour']")).toHaveCount(1);
    await expect(page.locator("#batch-registry-tour figure.tour-shot")).toHaveCount(7);
    await expect(page.locator("#batch-registry-tour")).toContainText("v0.24.19");
    await expect(page.locator("#batch-registry-tour .tour-note a[href='/oblik-tovariv-u-magazyni']")).toHaveCount(1);
    await expect(page.locator("#labels-printing a[href='/tsinnyky-ta-etyketky']")).toHaveCount(1);
    await expect(page.locator(".feature-tour img[src='/assets/screenshots/02414/labels/01-editor.webp']")).toHaveCount(1);
    await expect(page.locator(".feature-tour img[src='/assets/screenshots/02414/labels/02-library.webp']")).toHaveCount(1);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("labels page shows real editor and printing boundaries", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/tsinnyky-ta-etyketky", {waitUntil:"load"});
    await expect(page.getByRole("heading",{name:"Цінники та етикетки без зовнішнього дизайнера"})).toBeVisible();
    await expect(page.locator(".feature-tour img[src='/assets/screenshots/02414/labels/01-editor.webp']")).toHaveCount(1);
    await expect(page.locator(".feature-tour img[src='/assets/screenshots/02414/labels/02-library.webp']")).toHaveCount(1);
    await expect(page.locator(".feature-tour img[src='/assets/screenshots/02414/labels/03-purchase-print.webp']")).toHaveCount(1);
    for (const src of [
      "/assets/screenshots/02414/labels/01-editor.webp",
      "/assets/screenshots/02414/labels/02-library.webp",
      "/assets/screenshots/02414/labels/03-purchase-print.webp",
    ]) {
      const stats = await page.evaluate(async src => {
        const response = await fetch(src, {cache:"no-store"});
        if (!response.ok) throw new Error(`image fetch failed: ${response.status} ${src}`);
        const blob = await response.blob();
        const bitmap = await createImageBitmap(blob);
        const canvas = document.createElement("canvas");
        canvas.width = 32;
        canvas.height = 32;
        const ctx = canvas.getContext("2d", {willReadFrequently:true});
        ctx.drawImage(bitmap, 0, 0, 32, 32);
        const data = ctx.getImageData(0, 0, 32, 32).data;
        let min = 255, max = 0;
        const colors = new Set();
        for (let i=0;i<data.length;i+=4) {
          const lum = Math.round((data[i] + data[i+1] + data[i+2]) / 3);
          min = Math.min(min, lum);
          max = Math.max(max, lum);
          colors.add(`${data[i]}:${data[i+1]}:${data[i+2]}`);
        }
        const result = {width:bitmap.width,height:bitmap.height,range:max-min,colors:colors.size,bytes:blob.size};
        bitmap.close();
        return result;
      }, src);
      expect(stats.width).toBeGreaterThanOrEqual(750);
      expect(stats.height).toBeGreaterThanOrEqual(500);
      expect(stats.bytes).toBeGreaterThanOrEqual(18000);
      expect(stats.range).toBeGreaterThanOrEqual(60);
      expect(stats.colors).toBeGreaterThanOrEqual(40);
    }
    await expect(page.locator(".feature-tour")).toContainText("Друк із закупівлі");
    await expect(page.locator("main")).toContainText("Code128");
    await expect(page.locator("main")).toContainText("A4 або рулонний формат");
    await expect(page.locator("main")).toContainText("Друк залежить від фізичного принтера та його драйвера");
    await expect(page.locator("a[href='/modules#labels-printing']")).toHaveCount(1);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("procurement page explains automatic batches and batch boundaries", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/avtomatyzatsiya-zakupivel-i-skladu", {waitUntil:"load"});
    const section = page.locator("#batch-fefo");
    await expect(section).toHaveCount(1);
    await expect(section).toContainText("04 · ПАРТІЇ ТА FEFO");
    await expect(section).toContainText("Автооблік не вмикається сам");
    await expect(section).toContainText("Прострочені партії не використовуються");
    await expect(section).toContainText("Повернення відновлює саме початкові партії");
    await expect(section).toContainText("Партійна інвентаризація конкретних партій поки не заявляється як завершений сценарій");
    await expect(section).toContainText("59 тем у 14 категоріях");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("multiwarehouse walkthrough shows six real stages with local-database boundaries", async ({page}) => {
  await page.setViewportSize({width:1280,height:900});
  await page.goto(origin + "/avtomatyzatsiya-zakupivel-i-skladu", {waitUntil:"load"});
  const tour = page.locator(".feature-tour.multiwarehouse-single-slider");
  const slider = tour.locator(".live-shot-carousel");
  const figures = slider.locator("figure.tour-shot");
  await expect(figures).toHaveCount(6);
  await expect(slider.locator(".live-shot-dots")).toHaveCount(0);
  await expect(tour.getByText("Від чернетки переміщення до часткового приймання")).toBeVisible();
  await expect(tour.locator(".tour-eyebrow")).toHaveText("РЕАЛЬНИЙ СЦЕНАРІЙ · ПЕРЕМІЩЕННЯ МІЖ СКЛАДАМИ");
  await expect(tour.locator(".tour-note")).toContainText("однієї локальної бази OutPOSt");
  await expect(tour.locator(".tour-note")).toContainText("не є залишком складу-одержувача");
  await expect(tour.locator(".tour-note")).toContainText("не скасовується");
  const heights = [];
  for (let i=0;i<6;i++) {
    if (i) await slider.locator(".live-shot-next").click();
    await expect(figures.nth(i)).toBeVisible();
    await expect(slider.locator(".live-shot-counter")).toHaveText("Крок " + (i + 1) + " із 6");
    const figBox = await figures.nth(i).boundingBox();
    const imageBox = await figures.nth(i).locator("a:has(img)").boundingBox();
    const captionBox = await figures.nth(i).locator("figcaption").boundingBox();
    expect(captionBox.y).toBeGreaterThanOrEqual(imageBox.y + imageBox.height - 2);
    expect(await figures.nth(i).locator("figcaption").evaluate(el => getComputedStyle(el).textAlign)).toBe("center");
    heights.push(figBox.height);
    const opener = figures.nth(i).locator("a:has(img)");
    expect(await opener.getAttribute("target")).toBeNull();
    await opener.click({position:{x:Math.round(imageBox.width/2),y:Math.round(imageBox.height/2)}});
    const viewer = page.locator("dialog.live-shot-dialog");
    await expect(viewer).toBeVisible();
    await expect(viewer.locator("img")).toHaveAttribute("src", new RegExp("/02421/multiwarehouse/"));
    await viewer.locator(".live-shot-dialog-close").click();
    await expect(viewer).toBeHidden();
  }
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(3);
  await expect(slider.locator(".live-shot-next")).toBeDisabled();
});

test("retail automation page reflects FEFO, director and payroll workflows", async ({page}) => {
  for (const width of [1280,390]) {
    await page.setViewportSize({width,height:900});
    await page.goto(origin + "/avtomatyzatsiya-rozdribnoi-torgivli", {waitUntil:"load"});
    const management = page.locator(".scenario-section").filter({hasText:"05 · КЕРУВАННЯ І ПРОДАВЦІ"});
    await expect(management).toHaveCount(1);
    await expect(management).toContainText("10 директорських розділів");
    await expect(management).toContainText("Управлінська зарплатня");
    await expect(management).toContainText("Самовиплата продавцем вимкнена за замовчуванням");
    await expect(management).toContainText("зарплатний блок — управлінський");
    await expect(management).toContainText("59 тем у 14 категоріях");
    await expect(page.locator("main")).toContainText("FEFO-контроль партій");
    await expect(page.locator("main")).toContainText("Прострочені партії не використовуються");
    await expect(page.locator("main")).toContainText("повернення відновлює саме початкові партії продажу");
    await expect(page.locator("main")).toContainText("Автооблік партій");
    await expect(page.locator("main")).toContainText("Не вмикається сам після оновлення");
    await expect(page.locator("main")).not.toContainText("foundation для кількох складів");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test("promotions and loyalty walkthrough shows six real stages with explicit discount boundaries", async ({page}) => {
  await page.setViewportSize({width:1280,height:900});
  await page.goto(origin + "/avtomatyzatsiya-rozdribnoi-torgivli", {waitUntil:"load"});
  const tour = page.locator(".feature-tour.loyalty-single-slider");
  const slider = tour.locator(".live-shot-carousel");
  const figures = slider.locator("figure.tour-shot");
  await expect(figures).toHaveCount(6);
  await expect(slider.locator(".live-shot-dots")).toHaveCount(0);
  await expect(tour.getByText("Від правила акції до бонусів і статистики")).toBeVisible();
  await expect(tour.locator(".tour-eyebrow")).toHaveText("РЕАЛЬНИЙ СЦЕНАРІЙ · АКЦІЇ ТА ЛОЯЛЬНІСТЬ");
  await expect(tour.locator(".tour-note")).toContainText("бонуси в OutPOSt — це знижка");
  await expect(tour.locator(".tour-note")).toContainText("вони не складаються");
  await expect(tour.locator(".tour-note")).toContainText("«2+1»");
  const heights = [];
  for (let i=0;i<6;i++) {
    if (i) await slider.locator(".live-shot-next").click();
    await expect(figures.nth(i)).toBeVisible();
    await expect(slider.locator(".live-shot-counter")).toHaveText("Крок " + (i + 1) + " із 6");
    const figBox = await figures.nth(i).boundingBox();
    const imageBox = await figures.nth(i).locator("a:has(img)").boundingBox();
    const captionBox = await figures.nth(i).locator("figcaption").boundingBox();
    expect(captionBox.y).toBeGreaterThanOrEqual(imageBox.y + imageBox.height - 2);
    expect(await figures.nth(i).locator("figcaption").evaluate(el => getComputedStyle(el).textAlign)).toBe("center");
    heights.push(figBox.height);
    const opener = figures.nth(i).locator("a:has(img)");
    expect(await opener.getAttribute("target")).toBeNull();
    await opener.click({position:{x:Math.round(imageBox.width/2),y:Math.round(imageBox.height/2)}});
    const viewer = page.locator("dialog.live-shot-dialog");
    await expect(viewer).toBeVisible();
    await expect(viewer.locator("img")).toHaveAttribute("src", new RegExp("/02420/loyalty/"));
    await viewer.locator(".live-shot-dialog-close").click();
    await expect(viewer).toBeHidden();
  }
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(3);
  await expect(slider.locator(".live-shot-next")).toBeDisabled();
});

test("Windows POS sale walkthrough uses finalized single-stage template across all six real screenshots", async ({page}) => {
  await page.setViewportSize({width:1280,height:900});
  await page.goto(origin + "/programa-dlya-kasy-windows", {waitUntil:"load"});
  const tour = page.locator(".feature-tour.single-shot-slider");
  const slider = tour.locator(".live-shot-carousel");
  const figures = slider.locator("figure.tour-shot");
  await expect(figures).toHaveCount(6);
  await expect(slider.locator(".live-shot-dots")).toHaveCount(0);
  await expect(tour.getByText("Як відбувається продаж")).toBeVisible();
  const related = page.locator(".scenario-related");
  const belowCoreContent = await tour.evaluate((el) => el.getBoundingClientRect().top > document.querySelector(".scenario-section.dark").getBoundingClientRect().top);
  expect(belowCoreContent).toBeTruthy();
  await expect(related).toBeVisible();
  const overlay = slider.locator(".live-shot-controls");
  expect(await overlay.evaluate(el => getComputedStyle(el).position)).toBe("absolute");
  const heights = [];
  for (let i=0;i<6;i++) {
    if (i) await slider.locator(".live-shot-next").click();
    await expect(figures.nth(i)).toBeVisible();
    await expect(slider.locator(".live-shot-counter")).toHaveText("Крок " + (i + 1) + " із 6");
    const figBox = await figures.nth(i).boundingBox();
    const imageBox = await figures.nth(i).locator("a:has(img)").boundingBox();
    const captionBox = await figures.nth(i).locator("figcaption").boundingBox();
    expect(captionBox.y).toBeGreaterThanOrEqual(imageBox.y + imageBox.height - 2);
    const centered = await figures.nth(i).locator("figcaption").evaluate(el => getComputedStyle(el).textAlign);
    expect(centered).toBe("center");
    heights.push(figBox.height);
    const opener = figures.nth(i).locator("a:has(img)");
    expect(await opener.getAttribute("target")).toBeNull();
    await opener.click({position:{x:Math.round(imageBox.width/2),y:Math.round(imageBox.height/2)}});
    const viewer = page.locator("dialog.live-shot-dialog");
    await expect(viewer).toBeVisible();
    await expect(viewer.locator("img")).toHaveAttribute("src", new RegExp("/02412/pos-sale/"));
    await viewer.locator(".live-shot-dialog-close").click();
    await expect(viewer).toBeHidden();
  }
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(3);
  await expect(slider.locator(".live-shot-next")).toBeDisabled();
});

test("debt walkthrough has seven compact bottom-positioned slides, overlaid arrows and every photo opens in-page", async ({page}) => {
  await page.setViewportSize({width:1280,height:900});
  await page.goto(origin + "/prodazh-v-borg", {waitUntil:"load"});
  const tour = page.locator(".feature-tour.debt-single-slider");
  const slider = tour.locator(".live-shot-carousel");
  const figures = slider.locator("figure.debt-story-item");
  await expect(figures).toHaveCount(7);
  await expect(slider.locator(".live-shot-dots")).toHaveCount(0);
  await expect(tour.locator(".debt-story-zoom")).toHaveCount(0);
  const below = await tour.evaluate(el => el.getBoundingClientRect().top > document.querySelector(".scenario-related").getBoundingClientRect().top);
  expect(below).toBeTruthy();
  const overlay = slider.locator(".live-shot-controls");
  expect(await overlay.evaluate(el => getComputedStyle(el).position)).toBe("absolute");
  const heights = [];
  for (let i=0;i<7;i++) {
    if (i) await slider.locator(".live-shot-next").click();
    await expect(figures.nth(i)).toBeVisible();
    await expect(slider.locator(".live-shot-counter")).toHaveText("Крок " + (i+1) + " із 7");
    const figBox = await figures.nth(i).boundingBox();
    const imageBox = await figures.nth(i).locator(".debt-story-image").boundingBox();
    const captionBox = await figures.nth(i).locator(".debt-story-copy").boundingBox();
    expect(captionBox.y).toBeGreaterThanOrEqual(imageBox.y + imageBox.height - 2);
    heights.push(figBox.height);
    const opener = figures.nth(i).locator(".debt-story-image");
    await opener.click({position:{x:Math.round(imageBox.width/2),y:Math.round(imageBox.height/2)}});
    const viewer = page.locator("dialog.live-shot-dialog");
    await expect(viewer).toBeVisible();
    const toolbarBox = await viewer.locator(".live-shot-dialog-toolbar").boundingBox();
    const titleBox = await viewer.locator(".live-shot-dialog-title").boundingBox();
    expect(Math.abs((toolbarBox.x + toolbarBox.width / 2) - (titleBox.x + titleBox.width / 2))).toBeLessThanOrEqual(2);
    await expect(viewer.locator("img")).toHaveAttribute("src", new RegExp("/0?2410/debt-sale/"));
    await viewer.locator(".live-shot-dialog-close").click();
    await expect(viewer).toBeHidden();
  }
  expect(Math.max(...heights)-Math.min(...heights)).toBeLessThanOrEqual(3);
  await expect(slider.locator(".live-shot-next")).toBeDisabled();
  await slider.locator(".live-shot-prev").click();
  await expect(slider.locator(".live-shot-counter")).toHaveText("Крок 6 із 7");
});

test("migrated batch and payroll tours keep all steps, intrinsic dimensions and keyboard isolation", async ({page}) => {
  test.setTimeout(120000);
  const cases = [
    {path:"/modules",selector:"#batch-registry-tour",count:7,prefix:"/assets/screenshots/02419/batch-expiry/"},
    {path:"/avtomatyzatsiya-magazynu",selector:"#director-payroll-tour",count:8,prefix:"/assets/screenshots/02422/director-payroll/"},
  ];
  for (const width of [1280,390,360]) {
    await page.setViewportSize({width,height:900});
    for (const item of cases) {
      await page.goto(origin + item.path, {waitUntil:"load"});
      const ids = await page.locator("[id]").evaluateAll(nodes => nodes.map(n=>n.id));
      expect(new Set(ids).size, "duplicate page IDs").toBe(ids.length);
      const tour = page.locator(item.selector);
      const carousel = tour.locator(".live-shot-carousel");
      const figures = carousel.locator("figure.tour-shot");
      await expect(figures).toHaveCount(item.count);
      await expect(carousel.locator(".live-shot-prev")).toBeDisabled();
      const sources = await figures.locator("img").evaluateAll(nodes => nodes.map(n=>n.getAttribute("src")));
      expect(new Set(sources).size).toBe(item.count);
      expect(sources.every(src=>src.startsWith(item.prefix))).toBe(true);
      const heights = [];
      for (let i=0;i<item.count;i++) {
        if (i) {await carousel.focus();await page.keyboard.press("ArrowRight");}
        const figure = figures.nth(i);
        await expect(figure).toBeVisible();
        await expect(carousel.locator(".live-shot-counter")).toHaveText(`Крок ${i+1} із ${item.count}`);
        const opener = figure.locator("a:has(img)");
        await opener.scrollIntoViewIfNeeded();
        const img = opener.locator("img");
        await expect(img).toHaveJSProperty("complete",true);
        const dimensions = await img.evaluate(n=>({actual:[n.naturalWidth,n.naturalHeight],declared:[Number(n.getAttribute("width")),Number(n.getAttribute("height"))],alt:n.getAttribute("alt")}));
        expect(dimensions.actual[0]).toBeGreaterThan(0);
        expect(dimensions.declared).toEqual(dimensions.actual);
        expect(dimensions.alt?.trim()).toBeTruthy();
        const caption = figure.locator("figcaption");
        const captionSize = await caption.evaluate(n=>({scroll:n.scrollHeight,client:n.clientHeight}));
        expect(captionSize.scroll, `${item.path} ${width}px step${i+1}: clipped caption`).toBeLessThanOrEqual(captionSize.client+1);
        const figureBox = await figure.boundingBox();
        const imageBox = await opener.boundingBox();
        const captionBox = await caption.boundingBox();
        expect(captionBox.y).toBeGreaterThanOrEqual(imageBox.y+imageBox.height-2);
        heights.push(figureBox.height);
        if (i===0 && width!==360) await page.screenshot({path:path.join(artifactRoot,`migrated-${slugFor(item.path)}-${width}.png`),fullPage:false});
        await opener.focus();
        await page.keyboard.press("Enter");
        const viewer = page.locator("dialog.live-shot-dialog");
        await expect(viewer).toBeVisible();
        await expect(viewer.locator("img")).toHaveAttribute("src",sources[i]);
        await expect(viewer.locator(".live-shot-dialog-count")).toHaveText(`${i+1} / ${item.count}`);
        if (i===0 && width===1280) await page.screenshot({path:path.join(artifactRoot,`migrated-${slugFor(item.path)}-viewer.png`),fullPage:false});
        await page.keyboard.press("ArrowRight");
        await expect(viewer.locator("img")).toHaveAttribute("src",sources[(i+1)%item.count]);
        await page.keyboard.press("ArrowLeft");
        await expect(viewer.locator("img")).toHaveAttribute("src",sources[i]);
        await viewer.evaluate(node=>{node.dataset.qaClosed="0";node.addEventListener("close",()=>{node.dataset.qaClosed="1";},{once:true});});
        await page.keyboard.press("Escape");
        await expect(viewer).toHaveAttribute("data-qa-closed","1");
        await expect(viewer).toBeHidden();
        await expect(opener).toBeFocused();
      }
      expect(Math.max(...heights)-Math.min(...heights)).toBeLessThanOrEqual(3);
      await expect(carousel.locator(".live-shot-next")).toBeDisabled();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth)).toBeLessThanOrEqual(1);
    }
    await page.goto(origin+"/features",{waitUntil:"load"});
    const carousel = page.locator(".feature-tour .live-shot-carousel");
    for(let i=0;i<6;i++){await carousel.focus();await page.keyboard.press("ArrowRight");}
    const last = carousel.locator("figure.tour-shot").nth(6);
    await expect(last).toBeVisible();
    await expect(last.getByRole("link",{name:"Повний директорський сценарій →"})).toHaveAttribute("href","/interfeis#director-v02422");
    const target = page.locator("#director-v02422");
    await last.getByRole("link",{name:"Повний директорський сценарій →"}).click();
    await expect(page).toHaveURL(origin+"/interfeis#director-v02422");
    await expect(target).toBeVisible();
  }
});

test("remaining migrated galleries load every image and keep separate debt flows", async ({page}) => {
  test.setTimeout(120000);
  const cases = [
    {path:"/programa-dlya-fop",selector:".feature-tour.single-shot-slider",count:5},
    {path:"/programa-dlya-nevelykogo-magazynu",selector:".feature-tour.single-shot-slider",count:6},
    {path:"/offline-programa-dlya-magazynu",selector:".feature-tour.single-shot-slider",count:5},
    {path:"/support",selector:".feature-tour.single-shot-slider",count:1,asset:"/assets/screenshots/02410/help/01-help-window.webp"},
    {path:"/prodazh-v-borg",selector:".feature-tour.single-shot-slider",count:1,asset:"/assets/screenshots/02410/debt-sale/08-underpayment-to-debt.webp"},
  ];
  for(const width of [1280,390,360]) {
    await page.setViewportSize({width,height:900});
    for(const item of cases) {
      await page.goto(origin+item.path,{waitUntil:"load"});
      const tour=page.locator(item.selector);
      const carousel=tour.locator(".live-shot-carousel");
      const figures=tour.locator("figure.tour-shot");
      await expect(figures).toHaveCount(item.count);
      const ids=await page.locator("[id]").evaluateAll(nodes=>nodes.map(n=>n.id));
      expect(new Set(ids).size).toBe(ids.length);
      if(item.path==="/prodazh-v-borg") {
        await expect(page.locator(".debt-single-slider figure.debt-story-item")).toHaveCount(7);
        await expect(tour).toContainText("25,40 грн");
      }
      if(item.path==="/support") {
        await expect(tour).toContainText("0.24.10");
        await expect(page.locator('link[rel="stylesheet"][href="/assets/feature-tour-v1.css"]')).toHaveCount(1);
      }
      for(let i=0;i<item.count;i++) {
        if(i) await carousel.locator(".live-shot-next").click();
        const figure=figures.nth(i);
        await expect(figure).toBeVisible();
        const opener=figure.locator("a:has(img)");
        await opener.scrollIntoViewIfNeeded();
        const img=opener.locator("img");
        await expect(img).toHaveJSProperty("complete",true);
        const dims=await img.evaluate(n=>({actual:[n.naturalWidth,n.naturalHeight],declared:[Number(n.getAttribute("width")),Number(n.getAttribute("height"))]}));
        expect(dims.actual[0]).toBeGreaterThan(0);
        expect(dims.declared).toEqual(dims.actual);
        expect(await img.evaluate(n=>getComputedStyle(n).objectFit)).toBe("contain");
        const source=await img.getAttribute("src");
        if(item.asset) expect(source).toBe(item.asset);
        const caption=await figure.locator("figcaption").evaluate(n=>({scroll:n.scrollHeight,client:n.clientHeight}));
        expect(caption.scroll).toBeLessThanOrEqual(caption.client+1);
        await opener.focus();await page.keyboard.press("Enter");
        const viewer=page.locator("dialog.live-shot-dialog");
        await expect(viewer).toBeVisible();
        await expect(viewer.locator("img")).toHaveAttribute("src",source);
        await expect(viewer.locator(".live-shot-dialog-count")).toHaveText(`${i+1} / ${item.count}`);
        await page.keyboard.press("Escape");
        await expect(viewer).toBeHidden();
        await expect(opener).toBeFocused();
      }
      expect(await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth)).toBeLessThanOrEqual(1);
      if(item.asset&&width!==360) await tour.screenshot({path:path.join(artifactRoot,`remaining-${slugFor(item.path)}-${width}.png`)});
    }
  }
});

test("screenshot viewer keeps its headline centered at mobile width", async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto(origin + "/prodazh-v-borg", {waitUntil:"load"});
  const opener = page.locator(".debt-single-slider .debt-story-item").first().locator(".debt-story-image");
  await opener.click();
  const viewer = page.locator("dialog.live-shot-dialog");
  await expect(viewer).toBeVisible();
  const toolbarBox = await viewer.locator(".live-shot-dialog-toolbar").boundingBox();
  const titleBox = await viewer.locator(".live-shot-dialog-title").boundingBox();
  expect(Math.abs((toolbarBox.x + toolbarBox.width / 2) - (titleBox.x + titleBox.width / 2))).toBeLessThanOrEqual(2);
  await viewer.locator(".live-shot-modal-next").click();
  await expect(viewer.locator(".live-shot-dialog-count")).toHaveText("2 / 7");
  const newTitle = await viewer.locator(".live-shot-dialog-title").boundingBox();
  expect(Math.abs((toolbarBox.x + toolbarBox.width / 2) - (newTitle.x + newTitle.width / 2))).toBeLessThanOrEqual(2);
  await viewer.locator(".live-shot-dialog-close").click();
  await expect(viewer).toBeHidden();
});
