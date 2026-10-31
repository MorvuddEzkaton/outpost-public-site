import { test, expect } from "@playwright/test";
import fs from "node:fs";
import crypto from "node:crypto";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const siteRoot = path.join(repoRoot, "site");
const artifactRoot = path.join(repoRoot, "browser-runtime-artifacts");
const origin = "http://127.0.0.1:4174";
const staticTypes = new Set(["document", "script", "stylesheet", "font", "image"]);

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
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
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

function isProtectedApi(url) {
  try {
    const parsed = new URL(url);
    return parsed.origin === origin && parsed.pathname.startsWith("/api/");
  } catch {
    return false;
  }
}

function isSameOriginStatic(request) {
  try {
    const parsed = new URL(request.url());
    return parsed.origin === origin && !parsed.pathname.startsWith("/api/") && staticTypes.has(request.resourceType());
  } catch {
    return false;
  }
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

    const type = mime.get(path.extname(target).toLowerCase()) || "application/octet-stream";
    res.writeHead(200, { "content-type": type, "cache-control": "no-store" });
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

function slugFor(pagePath) {
  return pagePath === "/" ? "home" : pagePath.replace(/^\//, "").replace(/[^a-zA-Z0-9_-]+/g, "-");
}

test("all sitemap pages load without browser runtime/static-resource errors", async ({ browser }) => {
  test.setTimeout(180_000);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const failures = [];

  for (const pagePath of sitemapPaths()) {
    const errors = [];

    const onPageError = (error) => errors.push(`uncaught JS error: ${error.message}`);
    const onConsole = (message) => {
      if (message.type() !== "error") return;
      const text = message.text().trim();
      if (!text || text.startsWith("Failed to load resource:")) return;
      errors.push(`console.error: ${text}`);
    };
    const onRequestFailed = (request) => {
      if (!isSameOriginStatic(request)) return;
      errors.push(`request failed: ${request.resourceType()} ${request.url()} (${request.failure()?.errorText || "unknown"})`);
    };
    const onResponse = (response) => {
      const request = response.request();
      if (!isSameOriginStatic(request) || isProtectedApi(response.url())) return;
      if (response.status() >= 400) errors.push(`HTTP ${response.status()}: ${request.resourceType()} ${response.url()}`);
    };

    page.on("pageerror", onPageError);
    page.on("console", onConsole);
    page.on("requestfailed", onRequestFailed);
    page.on("response", onResponse);

    const response = await page.goto(`${origin}${pagePath}`, { waitUntil: "load", timeout: 20_000 });
    if (!response || !response.ok()) errors.push(`document load failed: HTTP ${response?.status() ?? "no response"}`);
    await page.waitForTimeout(300);

    if (errors.length) {
      const screenshot = path.join(artifactRoot, `${slugFor(pagePath)}.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      failures.push(`${pagePath}: ${errors.join("; ")}`);
    }

    page.off("pageerror", onPageError);
    page.off("console", onConsole);
    page.off("requestfailed", onRequestFailed);
    page.off("response", onResponse);
  }

  await context.close();
  expect(failures, failures.join("\n")).toEqual([]);
});


test("demo finance, write-off and inventory flows stay connected", async ({ browser }) => {
  test.setTimeout(90_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(`${origin}/demo`, { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_API && window.OUTPOST_DEMO_MODULES)),
    { message: "demo integration APIs should initialize" },
  ).toBe(true);
  const initialFixture=await page.evaluate(()=>{const s=window.OUTPOST_DEMO_API.getState();return {shifts:s.cashShifts.length,shiftId:s.currentCashShift.id,nextShift:s.nextCashShift,returns:s.returns.length,nextReturn:s.nextReturn,writeoffs:s.writeoffs.length,nextWriteoff:s.nextWriteoff,inventories:s.inventories.length};});

  await page.locator('[data-view="finance"]').click();
  await expect(page.locator('[data-view-panel="finance"]')).toHaveClass(/is-active/);

  await page.locator('[data-cash-action="in"]').click();
  const cashComment = page.locator("#cash-action-comment");
  await cashComment.focus();
  await page.waitForTimeout(40);
  await expect(cashComment).toBeFocused();
  await page.locator("#cash-action-amount").fill("125.50");
  await cashComment.fill("Runtime regression: внесення");
  await page.locator("#confirm-cash-action").click();
  await expect(page.locator("#cash-action-dialog")).not.toHaveAttribute("open", "");

  await page.locator('[data-cash-action="out"]').click();
  await expect(page.locator("#cash-action-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#cash-action-title")).toHaveText("Вилучити кошти");
  await page.locator("#cash-action-supplier").selectOption({ index: 1 });
  await page.locator("#cash-action-amount").fill("25.50");
  await page.locator("#cash-action-comment").fill("Runtime regression: вилучення");
  await expect(page.locator("#cash-action-amount")).toHaveValue("25.50");
  await page.locator("#confirm-cash-action").click();
  await expect(page.locator("#cash-action-dialog")).not.toHaveAttribute("open", "");

  const cashState = await page.evaluate(() => {
    const movements = window.OUTPOST_DEMO_API.getState().cashMovements.filter((movement) => movement.affectsCash === true);
    return movements.slice(0, 2).map((movement) => ({
      type: movement.type,
      amount: movement.amount,
      direction: movement.direction,
      hasSupplier: Boolean(movement.supplierId),
    }));
  });
  expect(cashState).toEqual([
    { type: "SupplierPayment", amount: 25.5, direction: "out", hasSupplier: true },
    { type: "CashIn", amount: 125.5, direction: "in", hasSupplier: false },
  ]);

  await page.locator("#show-withdrawals").click();
  await expect(page.locator("#withdrawals-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#withdrawals-table")).toContainText("25");
  await page.locator("#withdrawals-dialog").getByText("Закрити", { exact: true }).click();

  const beforeCloseShift = await page.evaluate(() => window.OUTPOST_DEMO_MODULES.getCashSummary());
  expect(beforeCloseShift.isOpen).toBe(true);
  await page.locator("#finance-shift-action").click();
  await expect(page.locator("#close-shift-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#close-shift-expected")).toContainText("грн");
  const actualClosingBalance = Math.round((beforeCloseShift.expected + 5) * 100) / 100;
  await page.locator("#close-shift-actual").fill(actualClosingBalance.toFixed(2));
  await expect(page.locator("#close-shift-difference")).toContainText("+");
  await page.locator("#confirm-close-shift").click();
  await expect(page.locator("#close-shift-dialog")).not.toHaveAttribute("open", "");
  await expect(page.locator("#finance-shift-status")).toHaveText("Закрита");
  await expect(page.locator('[data-cash-action="in"]')).toBeDisabled();
  await expect(page.locator('[data-cash-action="out"]')).toBeDisabled();

  const closedShiftState = await page.evaluate(() => {
    const state = window.OUTPOST_DEMO_API.getState();
    const last = state.cashShifts[0];
    return {
      current: state.currentCashShift,
      count: state.cashShifts.length,
      id: last?.id,
      actual: last?.actualClosingBalance,
      expected: last?.expectedClosingBalance,
      difference: last?.difference,
    };
  });
  expect(closedShiftState.current).toBeNull();
  expect(closedShiftState.count).toBe(initialFixture.shifts+1);
  expect(closedShiftState.id).toBe(initialFixture.shiftId);
  expect(closedShiftState.actual).toBe(actualClosingBalance);
  expect(closedShiftState.expected).toBe(beforeCloseShift.expected);
  expect(closedShiftState.difference).toBe(5);

  await page.locator("#finance-shift-action").click();
  await expect(page.locator("#open-shift-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#open-shift-opening")).toHaveValue(actualClosingBalance.toFixed(2));
  await page.locator("#confirm-open-shift").click();
  await expect(page.locator("#open-shift-dialog")).not.toHaveAttribute("open", "");
  await expect(page.locator("#finance-shift-status")).toHaveText("Відкрита");

  const reopenedShiftState = await page.evaluate(() => {
    const state = window.OUTPOST_DEMO_API.getState();
    const summary = window.OUTPOST_DEMO_MODULES.getCashSummary();
    return {
      id: state.currentCashShift?.id,
      opening: state.currentCashShift?.openingBalance,
      sales: summary.sales,
      cashIn: summary.inAmount,
      cashOut: summary.outAmount,
      expected: summary.expected,
    };
  });
  expect(reopenedShiftState.id).toBe(initialFixture.nextShift);
  expect(reopenedShiftState.opening).toBe(actualClosingBalance);
  expect(reopenedShiftState.sales).toBe(0);
  expect(reopenedShiftState.cashIn).toBe(0);
  expect(reopenedShiftState.cashOut).toBe(0);
  expect(reopenedShiftState.expected).toBe(actualClosingBalance);

  const saleReturnTarget = await page.evaluate(() => {
    const state = window.OUTPOST_DEMO_API.getState();
    const product = state.products.find((item) => item.barcode && Number(item.price) > 0) || state.products[0];
    return {
      productId: product.id,
      barcode: product.barcode,
      stock: Number(product.stock),
      price: Number(product.price),
    };
  });

  await page.locator('[data-view="sale"]').click();
  await page.locator("#product-search").fill(saleReturnTarget.barcode);
  await page.locator("#product-search").press("Enter");
  await expect(page.locator("#cart-count")).toHaveText("1 поз.");
  await page.keyboard.press("F2");
  await expect(page.locator("#cash-payment-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#cash-payment-received")).toBeFocused();
  await page.locator("#cash-payment-received").press("Enter");
  await expect(page.locator("#cash-payment-dialog")).not.toHaveAttribute("open", "");

  const cashSaleForReturn = await page.evaluate((target) => {
    const state = window.OUTPOST_DEMO_API.getState();
    const sale = state.sales[0];
    const product = state.products.find((item) => item.id === target.productId);
    return {
      id: sale.id,
      payment: sale.payment,
      total: sale.total,
      lineProductId: sale.lines?.[0]?.productId || null,
      stockAfterSale: product.stock,
    };
  }, saleReturnTarget);
  expect(cashSaleForReturn.payment).toBe("cash");
  expect(cashSaleForReturn.lineProductId).toBe(saleReturnTarget.productId);
  expect(cashSaleForReturn.stockAfterSale).toBe(
    Math.round((saleReturnTarget.stock - 1) * 100) / 100,
  );

  await page.locator('[data-view-link="history"]').first().click();
  const returnButton = page.locator(`[data-return-sale="${cashSaleForReturn.id}"]`);
  await expect(returnButton).toBeEnabled();
  await returnButton.click();
  await expect(page.locator("#sale-return-dialog")).toHaveAttribute("open", "");
  await page.locator("#return-all-available").click();
  await expect(page.locator("#sale-return-total")).toContainText("грн");
  await page.locator("#open-return-payment").click();
  await expect(page.locator("#return-payment-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#return-payment-cash")).toHaveValue(cashSaleForReturn.total.toFixed(2));
  await page.locator("#confirm-sale-return").click();
  await expect(page.locator("#return-payment-dialog")).not.toHaveAttribute("open", "");

  const returnState = await page.evaluate(({ target, saleId }) => {
    const state = window.OUTPOST_DEMO_API.getState();
    const product = state.products.find((item) => item.id === target.productId);
    const record = state.returns[0];
    const movement = state.cashMovements.find((item) => item.type === "SaleReturn");
    const summary = window.OUTPOST_DEMO_MODULES.getCashSummary();
    return {
      returnsCount: state.returns.length,
      returnId: record?.id,
      saleId: record?.saleId,
      total: record?.total,
      returnedQty: record?.lines?.[0]?.qty,
      stockAfterReturn: product.stock,
      cashMovementAmount: movement?.amount,
      cashMovementDirection: movement?.direction,
      cashExpected: summary.expected,
      homeReturns: document.querySelector("#home-returns")?.textContent || "",
    };
  }, { target: saleReturnTarget, saleId: cashSaleForReturn.id });
  expect(returnState.returnsCount).toBe(initialFixture.returns+1);
  expect(returnState.returnId).toBe('RET-'+String(initialFixture.nextReturn).padStart(6,'0'));
  expect(returnState.saleId).toBe(cashSaleForReturn.id);
  expect(returnState.total).toBe(cashSaleForReturn.total);
  expect(returnState.returnedQty).toBe(1);
  expect(returnState.stockAfterReturn).toBe(saleReturnTarget.stock);
  expect(returnState.cashMovementAmount).toBe(cashSaleForReturn.total);
  expect(returnState.cashMovementDirection).toBe("out");
  expect(returnState.cashExpected).toBe(actualClosingBalance);
  expect(returnState.homeReturns).not.toBe("0,00 грн");
  await expect(page.locator(`[data-return-sale="${cashSaleForReturn.id}"]`)).toBeDisabled();
  await expect(page.locator("#returns-history")).toContainText(returnState.returnId);

  await page.locator('[data-view="stockops"]').click();
  await expect(page.locator('[data-view-panel="stockops"]')).toHaveClass(/is-active/);
  await page.locator("#new-writeoff").click();

  const writeoffProductId = await page.locator("#writeoff-product").inputValue();
  const stockBeforeWriteoff = await page.evaluate((productId) => {
    const product = window.OUTPOST_DEMO_API.getState().products.find((item) => item.id === productId);
    return product?.stock ?? null;
  }, writeoffProductId);
  expect(stockBeforeWriteoff).not.toBeNull();

  await page.locator("#writeoff-qty").fill("2");
  await page.locator("#add-writeoff-line").click();
  await expect(page.locator("#writeoff-draft-lines tr")).toHaveCount(1);
  await page.locator("#save-writeoff").click();

  const writeoffState = await page.evaluate(({ productId, before }) => {
    const state = window.OUTPOST_DEMO_API.getState();
    const product = state.products.find((item) => item.id === productId);
    return {
      writeoffCount: state.writeoffs.length,
      firstId: state.writeoffs[0]?.id || "",
      stock: product?.stock ?? null,
      expectedStock: window.OUTPOST_DEMO_API.round2(before - 2),
    };
  }, { productId: writeoffProductId, before: stockBeforeWriteoff });
  expect(writeoffState.writeoffCount).toBe(initialFixture.writeoffs+1);
  expect(writeoffState.firstId).toBe('WO-'+String(initialFixture.nextWriteoff).padStart(6,'0'));
  expect(writeoffState.stock).toBe(writeoffState.expectedStock);

  await page.locator('[data-stock-tab="inventory"]').click();
  await page.locator("#new-inventory").click();
  await page.locator("#inventory-comment").fill("Runtime regression inventory");
  await page.locator("#create-inventory").click();
  await expect(page.locator("#inventory-count-dialog")).toHaveAttribute("open", "");

  const inventoryTarget = await page.evaluate(() => {
    const state = window.OUTPOST_DEMO_API.getState();
    const inventory = state.inventories[0];
    const item = inventory.items.find((candidate) => Number(candidate.expected) >= 0) || inventory.items[0];
    return {
      inventoryId: inventory.id,
      productId: item.productId,
      expected: Number(item.expected),
    };
  });
  const actual = Math.max(0, inventoryTarget.expected + 3);
  const actualInput = page.locator(`[data-inventory-actual="${inventoryTarget.productId}"]`);
  await actualInput.fill(String(actual));
  await actualInput.dispatchEvent("change");

  const beforePost = await page.evaluate((target) => {
    const state = window.OUTPOST_DEMO_API.getState();
    const inventory = state.inventories.find((item) => item.id === target.inventoryId);
    const snapshotItem = inventory.items.find((item) => item.productId === target.productId);
    const product = state.products.find((item) => item.id === target.productId);
    return {
      status: inventory.status,
      actual: snapshotItem.actual,
      productStock: product.stock,
    };
  }, inventoryTarget);
  expect(beforePost.status).toBe("draft");
  expect(beforePost.actual).toBe(actual);
  expect(beforePost.productStock).toBe(inventoryTarget.expected);

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#inventory-post").click();
  await expect(page.locator("#inventory-count-dialog")).not.toHaveAttribute("open", "");

  const afterPost = await page.evaluate((target) => {
    const state = window.OUTPOST_DEMO_API.getState();
    const inventory = state.inventories.find((item) => item.id === target.inventoryId);
    const product = state.products.find((item) => item.id === target.productId);
    return {
      status: inventory.status,
      postedAt: inventory.postedAt,
      productStock: product.stock,
    };
  }, inventoryTarget);
  expect(afterPost.status).toBe("posted");
  expect(afterPost.postedAt).toBeTruthy();
  expect(afterPost.productStock).toBe(actual);

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  await expect.poll(() => page.evaluate(() => {
    const state = window.OUTPOST_DEMO_API.getState();
    return {
      writeoffs: state.writeoffs?.length || 0,
      inventories: state.inventories?.length || 0,
      demoCashMovements: state.cashMovements.filter((movement) => movement.affectsCash === true && !movement.demoSeed).length,
      returns: state.returns?.length || 0,
      cashShifts: state.cashShifts?.length || 0,
      currentShiftId: state.currentCashShift?.id || null,
      currentOpening: state.currentCashShift?.openingBalance ?? null,
    };
  })).toEqual({
    writeoffs: initialFixture.writeoffs,
    inventories: initialFixture.inventories,
    demoCashMovements: 0,
    returns: initialFixture.returns,
    cashShifts: initialFixture.shifts,
    currentShiftId: initialFixture.shiftId,
    currentOpening: 2000,
  });

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("demo selected-cart controls and discount persist into sale", async ({ browser }) => {
  test.setTimeout(60_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_API?.getCart)),
    { message: "cart regression API should initialize" },
  ).toBe(true);

  const targets = await page.evaluate(() => {
    const products = window.OUTPOST_DEMO_API.getState().products
      .filter((item) => item.barcode && Number(item.price) > 0)
      .slice(0, 2);
    return products.map((item) => ({
      id: item.id,
      barcode: item.barcode,
      price: Number(item.price),
    }));
  });
  expect(targets).toHaveLength(2);

  await page.locator("#product-search").fill(targets[0].barcode);
  await page.locator("#product-search").press("Enter");
  await expect(page.locator("#cart-count")).toHaveText("1 поз.");
  await expect(page.locator("#cart-inc-selected")).toBeEnabled();
  await expect(page.locator("#cart-discount-selected")).toBeEnabled();

  await page.locator("#cart-inc-selected").click();
  let cartState = await page.evaluate(() => ({
    cart: window.OUTPOST_DEMO_API.getCart(),
    selected: window.OUTPOST_DEMO_API.getSelectedCartProductId(),
    total: window.OUTPOST_DEMO_API.getCartTotal(),
  }));
  expect(cartState.cart).toHaveLength(1);
  expect(cartState.cart[0].qty).toBe(2);
  expect(cartState.selected).toBe(targets[0].id);

  await page.locator("#cart-discount-selected").click();
  await expect(page.locator("#discount-dialog")).toHaveAttribute("open", "");
  await page.locator("#discount-percent").fill("12.5");
  await page.locator("#apply-discount").click();
  await expect(page.locator("#discount-dialog")).not.toHaveAttribute("open", "");

  const discountedUnit = Math.round((targets[0].price * 0.875 + Number.EPSILON) * 100) / 100;
  cartState = await page.evaluate(() => ({
    cart: window.OUTPOST_DEMO_API.getCart(),
    total: window.OUTPOST_DEMO_API.getCartTotal(),
  }));
  expect(cartState.cart[0].discountPercent).toBe(12.5);
  expect(cartState.total).toBe(Math.round((discountedUnit * 2 + Number.EPSILON) * 100) / 100);

  await page.locator("#cart-dec-selected").click();
  cartState = await page.evaluate(() => window.OUTPOST_DEMO_API.getCart());
  expect(cartState[0].qty).toBe(1);

  await page.locator("#product-search").fill(targets[1].barcode);
  await page.locator("#product-search").press("Enter");
  cartState = await page.evaluate(() => ({
    cart: window.OUTPOST_DEMO_API.getCart(),
    selected: window.OUTPOST_DEMO_API.getSelectedCartProductId(),
  }));
  expect(cartState.cart).toHaveLength(2);
  expect(cartState.selected).toBe(targets[1].id);

  const secondRow = page.locator('[data-cart-row="' + targets[1].id + '"]');
  await secondRow.focus();
  await page.waitForTimeout(30);
  await expect(secondRow).toBeFocused();
  await page.keyboard.press("Delete");
  cartState = await page.evaluate(() => ({
    cart: window.OUTPOST_DEMO_API.getCart(),
    selected: window.OUTPOST_DEMO_API.getSelectedCartProductId(),
  }));
  expect(cartState.cart).toHaveLength(1);
  expect(cartState.cart[0].productId).toBe(targets[0].id);
  expect(cartState.selected).toBe(targets[0].id);

  await page.keyboard.press("F2");
  await expect(page.locator("#cash-payment-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#cash-payment-received")).toBeFocused();
  await page.locator("#cash-payment-received").press("Enter");
  await expect(page.locator("#cash-payment-dialog")).not.toHaveAttribute("open", "");
  const saleState = await page.evaluate(() => {
    const sale = window.OUTPOST_DEMO_API.getState().sales[0];
    return {
      payment: sale.payment,
      total: sale.total,
      line: sale.lines[0],
      cartLength: window.OUTPOST_DEMO_API.getCart().length,
    };
  });
  expect(saleState.payment).toBe("cash");
  expect(saleState.total).toBe(discountedUnit);
  expect(saleState.line.productId).toBe(targets[0].id);
  expect(saleState.line.discountPercent).toBe(12.5);
  expect(saleState.line.retailPrice).toBe(targets[0].price);
  expect(saleState.line.price).toBe(discountedUnit);
  expect(saleState.cartLength).toBe(0);

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("demo products stock search creation and movements stay functional", async ({ browser }) => {
  test.setTimeout(70_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_PRODUCTS_MODULE)),
    { message: "products stock module should initialize" },
  ).toBe(true);

  await page.locator('[data-view="products"]').click();
  await expect(page.locator('[data-view-panel="products"]')).toHaveClass(/is-active/);

  const existing = await page.evaluate(() => {
    const product = window.OUTPOST_DEMO_API.getState().products.find((item) => item.barcode) ||
      window.OUTPOST_DEMO_API.getState().products[0];
    return { id: product.id, name: product.name, barcode: product.barcode || product.code };
  });
  await page.locator("#product-stock-search").fill(existing.barcode);
  await expect(page.locator("#products-table")).toContainText(existing.name);
  await page.locator("#products-table tr").first().click();
  await expect(page.locator("#product-movements")).toBeEnabled();

  await page.locator("#new-product").click();
  await expect(page.locator("#product-new-dialog")).toHaveAttribute("open", "");
  const generatedCode = await page.locator("#product-new-code").inputValue();
  expect(Number(generatedCode)).toBeGreaterThan(10000);

  const costInput = page.locator("#product-new-cost");
  await costInput.focus();
  await page.waitForTimeout(60);
  await expect(costInput).toBeFocused();
  await expect(page.locator("#product-new-name")).toHaveValue("");

  await page.locator("#product-new-name").fill("Runtime Test Product");
  await page.locator("#product-new-barcode").fill("9900000000012");
  await page.locator("#product-new-unit").selectOption("шт");
  await page.locator("#product-new-cost").fill("10");
  await page.locator("#product-new-price").fill("20");
  await page.locator("#product-new-min-price").fill("15");
  await page.locator("#product-new-min-stock").fill("2");
  await page.locator("#save-new-product").click();
  await expect(page.locator("#product-new-dialog")).not.toHaveAttribute("open", "");

  const created = await page.evaluate(() => {
    const product = window.OUTPOST_DEMO_API.getState().products.find((item) => item.barcode === "9900000000012");
    return product ? {
      id: product.id,
      code: product.code,
      name: product.name,
      price: product.price,
      cost: product.cost,
      minimumPrice: product.minimumPrice,
      minimumStock: product.minimumStock,
      stock: product.stock,
      unit: product.unit,
    } : null;
  });
  expect(created).toEqual({
    id: "pd0001",
    code: generatedCode,
    name: "Runtime Test Product",
    price: 20,
    cost: 10,
    minimumPrice: 15,
    minimumStock: 2,
    stock: 0,
    unit: "шт",
  });

  await expect(page.locator("#products-table")).toContainText("Runtime Test Product");
  await page.locator("#product-movements").click();
  await expect(page.locator("#stock-movements-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#stock-movements-count")).toHaveText("Операцій: 0");
  await page.locator("#stock-movements-dialog").getByText("Закрити", { exact: true }).click();

  await page.locator('[data-view="sale"]').click();
  await page.locator("#product-search").fill("9900000000012");
  await page.locator("#product-search").press("Enter");
  await expect(page.locator("#cart-count")).toHaveText("1 поз.");

  await page.locator("#cart-discount-selected").click();
  await page.locator("#discount-percent").fill("30");
  await page.locator("#apply-discount").click();
  await expect(page.locator("#discount-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#discount-error")).toContainText("нижче мінімально дозволеної");
  await page.locator("#discount-percent").fill("20");
  await page.locator("#apply-discount").click();
  await expect(page.locator("#discount-dialog")).not.toHaveAttribute("open", "");

  await page.keyboard.press("F2");
  await expect(page.locator("#cash-payment-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#cash-payment-received")).toBeFocused();
  await page.locator("#cash-payment-received").press("Enter");
  await expect(page.locator("#cash-payment-dialog")).not.toHaveAttribute("open", "");
  const saleId = await page.evaluate(() => window.OUTPOST_DEMO_API.getState().sales[0].id);
  const afterSale = await page.evaluate((productId) => {
    const product = window.OUTPOST_DEMO_API.getState().products.find((item) => item.id === productId);
    const sale = window.OUTPOST_DEMO_API.getState().sales[0];
    return {
      stock: product.stock,
      total: sale.total,
      discount: sale.lines[0].discountPercent,
      soldPrice: sale.lines[0].price,
    };
  }, created.id);
  expect(afterSale.stock).toBe(-1);
  expect(afterSale.total).toBe(16);
  expect(afterSale.discount).toBe(20);
  expect(afterSale.soldPrice).toBe(16);

  await page.locator('[data-view="products"]').click();
  await page.locator("#product-stock-search").fill("9900000000012");
  await page.locator("#products-table tr").first().click();
  await page.locator("#product-movements").click();
  await expect(page.locator("#stock-movements-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#stock-movements-table")).toContainText("Продаж");
  await expect(page.locator("#stock-movements-table")).toContainText(saleId);
  await expect(page.locator("#stock-movements-table")).toContainText("-1");
  await page.locator("#stock-movements-dialog").getByText("Закрити", { exact: true }).click();

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  await expect.poll(() => page.evaluate(() =>
    window.OUTPOST_DEMO_API.getState().products.some((item) => item.barcode === "9900000000012"),
  )).toBe(false);

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("demo customer debt ledger tracks repayment and write-off", async ({ browser }) => {
  test.setTimeout(60_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_MODULES?.getCashSummary)),
    { message: "finance module should initialize for debt ledger" },
  ).toBe(true);

  const target = await page.evaluate(() => {
    const customers = window.OUTPOST_DEMO_API.getState().customers
      .filter((customer) => Number(customer.debt) > 1)
      .sort((a, b) => Number(b.debt) - Number(a.debt));
    const customer = customers[0];
    const cash = window.OUTPOST_DEMO_MODULES.getCashSummary();
    return customer ? {
      id: customer.id,
      name: customer.name,
      debt: Number(customer.debt),
      cashExpected: Number(cash.expected),
      seededRepayments: window.OUTPOST_DEMO_API.getState().cashMovements.filter((item) =>
        item.type === "DebtRepayment" && item.customerId === customer.id
      ).length,
    } : null;
  });
  expect(target).not.toBeNull();
  expect(target.debt).toBeGreaterThan(1);

  const repayment = Math.round((Math.min(10, target.debt / 2) + Number.EPSILON) * 100) / 100;
  await page.locator('[data-view="customers"]').click();
  await page.locator('[data-customer-id="' + target.id + '"]').click();
  await expect(page.locator("#customer-detail")).toContainText(target.name);
  await expect(page.locator("#debt-ledger-table")).toBeVisible();

  await page.locator("#repay-amount").fill(repayment.toFixed(2));
  await page.locator("#repay-debt").click();

  const afterRepayment = await page.evaluate((customerId) => {
    const state = window.OUTPOST_DEMO_API.getState();
    const customer = state.customers.find((item) => item.id === customerId);
    const movement = state.cashMovements.find((item) =>
      item.type === "DebtRepayment" && item.customerId === customerId
    );
    const cash = window.OUTPOST_DEMO_MODULES.getCashSummary();
    return {
      debt: Number(customer.debt),
      movementAmount: movement?.amount,
      movementCustomerId: movement?.customerId,
      cashExpected: Number(cash.expected),
    };
  }, target.id);
  expect(afterRepayment.debt).toBe(Math.round((target.debt - repayment + Number.EPSILON) * 100) / 100);
  expect(afterRepayment.movementAmount).toBe(repayment);
  expect(afterRepayment.movementCustomerId).toBe(target.id);
  expect(afterRepayment.cashExpected).toBe(
    Math.round((target.cashExpected + repayment + Number.EPSILON) * 100) / 100,
  );
  await expect(page.locator("#debt-ledger-table")).toContainText("Повернення боргу");

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#writeoff-debt").click();

  const afterWriteOff = await page.evaluate((customerId) => {
    const state = window.OUTPOST_DEMO_API.getState();
    const customer = state.customers.find((item) => item.id === customerId);
    const record = state.debtWriteOffs?.[0];
    const cash = window.OUTPOST_DEMO_MODULES.getCashSummary();
    return {
      debt: Number(customer.debt),
      writeOffCustomerId: record?.customerId,
      writeOffAmount: record?.amount,
      cashExpected: Number(cash.expected),
    };
  }, target.id);
  expect(afterWriteOff.debt).toBe(0);
  expect(afterWriteOff.writeOffCustomerId).toBe(target.id);
  expect(afterWriteOff.writeOffAmount).toBe(afterRepayment.debt);
  expect(afterWriteOff.cashExpected).toBe(afterRepayment.cashExpected);
  await expect(page.locator("#debt-ledger-table")).toContainText("Списання боргу");
  await expect(page.locator("#writeoff-debt")).toBeDisabled();

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  const resetDebt = await page.evaluate((customerId) => {
    const state = window.OUTPOST_DEMO_API.getState();
    const customer = state.customers.find((item) => item.id === customerId);
    return {
      debt: Number(customer.debt),
      writeOffCount: state.debtWriteOffs?.length || 0,
      manualRepayments: state.cashMovements.filter((item) =>
        item.type === "DebtRepayment" && item.customerId === customerId
      ).length,
    };
  }, target.id);
  expect(resetDebt.debt).toBe(target.debt);
  expect(resetDebt.writeOffCount).toBe(0);
  expect(resetDebt.manualRepayments).toBe(target.seededRepayments);

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("demo appearance settings persist locally", async ({ browser }) => {
  test.setTimeout(45_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_API?.getAppearance)),
    { message: "appearance API should initialize" },
  ).toBe(true);

  await page.locator('[data-view="settings"]').click();
  await expect(page.locator('[data-view-panel="settings"]')).toHaveClass(/is-active/);

  await page.locator("#appearance-theme").selectOption("dark");
  await page.locator("#appearance-accent").selectOption("purple");
  await page.locator("#appearance-font").selectOption("16");
  await page.locator("#appearance-bold").check();
  await page.locator("#appearance-apply").click();

  const applied = await page.evaluate(() => ({
    appearance: window.OUTPOST_DEMO_API.getAppearance(),
    theme: document.documentElement.dataset.demoTheme,
    accent: document.documentElement.dataset.demoAccent,
    fontSize: document.documentElement.dataset.demoFontSize,
    bold: document.documentElement.dataset.demoBold,
    accentCss: getComputedStyle(document.documentElement).getPropertyValue("--blue").trim(),
  }));
  expect(applied.appearance).toEqual({ theme: "dark", accent: "purple", fontSize: 16, bold: true });
  expect(applied.theme).toBe("dark");
  expect(applied.accent).toBe("purple");
  expect(applied.fontSize).toBe("16");
  expect(applied.bold).toBe("true");
  expect(applied.accentCss).toBe("#7957d5");
  await expect(page.locator("#appearance-summary")).toContainText("темна тема");
  await expect(page.locator("#appearance-summary")).toContainText("фіолетовий акцент");
  await expect(page.locator("#appearance-summary")).toContainText("шрифт 16");
  await expect(page.locator("#appearance-summary")).toContainText("жирний текст");

  await page.reload({ waitUntil: "load" });
  const persisted = await page.evaluate(() => window.OUTPOST_DEMO_API.getAppearance());
  expect(persisted).toEqual({ theme: "dark", accent: "purple", fontSize: 16, bold: true });
  expect(await page.locator("html").getAttribute("data-demo-theme")).toBe("dark");

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  const afterDataReset = await page.evaluate(() => window.OUTPOST_DEMO_API.getAppearance());
  expect(afterDataReset).toEqual(persisted);

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("command center chart and layout preferences persist without changing demo records", async ({page}) => {
  test.setTimeout(45000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(origin+'/demo',{waitUntil:'load'});
  await page.locator('.demo-nav[data-view="home"]').click();
  const before=await page.evaluate(()=>localStorage.getItem('outpost_online_demo_v2'));
  await page.locator('[data-dashboard-period="14"]').click();
  await page.locator('[data-dashboard-chart="line"]').click();
  await expect(page.locator('#dashboard-chart svg')).toHaveAccessibleName('Чиста виручка за 14 днів');
  await expect(page.locator('#dashboard-chart polyline')).toHaveCount(1);
  await page.locator('#dashboard-configure').click();
  const dialog=page.locator('#dashboard-layout-dialog');await expect(dialog).toBeVisible();
  await page.keyboard.press('F7');await expect(dialog).toBeVisible();
  await expect(page.locator('#product-search-dialog')).toBeHidden();
  await dialog.locator('[data-layout-id="CashBalance"] input').uncheck();
  await dialog.locator('[data-layout-id="Revenue"] [data-layout-move="-1"]').click();
  await dialog.locator('[data-dashboard-settings-tab="sections"]').click();
  await dialog.locator('[data-layout-id="Chart"] input').uncheck();
  await dialog.locator('#dashboard-layout-save').click();
  await expect(page.locator('[data-dashboard-metric="CashBalance"]')).toHaveCount(0);
  await expect(page.locator('.dashboard-kpi').first()).toHaveAttribute('data-dashboard-metric','Revenue');
  await expect(page.locator('[data-dashboard-section="Chart"]')).toBeHidden();
  await page.reload({waitUntil:'load'});await page.locator('.demo-nav[data-view="home"]').click();
  await expect(page.locator('.dashboard-kpi')).toHaveCount(10);
  await expect(page.locator('.dashboard-kpi').first()).toHaveAttribute('data-dashboard-metric','Revenue');
  await expect(page.locator('[data-dashboard-section="Chart"]')).toBeHidden();
  await page.locator('#dashboard-configure').click();
  await page.keyboard.press('Escape');await expect(dialog).toBeHidden();
  await expect(page.locator('#dashboard-configure')).toBeFocused();
  await page.locator('#dashboard-configure').click();
  await dialog.locator('#dashboard-layout-defaults').click();
  await dialog.locator('#dashboard-layout-save').click();
  await expect(page.locator('.dashboard-kpi')).toHaveCount(11);
  await expect(page.locator('[data-dashboard-section="Chart"]')).toBeVisible();
  await expect(page.locator('#dashboard-chart svg')).toHaveAccessibleName('Чиста виручка за 14 днів');
  expect(await page.evaluate(()=>localStorage.getItem('outpost_online_demo_v2'))).toBe(before);
  expect(errors).toEqual([]);
});

test("demo cash payment dialog calculates change and blocks underpayment", async ({ browser }) => {
  test.setTimeout(45_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_API?.getCart)),
    { message: "cash-payment demo API should initialize" },
  ).toBe(true);

  const target = await page.evaluate(() => {
    const product = window.OUTPOST_DEMO_API.getState().products.find((item) => item.barcode && Number(item.price) > 0);
    return { barcode: product.barcode, price: Number(product.price) };
  });

  await page.locator("#product-search").fill(target.barcode);
  await page.locator("#product-search").press("Enter");
  await page.keyboard.press("F2");

  await expect(page.locator("#cash-payment-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#cash-payment-received")).toBeFocused();
  await expect(page.locator("#cash-payment-received")).toHaveValue(target.price.toFixed(2));

  await page.locator("#cash-payment-received").fill((target.price - 1).toFixed(2));
  await page.locator("#confirm-cash-payment").click();
  await expect(page.locator("#cash-payment-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#cash-payment-error")).toContainText("меншою за суму чека");
  expect(await page.evaluate(() => window.OUTPOST_DEMO_API.getCart().length)).toBe(1);

  await page.locator("#cash-payment-received").fill((target.price + 100).toFixed(2));
  await expect(page.locator("#cash-payment-change")).toContainText("100");
  await page.locator("#cash-payment-received").press("Enter");
  await expect(page.locator("#cash-payment-dialog")).not.toHaveAttribute("open", "");
  await expect(page.locator("#product-search")).toBeFocused();

  const sale = await page.evaluate(() => window.OUTPOST_DEMO_API.getState().sales[0]);
  expect(sale.payment).toBe("cash");
  expect(Number(sale.total)).toBe(target.price);
  expect(Number(sale.cash)).toBe(target.price);
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("demo mixed and debt payments keep keyboard-first focus and Enter confirmation", async ({ browser }) => {
  test.setTimeout(50_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_API?.getCart)),
    { message: "payment keyboard demo API should initialize" },
  ).toBe(true);

  const target = await page.evaluate(() => {
    const state = window.OUTPOST_DEMO_API.getState();
    const product = state.products.find((item) => item.barcode && Number(item.price) > 0);
    const customer = state.customers[0];
    return {
      barcode: product.barcode,
      productId: product.id,
      customerId: customer.id,
      customerName: customer.name,
      customerDebt: Number(customer.debt || 0),
    };
  });

  await page.locator("#product-search").fill(target.barcode);
  await page.locator("#product-search").press("Enter");
  await page.keyboard.press("F4");
  await expect(page.locator("#mixed-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#mixed-cash")).toBeFocused();
  await page.locator("#mixed-cash").press("Enter");
  await expect(page.locator("#mixed-dialog")).not.toHaveAttribute("open", "");
  await expect(page.locator("#product-search")).toBeFocused();

  const mixedSale = await page.evaluate(() => window.OUTPOST_DEMO_API.getState().sales[0]);
  expect(mixedSale.payment).toBe("mixed");
  expect(Number(mixedSale.cash) + Number(mixedSale.card)).toBe(Number(mixedSale.total));
  await page.locator("#product-search").fill(target.barcode);
  await page.locator("#product-search").press("Enter");
  await page.keyboard.press("F5");
  await expect(page.locator("#debt-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#debt-customer")).toBeFocused();
  await page.locator("#debt-customer").selectOption(target.customerId);
  await page.locator("#debt-customer").press("Enter");
  await expect(page.locator("#debt-dialog")).not.toHaveAttribute("open", "");
  await expect(page.locator("#product-search")).toBeFocused();
  await expect(page.locator("#selected-client-label")).toHaveText(target.customerName);

  const debtState = await page.evaluate((customerId) => {
    const state = window.OUTPOST_DEMO_API.getState();
    const sale = state.sales[0];
    const customer = state.customers.find((item) => item.id === customerId);
    return { payment: sale.payment, customerId: sale.customerId, total: Number(sale.total), debt: Number(customer.debt) };
  }, target.customerId);
  expect(debtState.payment).toBe("debt");
  expect(debtState.customerId).toBe(target.customerId);
  expect(debtState.debt).toBe(Math.round((target.customerDebt + debtState.total + Number.EPSILON) * 100) / 100);

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("demo F1 opens seller help and Escape closes it", async ({ browser }) => {
  test.setTimeout(35_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await page.keyboard.press("F1");
  await expect(page.locator("#seller-help-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#seller-help-dialog")).toContainText("Довідка продавця");
  await expect(page.locator("#seller-help-dialog")).toContainText("F2");
  await expect(page.locator("#seller-help-dialog")).toContainText("F7");
  await expect(page.locator("#seller-help-dialog .dialog-close")).toBeFocused();

  await page.keyboard.press("F1");
  await expect(page.locator("#seller-help-dialog")).toHaveAttribute("open", "");
  await page.keyboard.press("Escape");
  await expect(page.locator("#seller-help-dialog")).not.toHaveAttribute("open", "");
  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("demo repeated F7/F4/F5 shortcuts keep dialogs stable", async ({ browser }) => {
  test.setTimeout(45_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_API?.getCart)),
    { message: "repeated-shortcut demo API should initialize" },
  ).toBe(true);

  await page.keyboard.press("F7");
  await expect(page.locator("#product-search-dialog")).toHaveAttribute("open", "");
  await page.keyboard.press("F7");
  await expect(page.locator("#product-search-dialog")).toHaveAttribute("open", "");
  await page.keyboard.press("Escape");
  await expect(page.locator("#product-search-dialog")).not.toHaveAttribute("open", "");

  const target = await page.evaluate(() => {
    const product = window.OUTPOST_DEMO_API.getState().products.find((item) => item.barcode && Number(item.price) > 0);
    return product.barcode;
  });
  await page.locator("#product-search").fill(target);
  await page.locator("#product-search").press("Enter");

  await page.keyboard.press("F4");
  await expect(page.locator("#mixed-dialog")).toHaveAttribute("open", "");
  await page.keyboard.press("F4");
  await expect(page.locator("#mixed-dialog")).toHaveAttribute("open", "");
  await page.keyboard.press("Escape");
  await expect(page.locator("#mixed-dialog")).not.toHaveAttribute("open", "");

  await page.keyboard.press("F5");
  await expect(page.locator("#debt-dialog")).toHaveAttribute("open", "");
  await page.keyboard.press("F5");
  await expect(page.locator("#debt-dialog")).toHaveAttribute("open", "");
  await page.keyboard.press("Escape");
  await expect(page.locator("#debt-dialog")).not.toHaveAttribute("open", "");

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  await context.close();
});


test("demo modal dialogs block cross-workflow F1-F7 shortcuts", async ({ browser }) => {
  test.setTimeout(45_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_API?.getCart)),
    { message: "modal shortcut guard demo API should initialize" },
  ).toBe(true);

  const barcode = await page.evaluate(() => {
    const product = window.OUTPOST_DEMO_API.getState().products.find((item) => item.barcode && Number(item.price) > 0);
    return product.barcode;
  });
  await page.locator("#product-search").fill(barcode);
  await page.locator("#product-search").press("Enter");
  await expect(page.locator("#cart-count")).toHaveText("1 поз.");

  await page.keyboard.press("F4");
  await expect(page.locator("#mixed-dialog")).toHaveAttribute("open", "");

  for (const key of ["F1", "F2", "F3", "F5", "F6", "F7"]) {
    await page.keyboard.press(key);
    await expect(page.locator("#mixed-dialog")).toHaveAttribute("open", "");
    await expect(page.locator("#seller-help-dialog")).not.toHaveAttribute("open", "");
    await expect(page.locator("#cash-payment-dialog")).not.toHaveAttribute("open", "");
    await expect(page.locator("#debt-dialog")).not.toHaveAttribute("open", "");
    await expect(page.locator("#product-search-dialog")).not.toHaveAttribute("open", "");
    await expect(page.locator('[data-view-panel="sale"]')).toHaveClass(/is-active/);
    expect(await page.evaluate(() => window.OUTPOST_DEMO_API.getCart().length)).toBe(1);
  }

  await page.keyboard.press("Escape");
  await expect(page.locator("#mixed-dialog")).not.toHaveAttribute("open", "");
  expect(pageErrors, pageErrors.join("\n")).toEqual([]);

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  await context.close();
});


test("demo dialog cancellation restores the keyboard workflow", async ({ browser }) => {
  test.setTimeout(55_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_API?.getCart)),
    { message: "dialog focus-restore demo API should initialize" },
  ).toBe(true);

  await page.keyboard.press("F1");
  await expect(page.locator("#seller-help-dialog")).toHaveAttribute("open", "");
  await page.keyboard.press("Escape");
  await expect(page.locator("#seller-help-dialog")).not.toHaveAttribute("open", "");
  await expect(page.locator("#product-search")).toBeFocused();

  await page.keyboard.press("F7");
  await expect(page.locator("#product-search-dialog")).toHaveAttribute("open", "");
  await page.keyboard.press("Escape");
  await expect(page.locator("#product-search-dialog")).not.toHaveAttribute("open", "");
  await expect(page.locator("#product-search")).toBeFocused();

  const barcode = await page.evaluate(() => {
    const product = window.OUTPOST_DEMO_API.getState().products.find((item) => item.barcode && Number(item.price) > 0);
    return product.barcode;
  });
  await page.locator("#product-search").fill(barcode);
  await page.locator("#product-search").press("Enter");

  for (const key of ["F2", "F4", "F5"]) {
    await page.keyboard.press(key);
    const dialogSelector = key === "F2" ? "#cash-payment-dialog" : key === "F4" ? "#mixed-dialog" : "#debt-dialog";
    await expect(page.locator(dialogSelector)).toHaveAttribute("open", "");
    await page.keyboard.press("Escape");
    await expect(page.locator(dialogSelector)).not.toHaveAttribute("open", "");
    await expect(page.locator("#product-search")).toBeFocused();
    expect(await page.evaluate(() => window.OUTPOST_DEMO_API.getCart().length)).toBe(1);
  }

  await page.keyboard.press("F6");
  await expect(page.locator('[data-view-panel="purchases"]')).toHaveClass(/is-active/);
  await page.locator("#open-purchase-item").click();
  await expect(page.locator("#purchase-item-dialog")).toHaveAttribute("open", "");
  await page.locator("#purchase-find-product").click();
  await expect(page.locator("#purchase-item-dialog")).not.toHaveAttribute("open", "");
  await expect(page.locator("#product-search-dialog")).toHaveAttribute("open", "");
  await page.keyboard.press("Escape");
  await expect(page.locator("#product-search-dialog")).not.toHaveAttribute("open", "");
  await expect(page.locator("#purchase-item-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#purchase-item-barcode")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.locator("#purchase-item-dialog")).not.toHaveAttribute("open", "");

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  await context.close();
});


test("demo payment shortcuts cannot complete a hidden off-screen sale", async ({ browser }) => {
  test.setTimeout(45_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_API?.getCart)),
    { message: "off-screen payment guard demo API should initialize" },
  ).toBe(true);

  const barcode = await page.evaluate(() => {
    const product = window.OUTPOST_DEMO_API.getState().products.find((item) => item.barcode && Number(item.price) > 0);
    return product.barcode;
  });
  const salesBefore = await page.evaluate(() => window.OUTPOST_DEMO_API.getState().sales.length);

  await page.locator("#product-search").fill(barcode);
  await page.locator("#product-search").press("Enter");
  await expect(page.locator("#cart-count")).toHaveText("1 поз.");

  await page.locator('[data-view="products"]').click();
  await expect(page.locator('[data-view-panel="products"]')).toHaveClass(/is-active/);
  await page.keyboard.press("F3");

  await expect(page.locator('[data-view-panel="sale"]')).toHaveClass(/is-active/);
  await expect(page.locator("#product-search")).toBeFocused();
  await expect(page.locator("#toast")).toContainText("Натисніть F3 ще раз");
  expect(await page.evaluate(() => window.OUTPOST_DEMO_API.getCart().length)).toBe(1);
  expect(await page.evaluate(() => window.OUTPOST_DEMO_API.getState().sales.length)).toBe(salesBefore);

  await page.keyboard.press("F3");
  await expect.poll(
    () => page.evaluate((count) => window.OUTPOST_DEMO_API.getState().sales.length === count + 1, salesBefore),
    { message: "second F3 on Sales should complete the visible cart" },
  ).toBe(true);
  expect(await page.evaluate(() => window.OUTPOST_DEMO_API.getCart().length)).toBe(0);
  await expect(page.locator("#product-search")).toBeFocused();

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  await context.close();
});


test("demo F7 search supports arrow-key result selection", async ({ browser }) => {
  test.setTimeout(40_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await page.keyboard.press("F7");
  await expect(page.locator("#product-search-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#f7-name")).toBeFocused();

  const firstSelected = await page.locator("#f7-results .is-selected").getAttribute("data-f7-product");
  expect(firstSelected).toBeTruthy();
  await page.keyboard.press("ArrowDown");
  const secondSelected = await page.locator("#f7-results .is-selected").getAttribute("data-f7-product");
  expect(secondSelected).toBeTruthy();
  expect(secondSelected).not.toBe(firstSelected);

  await page.keyboard.press("Enter");
  await expect(page.locator("#product-search-dialog")).not.toHaveAttribute("open", "");
  const cart = await page.evaluate(() => window.OUTPOST_DEMO_API.getCart());
  expect(cart).toHaveLength(1);
  expect(cart[0].productId).toBe(secondSelected);
  await expect(page.locator("#product-search")).toBeFocused();

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  await context.close();
});


test("demo sale Enter falls back to F7 search for non-exact text", async ({ browser }) => {
  test.setTimeout(40_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_API?.getCart)),
    { message: "sale Enter fallback demo API should initialize" },
  ).toBe(true);

  const probe = await page.evaluate(() => {
    const product = window.OUTPOST_DEMO_API.getState().products.find((item) => {
      const parts = String(item.name || "").trim().split(/\s+/);
      return parts[0] && parts[0].length >= 4 && String(item.name).toLowerCase() !== parts[0].toLowerCase();
    });
    const fragment = String(product.name).trim().split(/\s+/)[0];
    return { fragment, productName: product.name };
  });

  await page.locator("#product-search").fill(probe.fragment);
  await page.locator("#product-search").press("Enter");
  await expect(page.locator("#product-search-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#f7-name")).toHaveValue(probe.fragment);
  expect(await page.locator("#f7-results .search-result-row").count()).toBeGreaterThan(0);

  const selectedId = await page.locator("#f7-results .is-selected").getAttribute("data-f7-product");
  expect(selectedId).toBeTruthy();
  await page.keyboard.press("Enter");
  await expect(page.locator("#product-search-dialog")).not.toHaveAttribute("open", "");
  const cart = await page.evaluate(() => window.OUTPOST_DEMO_API.getCart());
  expect(cart).toHaveLength(1);
  expect(cart[0].productId).toBe(selectedId);
  await expect(page.locator("#product-search")).toBeFocused();

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();
  await context.close();
});


test("demo F6 enters Purchases with the primary action focused", async ({ browser }) => {
  test.setTimeout(35_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await page.keyboard.press("F6");
  await expect(page.locator('[data-view-panel="purchases"]')).toHaveClass(/is-active/);
  await expect(page.locator("#open-purchase-item")).toBeFocused();

  await page.keyboard.press("Enter");
  await expect(page.locator("#purchase-item-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#purchase-item-barcode")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.locator("#purchase-item-dialog")).not.toHaveAttribute("open", "");

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("demo parallel checks isolate carts and preserve unfinished sales on reload", async ({ browser }) => {
  test.setTimeout(30_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  const tabs = page.locator(".client-tab");
  await expect(tabs.nth(0)).toHaveClass(/is-active/);
  const barcode=await page.evaluate(()=>window.OUTPOST_DEMO_API.getState().products.find(p=>p.barcode).barcode);
  await page.locator('#product-search').fill(barcode);await page.locator('#product-search').press('Enter');
  await expect(page.locator('#cart-count')).toHaveText('1 поз.');
  await tabs.nth(1).click();
  await expect(tabs.nth(1)).toHaveClass(/is-active/);await expect(page.locator('#cart-count')).toHaveText('0 поз.');
  await page.locator('#product-search').fill(barcode);await page.locator('#product-search').press('Enter');
  await page.locator('[data-cart-quantity]').fill('2');await page.locator('[data-cart-quantity]').press('Tab');
  await page.reload({waitUntil:'load'});await expect(tabs.nth(1)).toHaveClass(/is-active/);
  await expect(page.locator('[data-cart-quantity]')).toHaveValue('2');
  await page.locator('[data-pay="card"]').click();await expect(page.locator('#cart-count')).toHaveText('0 поз.');
  await tabs.nth(0).click();await expect(page.locator('[data-cart-quantity]')).toHaveValue('1');

  await page.locator(".client-tab-add").click();
  await expect(tabs).toHaveCount(5);await expect(tabs.nth(4)).toHaveClass(/is-active/);await expect(page.locator('#cart-count')).toHaveText('0 поз.');

  await page.keyboard.press("F1");
  await expect(page.locator("#seller-help-dialog")).toContainText("↑ / ↓");
  await expect(page.locator("#seller-help-dialog")).toContainText("Enter");
  await page.keyboard.press("Escape");

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("demo main navigation and browser-only scope stay intact", async ({ browser }) => {
  test.setTimeout(45_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(window.OUTPOST_DEMO_API)),
    { message: "demo API should initialize" },
  ).toBe(true);

  const views = ["home", "sale", "purchases", "stockops", "products", "customers", "finance", "reports", "settings"];
  for (const view of views) {
    await page.locator('[data-view="' + view + '"]').click();
    await expect(page.locator('[data-view-panel="' + view + '"]')).toHaveClass(/is-active/);
    await expect(page.locator('[data-view="' + view + '"]')).toHaveClass(/is-active/);
  }

  const browserOnlyLabels = (await page.locator("[data-demo-info]").allTextContents())
    .map((value) => value.replace(/\s+/g, " ").trim())
    .sort();
  // The remaining explicitly desktop-only tools retain their limitation labels.
  expect(browserOnlyLabels).toEqual([
    "Відкрити імпортер",
    "Відкрити папку даних",
    "Керувати користувачами",
    "Обрізати залишки до ±999",
    "Повна очистка БД",
  ].sort());

  await expect(page.locator("#appearance-apply")).toBeEnabled();
  await expect(page.locator("#appearance-theme")).toBeEnabled();
  await expect(page.locator("#appearance-accent")).toBeEnabled();
  await expect(page.locator("#appearance-font")).toBeEnabled();

  const navDisabled = await page.locator(".demo-nav:disabled").count();
  expect(navDisabled).toBe(0);

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("demo discounted cash sale returns the exact paid amount", async ({ browser }) => {
  test.setTimeout(60_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  await expect.poll(
    () => page.evaluate(() => Boolean(
      window.OUTPOST_DEMO_API?.getCart &&
      window.OUTPOST_DEMO_MODULES?.getCashSummary &&
      window.OUTPOST_DEMO_RETURNS?.openReturn
    )),
    { message: "sale, cash and return APIs should initialize" },
  ).toBe(true);

  const target = await page.evaluate(() => {
    const state = window.OUTPOST_DEMO_API.getState();
    const product = state.products.find((item) => {
      const price = Number(item.price || 0);
      const minimum = Number(item.minimumPrice || 0);
      return item.barcode && price > 0 && (!minimum || minimum <= price * 0.9 + 0.004);
    });
    const cash = window.OUTPOST_DEMO_MODULES.getCashSummary();
    return product ? {
      id: product.id,
      barcode: product.barcode,
      price: Number(product.price),
      stock: Number(product.stock),
      cashExpected: Number(cash.expected),
    } : null;
  });
  expect(target).not.toBeNull();

  await page.locator('[data-view="sale"]').click();
  await page.locator("#product-search").fill(target.barcode);
  await page.locator("#product-search").press("Enter");
  await expect(page.locator("#cart-count")).toHaveText("1 поз.");
  await page.locator("#cart-inc-selected").click();

  await page.locator("#cart-discount-selected").click();
  await expect(page.locator("#discount-dialog")).toHaveAttribute("open", "");
  await page.locator("#discount-percent").fill("10");
  await page.locator("#apply-discount").click();
  await expect(page.locator("#discount-dialog")).not.toHaveAttribute("open", "");

  const discountedUnit = Math.round((target.price * 0.9 + Number.EPSILON) * 100) / 100;
  const paidTotal = Math.round((discountedUnit * 2 + Number.EPSILON) * 100) / 100;
  const cart = await page.evaluate(() => ({
    lines: window.OUTPOST_DEMO_API.getCart(),
    total: window.OUTPOST_DEMO_API.getCartTotal(),
  }));
  expect(cart.lines).toHaveLength(1);
  expect(cart.lines[0].qty).toBe(2);
  expect(cart.lines[0].discountPercent).toBe(10);
  expect(cart.total).toBe(paidTotal);

  await page.keyboard.press("F2");
  await expect(page.locator("#cash-payment-dialog")).toHaveAttribute("open", "");
  await expect(page.locator("#cash-payment-received")).toBeFocused();
  await page.locator("#cash-payment-received").press("Enter");
  await expect(page.locator("#cash-payment-dialog")).not.toHaveAttribute("open", "");

  const afterSale = await page.evaluate((productId) => {
    const state = window.OUTPOST_DEMO_API.getState();
    const sale = state.sales[0];
    const product = state.products.find((item) => item.id === productId);
    const cash = window.OUTPOST_DEMO_MODULES.getCashSummary();
    return {
      saleId: sale.id,
      payment: sale.payment,
      total: Number(sale.total),
      lineQty: Number(sale.lines?.[0]?.qty),
      linePrice: Number(sale.lines?.[0]?.price),
      discountPercent: Number(sale.lines?.[0]?.discountPercent),
      stock: Number(product.stock),
      cashExpected: Number(cash.expected),
    };
  }, target.id);
  expect(afterSale.payment).toBe("cash");
  expect(afterSale.total).toBe(paidTotal);
  expect(afterSale.lineQty).toBe(2);
  expect(afterSale.linePrice).toBe(discountedUnit);
  expect(afterSale.discountPercent).toBe(10);
  expect(afterSale.stock).toBe(Math.round((target.stock - 2 + Number.EPSILON) * 100) / 100);
  expect(afterSale.cashExpected).toBe(
    Math.round((target.cashExpected + paidTotal + Number.EPSILON) * 100) / 100,
  );

  await page.locator('[data-view-link="history"]').first().click();
  const returnButton = page.locator('[data-return-sale="' + afterSale.saleId + '"]');
  await expect(returnButton).toBeEnabled();
  await returnButton.click();
  await page.locator("#return-all-available").click();
  await page.locator("#open-return-payment").click();
  await expect(page.locator("#return-payment-cash")).toHaveValue(paidTotal.toFixed(2));
  await page.locator("#confirm-sale-return").click();

  const afterReturn = await page.evaluate(({ productId, saleId }) => {
    const state = window.OUTPOST_DEMO_API.getState();
    const product = state.products.find((item) => item.id === productId);
    const record = state.returns.find((item) => item.saleId === saleId);
    const cashMovement = state.cashMovements.find((item) =>
      item.type === "SaleReturn" && String(item.comment || "").includes(saleId)
    );
    const cash = window.OUTPOST_DEMO_MODULES.getCashSummary();
    return {
      returnTotal: Number(record?.total),
      returnQty: Number(record?.lines?.[0]?.qty),
      returnPrice: Number(record?.lines?.[0]?.price),
      returnAmount: Number(record?.lines?.[0]?.amount),
      cashMovementAmount: Number(cashMovement?.amount),
      stock: Number(product.stock),
      cashExpected: Number(cash.expected),
    };
  }, { productId: target.id, saleId: afterSale.saleId });
  expect(afterReturn.returnTotal).toBe(paidTotal);
  expect(afterReturn.returnQty).toBe(2);
  expect(afterReturn.returnPrice).toBe(discountedUnit);
  expect(afterReturn.returnAmount).toBe(paidTotal);
  expect(afterReturn.cashMovementAmount).toBe(paidTotal);
  expect(afterReturn.stock).toBe(target.stock);
  expect(afterReturn.cashExpected).toBe(target.cashExpected);

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("[data-reset-demo]").first().click();

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test('fictional month reports open historical receipts and reconcile net revenue',async({page})=>{
  await page.goto(origin+'/demo',{waitUntil:'load'});
  const expected=await page.evaluate(()=>{const s=window.OUTPOST_DEMO_API.getState();return {receipts:s.sales.length,net:window.OUTPOST_DEMO_API.round2(s.sales.reduce((n,x)=>n+x.total,0)-s.returns.reduce((n,x)=>n+x.total,0)),firstDay:s.datasetMeta.from};});
  expect(expected.receipts).toBeGreaterThan(1000);
  await page.locator('[data-view="reports"]').click();
  await expect(page.locator('#report-daily tr')).toHaveCount(30);
  await expect(page.locator('#report-products tr')).toHaveCount(12);
  const netText=await page.evaluate(n=>window.OUTPOST_DEMO_API.money(n),expected.net);
  await expect(page.locator('#stats-grid .desktop-card').first()).toContainText(netText);
  await page.locator('#reports-period').selectOption('1');await expect(page.locator('#report-daily tr')).toHaveCount(1);
  await page.locator('#reports-period').selectOption('30');
  await page.locator('[data-report-day="'+expected.firstDay+'"]').click();
  await expect(page.locator('#history-from')).toHaveValue(expected.firstDay);await expect(page.locator('#sales-history tr')).not.toHaveCount(0);
  await page.locator('[data-open-sale]').first().click();await expect(page.locator('#demo-document-dialog')).toBeVisible();
  await expect(page.locator('#demo-document-lines tr')).not.toHaveCount(0);
  await page.keyboard.press('F7');await expect(page.locator('#product-search-dialog')).toBeHidden();await page.keyboard.press('Escape');
  await page.locator('#history-payment').selectOption('card');
  const methods=await page.locator('#sales-history tr').evaluateAll(rows=>rows.map(r=>r.children[2]?.textContent));expect(methods.length).toBeGreaterThan(0);expect(methods.every(x=>x==='Картка')).toBe(true);
});

test('purchase drafts survive switching and reload then post exactly once with fractional quantities',async({page})=>{
  await page.goto(origin+'/demo',{waitUntil:'load'});await page.locator('[data-view="purchases"]').click();
  await page.locator('#open-purchase-item').click();const product=await page.evaluate(()=>window.OUTPOST_DEMO_API.getState().products[0]);
  await page.locator('#purchase-item-qty').fill('0.568');await page.locator('#add-purchase-draft-line').click();
  await expect(page.locator('#purchase-draft-lines')).toContainText('0,568');
  const firstId=await page.locator('#purchase-session-id').innerText();
  await page.locator('#new-purchase-session').click();await page.locator('#open-purchase-item').click();await page.locator('#purchase-item-qty').fill('2');await page.locator('#add-purchase-draft-line').click();
  const secondId=await page.locator('#purchase-session-id').innerText();expect(secondId).not.toBe(firstId);
  await page.reload({waitUntil:'load'});await page.locator('[data-view="purchases"]').click();await expect(page.locator('#purchase-session-id')).toHaveText(secondId);
  await page.locator('[data-open-purchase-draft="'+firstId+'"]').click();await expect(page.locator('#purchase-draft-lines')).toContainText('0,568');
  const before=await page.evaluate(()=>{const s=window.OUTPOST_DEMO_API.getState();return {stock:s.products[0].stock,count:s.purchases.length,supplierDebt:s.suppliers.find(p=>p.id===s.purchaseDraft.supplierId).debt,cost:s.purchaseDraft.lines[0].cost};});
  await page.locator('#post-purchase-session').click();await page.locator('#confirm-post-purchase-session').click();
  const after=await page.evaluate(id=>{const s=window.OUTPOST_DEMO_API.getState();return {stock:s.products[0].stock,posted:s.purchases.filter(p=>p.sessionId===id),drafts:s.purchaseDrafts.map(d=>d.id),count:s.purchases.length,supplierDebt:s.suppliers.find(p=>p.id===s.purchaseDraft.supplierId).debt};},firstId);
  expect(after.stock).toBeCloseTo(before.stock+.568,3);expect(after.posted).toHaveLength(1);expect(after.posted[0].qty).toBe(.568);expect(after.drafts).toContain(secondId);expect(after.count).toBe(before.count+1);expect(after.supplierDebt).toBeCloseTo(before.supplierDebt+Math.round(.568*before.cost*100)/100,2);
  await page.reload({waitUntil:'load'});expect(await page.evaluate(id=>window.OUTPOST_DEMO_API.getState().purchases.filter(p=>p.sessionId===id).length,firstId)).toBe(1);
});

test('inventory snapshot posting preserves fractional sales made while counting',async({page})=>{
  await page.goto(origin+'/demo',{waitUntil:'load'});const product=await page.evaluate(()=>window.OUTPOST_DEMO_API.getState().products.find(p=>p.stock>2&&p.barcode));
  await page.locator('[data-view="stockops"]').click();await page.locator('[data-stock-tab="inventory"]').click();await page.locator('#new-inventory').click();await page.locator('#create-inventory').click();
  const id=await page.evaluate(()=>window.OUTPOST_DEMO_API.getState().inventories[0].id);
  await page.locator('[data-inventory-actual="'+product.id+'"]').fill(String(product.stock-.125));await page.locator('[data-inventory-actual="'+product.id+'"]').dispatchEvent('change');await page.locator('#inventory-save-close').click();
  await page.locator('[data-view="sale"]').click();await page.locator('#product-search').fill(product.barcode);await page.locator('#product-search').press('Enter');await page.locator('[data-cart-quantity="'+product.id+'"]').fill('0.568');await page.locator('[data-cart-quantity="'+product.id+'"]').press('Tab');
  await page.locator('[data-pay="card"]').click();
  const sale=await page.evaluate(()=>window.OUTPOST_DEMO_API.getState().sales[0]);expect(sale.lines[0].qty).toBe(.568);
  await page.locator('[data-view="stockops"]').click();await page.locator('[data-stock-tab="inventory"]').click();await page.locator('[data-inventory-id="'+id+'"]').dblclick();
  page.once('dialog',d=>d.accept());await page.locator('#inventory-post').click();
  const result=await page.evaluate(({id,pid})=>{const s=window.OUTPOST_DEMO_API.getState();return {stock:s.products.find(p=>p.id===pid).stock,status:s.inventories.find(i=>i.id===id).status};},{id,pid:product.id});
  expect(result.status).toBe('posted');expect(result.stock).toBeCloseTo(product.stock-.568-.125,3);
});

test('write-off drafts preserve fractional quantities across closing and reload',async({page})=>{
  await page.goto(origin+'/demo',{waitUntil:'load'});await page.locator('[data-view="stockops"]').click();await page.locator('#new-writeoff').click();const pid=await page.locator('#writeoff-product').inputValue();
  const before=await page.evaluate(id=>{const s=window.OUTPOST_DEMO_API.getState();return {stock:s.products.find(p=>p.id===id).stock,count:s.writeoffs.length};},pid);
  await page.locator('#writeoff-qty').fill('.125');await page.locator('#writeoff-comment').fill('Збережена чернетка');await page.locator('#add-writeoff-line').click();await page.locator('#save-writeoff-draft').click();
  await page.reload({waitUntil:'load'});await page.locator('[data-view="stockops"]').click();await page.locator('#new-writeoff').click();await expect(page.locator('#writeoff-draft-lines')).toContainText('0,125');await expect(page.locator('#writeoff-comment')).toHaveValue('Збережена чернетка');
  await page.locator('#save-writeoff').click();const after=await page.evaluate(id=>{const s=window.OUTPOST_DEMO_API.getState();return {stock:s.products.find(p=>p.id===id).stock,count:s.writeoffs.length,draft:s.writeoffDraft};},pid);
  expect(after.stock).toBeCloseTo(before.stock-.125,3);expect(after.count).toBe(before.count+1);expect(after.draft).toBeNull();
});

test('partial fractional refunds never exceed the amount originally paid',async({page})=>{
  await page.goto(origin+'/demo',{waitUntil:'load'});await page.locator('[data-view="products"]').click();await page.locator('#new-product').click();
  await page.locator('#product-new-name').fill('Демо · перевірка часткових повернень');await page.locator('#product-new-barcode').fill('2999990000011');await page.locator('#product-new-cost').fill('.01');await page.locator('#product-new-price').fill('.03');await page.locator('#save-new-product').click();
  const pid=await page.evaluate(()=>window.OUTPOST_DEMO_API.getState().products.find(p=>p.barcode==='2999990000011').id);
  await page.locator('[data-view="purchases"]').click();await page.locator('#open-purchase-item').click();await page.locator('#purchase-item-barcode').fill('2999990000011');await page.locator('#purchase-item-barcode').press('Enter');await page.locator('#add-purchase-draft-line').click();await page.locator('#post-purchase-session').click();await page.locator('#confirm-post-purchase-session').click();
  await page.locator('[data-view="sale"]').click();await page.locator('#product-search').fill('2999990000011');await page.locator('#product-search').press('Enter');await page.locator('[data-pay="card"]').click();
  const id=await page.evaluate(()=>window.OUTPOST_DEMO_API.getState().sales[0].id);await page.locator('[data-view-link="history"]').first().click();
  for(const amount of ['0.02','0.01']){await page.locator('[data-return-sale="'+id+'"]').click();await page.locator('[data-return-qty="'+pid+'"]').fill('.5');await page.locator('#open-return-payment').click();await expect(page.locator('#return-payment-card')).toHaveValue(amount);await page.locator('#confirm-sale-return').click();}
  const result=await page.evaluate(({id,pid})=>{const s=window.OUTPOST_DEMO_API.getState();return {refunded:s.returns.filter(r=>r.saleId===id).reduce((sum,r)=>sum+r.total,0),stock:s.products.find(p=>p.id===pid).stock};},{id,pid});expect(result.refunded).toBeCloseTo(.03,2);expect(result.stock).toBe(1);await expect(page.locator('[data-return-sale="'+id+'"]')).toBeDisabled();
});

test('legacy demo upgrade keeps an exact recoverable copy of previous work',async({page})=>{
  await page.goto(origin+'/demo',{waitUntil:'load'});
  const original=await page.evaluate(()=>{const s=JSON.parse(JSON.stringify(window.OUTPOST_DEMO_API.getState()));s.datasetMeta={fraction:'5%',label:'Legacy sample'};s.sales=[{id:'KEEP-MY-TEST',at:new Date().toISOString(),payment:'cash',cash:10,card:0,total:10,itemCount:0,lines:[]}];const raw=JSON.stringify(s);localStorage.removeItem('outpost_online_demo_legacy_backup_v2');localStorage.setItem('outpost_online_demo_v2',raw);return raw;});
  await page.reload({waitUntil:'load'});expect(await page.evaluate(()=>window.OUTPOST_DEMO_API.getState().datasetMeta.seedRevision)).toBe(3);
  expect(await page.evaluate(()=>localStorage.getItem('outpost_online_demo_legacy_backup_v2'))).toBe(original);
  await page.locator('[data-view="settings"]').click();page.once('dialog',d=>d.accept());await page.locator('#restore-legacy-data').click();await page.waitForLoadState('load');
  await expect.poll(()=>page.evaluate(()=>window.OUTPOST_DEMO_API.getState().sales[0]?.id)).toBe('KEEP-MY-TEST');
});

test("homepage exposes the online demo while demo stays noindex", async ({ browser }) => {
  test.setTimeout(40_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/", { waitUntil: "load", timeout: 20_000 });
  const demoLinks = page.locator('a[href="/demo"]');
  expect(await demoLinks.count()).toBeGreaterThanOrEqual(3);
  const heroButtons = page.locator(".hero-buttons a");
  await expect(heroButtons).toHaveCount(2);
  await expect(heroButtons.nth(0)).toContainText("Завантажити демоверсію");
  await expect(heroButtons.nth(0)).toHaveAttribute("download", "");
  await expect(heroButtons.nth(1)).toHaveAttribute("href", "/demo");
  await expect(heroButtons.nth(1)).toContainText("Онлайн демо-версія");

  await heroButtons.nth(1).click();
  await expect(page).toHaveURL(origin + "/demo");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/i);
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", "https://outpost.com.ua/demo");

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("online demo shows the stability and reduced-functionality notice", async ({ browser }) => {
  test.setTimeout(30_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/demo", { waitUntil: "load", timeout: 20_000 });
  const notice = page.locator(".demo-stability-notice");
  await expect(notice).toBeVisible();
  await expect(notice).toContainText("повної Windows-версії");
  await expect(notice).toContainText("окремим приблизним preview");
  await expect(notice).toContainText("не відтворює всі можливості");

  const noticeBox = await notice.boundingBox();
  const webbarBox = await page.locator(".demo-webbar").boundingBox();
  const windowBox = await page.locator(".outpost-window").boundingBox();
  expect(noticeBox).not.toBeNull();
  expect(webbarBox).not.toBeNull();
  expect(windowBox).not.toBeNull();
  expect(noticeBox.y).toBeGreaterThanOrEqual(webbarBox.y + webbarBox.height - 1);
  expect(windowBox.y).toBeGreaterThanOrEqual(noticeBox.y + noticeBox.height - 1);

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("download release cards show both product marks", async ({ browser }) => {
  test.setTimeout(30_000);
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(origin + "/download", { waitUntil: "load", timeout: 20_000 });

  const outpostCard = page.locator('[data-download-product="outpost"]');
  const accountingCard = page.locator('[data-download-product="accounting"]');
  const outpostRow = outpostCard.locator(".release-title-row");
  const accountingRow = accountingCard.locator(".release-title-row");
  const outpostMark = outpostRow.locator("img.outpost-release-mark");
  const accountingMark = accountingRow.locator("img.accounting-release-mark");
  const outpostTitle = outpostRow.locator("h2");
  const accountingTitle = accountingRow.locator("h2");

  await expect(outpostRow).toBeVisible();
  await expect(accountingRow).toBeVisible();
  await expect(outpostMark).toBeVisible();
  await expect(outpostMark).toHaveAttribute("src", "/assets/outpost-logo.png");
  await expect(outpostMark).toHaveAttribute("width", "44");
  await expect(outpostMark).toHaveAttribute("height", "44");
  await expect(accountingMark).toBeVisible();

  const outpostBox = await outpostMark.boundingBox();
  const accountingBox = await accountingMark.boundingBox();
  const outpostTitleBox = await outpostTitle.boundingBox();
  const accountingTitleBox = await accountingTitle.boundingBox();
  expect(outpostBox).not.toBeNull();
  expect(accountingBox).not.toBeNull();
  expect(outpostTitleBox).not.toBeNull();
  expect(accountingTitleBox).not.toBeNull();
  expect(Math.round(outpostBox.width)).toBe(44);
  expect(Math.round(outpostBox.height)).toBe(44);
  expect(Math.round(accountingBox.width)).toBe(44);
  expect(Math.round(accountingBox.height)).toBe(44);
  expect(outpostBox.x + outpostBox.width).toBeLessThanOrEqual(outpostTitleBox.x);
  expect(accountingBox.x + accountingBox.width).toBeLessThanOrEqual(accountingTitleBox.x);
  expect(Math.abs((outpostBox.y + outpostBox.height / 2) - (outpostTitleBox.y + outpostTitleBox.height / 2))).toBeLessThan(3);
  expect(Math.abs((accountingBox.y + accountingBox.height / 2) - (accountingTitleBox.y + accountingTitleBox.height / 2))).toBeLessThan(3);

  await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", /Інсталятор\s+[0-9]+(?:,[0-9]+)?\s+МБ/);
  const jsonLd = await page.locator('script[type="application/ld+json"]').allTextContents();
  expect(jsonLd.join("\n")).toMatch(/"fileSize"\s*:\s*"[0-9]+(?:\.[0-9]+)? MB"/);

  expect(pageErrors, pageErrors.join("\n")).toEqual([]);
  await context.close();
});


test("universal download is one product button and preserves mobile layout", async ({ browser }) => {
  test.setTimeout(45_000);
  const setup = path.join(siteRoot, "setup", "OutPOSt-Setup.exe");
  test.skip(!fs.existsSync(setup), "Universal setup has not been introduced in this fixture");
  const expected = crypto.createHash("sha256").update(fs.readFileSync(setup)).digest("hex");
  for (const width of [390, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, acceptDownloads: true });
    const page = await context.newPage();
    await page.goto(origin + "/download", { waitUntil: "load" });
    const card = page.locator('[data-download-product="outpost"]');
    const binaries = card.locator('a[href$=".exe"]');
    await expect(binaries).toHaveCount(1);
    await expect(binaries).toHaveAttribute("href", "/setup/OutPOSt-Setup.exe");
    await expect(card.locator('a.btn')).toHaveCount(1);
    await expect(card.locator('a[href="/setup/OutPOSt-Setup.sha256.txt"]')).toBeVisible();
    await expect(page.locator('[data-download-product="accounting"] a[href$=".exe"]')).toHaveCount(1);
    const pending = page.waitForEvent("download");
    await binaries.click();
    const download = await pending;
    expect(download.suggestedFilename()).toBe("OutPOSt-Setup.exe");
    const saved = path.join(artifactRoot, "universal-" + width + ".exe");
    await download.saveAs(saved);
    expect(crypto.createHash("sha256").update(fs.readFileSync(saved)).digest("hex")).toBe(expected);
    await card.locator('[data-full-package-integrity] summary').click();
    const dimensions = await page.evaluate(() => ({ viewport: innerWidth, actual: document.documentElement.scrollWidth }));
    expect(dimensions.actual).toBeLessThanOrEqual(dimensions.viewport + 1);
    await page.screenshot({ path: path.join(artifactRoot, "universal-download-" + width + ".png"), fullPage: true });
    await context.close();
  }
});
