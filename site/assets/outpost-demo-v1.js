(() => {
  "use strict";

  const STORAGE_KEY = "outpost_online_demo_v2";
  const APPEARANCE_KEY = "outpost_online_demo_appearance_v1";
  const APPEARANCE_DEFAULTS = Object.freeze({ theme: "light", accent: "blue", fontSize: 13, bold: false });
  const APPEARANCE_OPTIONS = Object.freeze({
    themes: ["light", "dark", "contrast"],
    accents: ["blue", "green", "purple", "orange"],
    fonts: [11, 13, 14, 16, 18]
  });
  const DEMO_PROFILE = window.OUTPOST_DEMO_PROFILE || null;
  const DEMO_PRODUCTS = Array.isArray(window.OUTPOST_DEMO_PRODUCTS) ? window.OUTPOST_DEMO_PRODUCTS : [];

  const FALLBACK_SEED = {
    version: 2,
    datasetMeta: { label: "Резервний демо-набір", fraction: "fallback" },
    nextSale: 9001,
    nextPurchase: 501,
    products: [
      { id: "p1", code: "10001", name: "Кава мелена 250 г", barcode: "482000000001", price: 149, cost: 101, stock: 18, unit: "шт" },
      { id: "p2", code: "10002", name: "Молоко 2,5% 900 мл", barcode: "482000000002", price: 48, cost: 36, stock: 7, unit: "шт" },
      { id: "p3", code: "10003", name: "Хліб пшеничний", barcode: "482000000003", price: 32, cost: 24, stock: 4, unit: "шт" },
      { id: "p4", code: "10004", name: "Шоколад чорний 90 г", barcode: "482000000004", price: 72, cost: 51, stock: 2, unit: "шт" }
    ],
    customers: [
      { id: "c1", name: "Олена Коваленко", phone: "+380 67 000 10 20", debt: 340 },
      { id: "c2", name: "Андрій Мельник", phone: "+380 67 000 11 21", debt: 0 }
    ],
    suppliers: [
      { id: "s1", name: "ТОВ «Північ Трейд»" },
      { id: "s2", name: "ТОВ «Міський Опт»" }
    ],
    sales: [],
    purchases: [],
    cashMovements: []
  };

  function makeDemoPrng(seed = 20260912) {
    let value = seed >>> 0;
    return () => {
      value = (value * 1664525 + 1013904223) >>> 0;
      return value / 4294967296;
    };
  }

  function interpolateQuantile(values, unit) {
    if (!Array.isArray(values) || !values.length) return 50;
    if (values.length === 1) return Number(values[0]) || 50;
    const position = Math.max(0, Math.min(0.999999, unit)) * (values.length - 1);
    const lo = Math.floor(position);
    const hi = Math.min(values.length - 1, lo + 1);
    const mix = position - lo;
    return Number(values[lo]) + (Number(values[hi]) - Number(values[lo])) * mix;
  }

  function weightedValue(countMap, rand, fallback = 1) {
    const entries = Object.entries(countMap || {}).map(([key, count]) => [key, Number(count) || 0]).filter(([, count]) => count > 0);
    const total = entries.reduce((sum, [, count]) => sum + count, 0);
    if (!total) return fallback;
    let target = rand() * total;
    for (const [key, count] of entries) {
      target -= count;
      if (target <= 0) return key;
    }
    return entries[entries.length - 1][0];
  }

  function buildProfileSales(profile, customers) {
    const cfg = profile?.saleProfile;
    if (!cfg || !Number(cfg.count)) return [];

    const rand = makeDemoPrng(240912);
    const paymentCounts = { ...(cfg.paymentCounts || {}) };
    const paymentPool = [];
    ["cash", "card", "mixed", "debt"].forEach(type => {
      const count = Math.max(0, Math.floor(Number(paymentCounts[type]) || 0));
      for (let i = 0; i < count; i += 1) paymentPool.push(type);
    });
    while (paymentPool.length < cfg.count) paymentPool.push("cash");
    paymentPool.length = cfg.count;

    for (let i = paymentPool.length - 1; i > 0; i -= 1) {
      const j = Math.floor(rand() * (i + 1));
      [paymentPool[i], paymentPool[j]] = [paymentPool[j], paymentPool[i]];
    }

    const debtCustomers = (customers || []).filter(customer => Number(customer.debt) > 0);
    const now = new Date();
    now.setMinutes(0, 0, 0);
    const spanMs = 88 * 24 * 60 * 60 * 1000;
    const startMs = now.getTime() - spanMs;
    const sales = [];

    for (let i = 0; i < cfg.count; i += 1) {
      const payment = paymentPool[i] || "cash";
      const rawAmount = interpolateQuantile(cfg.amountQuantiles, rand());
      const transformed = Math.max(0.5, rawAmount * (0.95 + rand() * 0.10));
      const total = Math.round((transformed + Number.EPSILON) * 100) / 100;
      const itemCount = Math.max(1, Number(weightedValue(cfg.itemCountCounts, rand, 1)) || 1);
      const baseTime = startMs + spanMs * (i / Math.max(1, cfg.count - 1));
      const jitterMs = (rand() - 0.5) * 3 * 60 * 60 * 1000;
      const sale = {
        id: `D${String(i + 1).padStart(6, "0")}`,
        at: new Date(baseTime + jitterMs).toISOString(),
        payment,
        total,
        itemCount,
        lines: []
      };

      if (payment === "mixed") {
        const cash = Math.round(total * (0.25 + rand() * 0.5) * 100) / 100;
        sale.cash = cash;
        sale.card = Math.round((total - cash) * 100) / 100;
      } else if (payment === "cash") {
        sale.cash = total;
        sale.card = 0;
      } else if (payment === "card") {
        sale.cash = 0;
        sale.card = total;
      } else if (payment === "debt" && debtCustomers.length) {
        sale.customerId = debtCustomers[Math.floor(rand() * debtCustomers.length)].id;
      }
      sales.push(sale);
    }

    sales.sort((a, b) => String(b.at).localeCompare(String(a.at)));
    return sales;
  }

  function buildProfileCashMovements(profile) {
    const counts = profile?.cashMovementSourceCounts || {};
    const totalSource = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
    if (!totalSource) return [];
    const target = Math.max(1, Math.round(totalSource * 0.05));
    const rand = makeDemoPrng(119947);
    const result = [];
    const movementTypes = Object.keys(counts);
    const today = new Date();
    today.setMinutes(0, 0, 0);

    for (let i = 0; i < target; i += 1) {
      const type = weightedValue(counts, rand, movementTypes[0] || "Sale");
      result.push({
        id: `CM${String(i + 1).padStart(4, "0")}`,
        type,
        amount: Math.round((10 + rand() * 990) * 100) / 100,
        at: new Date(today.getTime() - (i % 45) * 24 * 60 * 60 * 1000 - rand() * 8 * 60 * 60 * 1000).toISOString()
      });
    }
    return result;
  }

  function buildDemoSeed() {
    if (!DEMO_PROFILE || DEMO_PRODUCTS.length < 300) return FALLBACK_SEED;
    const customers = JSON.parse(JSON.stringify(DEMO_PROFILE.customers || []));
    const suppliers = JSON.parse(JSON.stringify(DEMO_PROFILE.suppliers || []));
    return {
      version: 2,
      datasetMeta: {
        label: "Анонімізований зріз реальної бази OutPOSt",
        ...(DEMO_PROFILE.meta || {})
      },
      nextSale: 9001,
      nextPurchase: 501,
      products: JSON.parse(JSON.stringify(DEMO_PRODUCTS)),
      customers,
      suppliers,
      sales: buildProfileSales(DEMO_PROFILE, customers),
      purchases: JSON.parse(JSON.stringify(DEMO_PROFILE.purchases || [])),
      cashMovements: buildProfileCashMovements(DEMO_PROFILE)
    };
  }

  const SEED = buildDemoSeed();

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const cloneSeed = () => JSON.parse(JSON.stringify(SEED));

  let appearance = loadAppearance();
  let state = loadState();
  if (!state.purchaseDraft || !Array.isArray(state.purchaseDraft.lines)) {
    state.purchaseDraft = {
      id: `SES-${String(state.nextPurchase || 204).padStart(6, "0")}`,
      supplierId: state.suppliers?.[0]?.id || "",
      lines: []
    };
  }
  let cart = [];
  let selectedCartProductId = null;
  let activeView = "sale";
  let selectedCustomerId = null;
  let toastTimer = 0;
  let forceProductList = false;
  let lastAddedProductId = null;
  let f7SelectedProductId = null;
  let f7Target = "sale";
  let purchaseSelectedProductId = state.products?.[0]?.id || null;

  const moneyFmt = new Intl.NumberFormat("uk-UA", { style: "currency", currency: "UAH", minimumFractionDigits: 2 });
  const dateFmt = new Intl.DateTimeFormat("uk-UA", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return cloneSeed();
      const parsed = JSON.parse(raw);
      if (!parsed || parsed.version !== SEED.version || !Array.isArray(parsed.products)) return cloneSeed();
      return parsed;
    } catch {
      return cloneSeed();
    }
  }

  function saveState() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      showToast("Не вдалося зберегти стан демо у браузері.");
    }
  }

  function normalizeAppearance(value) {
    const source = value && typeof value === "object" ? value : {};
    const theme = APPEARANCE_OPTIONS.themes.includes(source.theme) ? source.theme : APPEARANCE_DEFAULTS.theme;
    const accent = APPEARANCE_OPTIONS.accents.includes(source.accent) ? source.accent : APPEARANCE_DEFAULTS.accent;
    const fontSize = APPEARANCE_OPTIONS.fonts.includes(Number(source.fontSize)) ? Number(source.fontSize) : APPEARANCE_DEFAULTS.fontSize;
    return { theme, accent, fontSize, bold: Boolean(source.bold) };
  }

  function loadAppearance() {
    try {
      const raw = localStorage.getItem(APPEARANCE_KEY);
      return normalizeAppearance(raw ? JSON.parse(raw) : APPEARANCE_DEFAULTS);
    } catch {
      return { ...APPEARANCE_DEFAULTS };
    }
  }

  function saveAppearance() {
    try {
      localStorage.setItem(APPEARANCE_KEY, JSON.stringify(appearance));
    } catch {
      showToast("Не вдалося зберегти налаштування інтерфейсу.");
    }
  }

  function applyAppearance(value = appearance) {
    appearance = normalizeAppearance(value);
    const root = document.documentElement;
    root.dataset.demoTheme = appearance.theme;
    root.dataset.demoAccent = appearance.accent;
    root.dataset.demoFontSize = String(appearance.fontSize);
    root.dataset.demoBold = String(appearance.bold);
    const metaTheme = document.querySelector('meta[name="theme-color"]');
    if (metaTheme) {
      metaTheme.setAttribute("content", appearance.theme === "contrast" ? "#000000" : appearance.theme === "dark" ? "#0f171e" : "#17232d");
    }
    return { ...appearance };
  }

  function appearanceLabels() {
    return {
      theme: { light: "світла", dark: "темна", contrast: "контрастна" },
      accent: { blue: "синій", green: "зелений", purple: "фіолетовий", orange: "помаранчевий" }
    };
  }

  function syncAppearanceControls() {
    const theme = $("#appearance-theme");
    const accent = $("#appearance-accent");
    const font = $("#appearance-font");
    const bold = $("#appearance-bold");
    if (theme) theme.value = appearance.theme;
    if (accent) accent.value = appearance.accent;
    if (font) font.value = String(appearance.fontSize);
    if (bold) bold.checked = appearance.bold;
    const summary = $("#appearance-summary");
    if (summary) {
      const labels = appearanceLabels();
      summary.textContent = `Застосовано: ${labels.theme[appearance.theme]} тема, ${labels.accent[appearance.accent]} акцент, шрифт ${appearance.fontSize}, ${appearance.bold ? "жирний" : "звичайний"} текст.`;
    }
  }

  function applyAppearanceFromControls() {
    appearance = normalizeAppearance({
      theme: $("#appearance-theme")?.value,
      accent: $("#appearance-accent")?.value,
      fontSize: Number($("#appearance-font")?.value),
      bold: Boolean($("#appearance-bold")?.checked)
    });
    saveAppearance();
    applyAppearance(appearance);
    syncAppearanceControls();
    showToast("Налаштування інтерфейсу застосовано локально у цьому браузері.");
  }

  function money(value) {
    return moneyFmt.format(Number(value) || 0);
  }

  function formatDate(value) {
    return dateFmt.format(new Date(value));
  }

  function round2(value) {
    return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
  }

  function productById(id) {
    return state.products.find(p => p.id === id);
  }

  function productCode(product) {
    if (product?.code) return String(product.code);
    const index = state.products.findIndex(p => p.id === product.id);
    return String(10001 + Math.max(index, 0));
  }

  function customerById(id) {
    return state.customers.find(c => c.id === id);
  }

  function supplierById(id) {
    return state.suppliers.find(s => s.id === id);
  }

  function cartDiscountPercent(line) {
    const value = Number(line?.discountPercent || 0);
    return Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  }

  function cartUnitPrice(line, product = productById(line?.productId)) {
    if (!product) return 0;
    return round2(Number(product.price || 0) * (1 - cartDiscountPercent(line) / 100));
  }

  function cartTotal() {
    return round2(cart.reduce((sum, line) => {
      const product = productById(line.productId);
      return sum + (product ? cartUnitPrice(line, product) * Number(line.qty || 0) : 0);
    }, 0));
  }

  function cartCount() {
    return cart.reduce((sum, line) => sum + line.qty, 0);
  }

  function stockClass(stock) {
    if (stock <= 0) return "critical";
    if (stock < 5) return "low";
    return "";
  }

  function stockLabel(stock) {
    if (stock <= 0) return "0 / немає";
    if (stock < 2) return "критично мало";
    if (stock < 5) return "скоро закінчиться";
    return "в наявності";
  }

  function showToast(message) {
    const toast = $("#toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2600);
  }

  function switchView(view) {
    activeView = view;
    $$(".demo-nav").forEach(btn => {
      const current = btn.dataset.view === view;
      btn.classList.toggle("is-active", current);
      if (current) btn.setAttribute("aria-current", "page");
      else btn.removeAttribute("aria-current");
    });
    $$(".demo-view").forEach(panel => panel.classList.toggle("is-active", panel.dataset.viewPanel === view));
    renderView(view);
    if (view === "sale") window.setTimeout(() => $("#product-search")?.focus(), 20);
  }

  function renderView(view) {
    if (view === "home") {
      renderHome();
    } else if (view === "sale") {
      renderProducts();
      renderCart();
    } else if (view === "products") {
      renderProductsTable();
      window.OUTPOST_DEMO_PRODUCTS_MODULE?.renderView?.("products");
    } else if (view === "customers") {
      renderCustomers();
    } else if (view === "purchases") {
      renderPurchaseForm();
      renderPurchaseHistory();
    } else if (view === "history") {
      renderSalesHistory();
      window.OUTPOST_DEMO_RETURNS?.renderView?.("history");
    } else if (view === "reports") {
      renderReports();
    } else if (view === "stockops" || view === "finance") {
      window.OUTPOST_DEMO_MODULES?.renderView?.(view);
    }
  }

  function renderAll() {
    renderHome();
    renderProducts();
    renderCart();
    renderProductsTable();
    renderCustomers();
    renderPurchaseForm();
    renderPurchaseHistory();
    renderSalesHistory();
    renderReports();
    window.OUTPOST_DEMO_MODULES?.renderAll?.();
    window.OUTPOST_DEMO_RETURNS?.renderAll?.();
    window.OUTPOST_DEMO_PRODUCTS_MODULE?.renderAll?.();
  }

  function renderProducts() {
    const grid = $("#product-grid");
    if (!grid) return;
    grid.innerHTML = "";
    grid.classList.remove("is-open");
  }

  function f7FilteredProducts() {
    const code = ($("#f7-code")?.value || "").trim().toLowerCase();
    const name = ($("#f7-name")?.value || "").trim().toLowerCase();
    const barcode = ($("#f7-barcode")?.value || "").trim().toLowerCase();
    const stockRaw = ($("#f7-stock")?.value || "").trim();
    const minStock = stockRaw === "" ? null : Number(stockRaw);

    return state.products.filter(product => {
      if (code && !productCode(product).toLowerCase().includes(code)) return false;
      if (name && !product.name.toLowerCase().includes(name)) return false;
      if (barcode && !product.barcode.toLowerCase().includes(barcode)) return false;
      if (minStock !== null && Number.isFinite(minStock) && product.stock < minStock) return false;
      return true;
    });
  }

  function renderF7Results() {
    const tbody = $("#f7-results");
    if (!tbody) return;
    const products = f7FilteredProducts();

    if (!products.some(product => product.id === f7SelectedProductId)) {
      f7SelectedProductId = products[0]?.id || null;
    }

    tbody.innerHTML = products.length ? products.map(product => `
      <tr class="search-result-row ${product.id === f7SelectedProductId ? "is-selected" : ""}" data-f7-product="${product.id}">
        <td>${productCode(product)}</td>
        <td>${product.barcode}</td>
        <td><strong>${product.name}</strong></td>
        <td>${money(product.price)}</td>
        <td>${product.stock} ${product.unit}</td>
      </tr>
    `).join("") : '<tr><td colspan="5" class="no-data">Товарів не знайдено.</td></tr>';

    $$("[data-f7-product]", tbody).forEach(row => {
      row.addEventListener("click", () => {
        f7SelectedProductId = row.dataset.f7Product;
        renderF7Results();
      });
      row.addEventListener("dblclick", () => {
        f7SelectedProductId = row.dataset.f7Product;
        addF7SelectedProduct();
      });
    });
  }

  function moveF7Selection(delta) {
    const products = f7FilteredProducts();
    if (!products.length) return;

    const currentIndex = products.findIndex(product => product.id === f7SelectedProductId);
    const startIndex = currentIndex >= 0 ? currentIndex : 0;
    const nextIndex = Math.max(0, Math.min(products.length - 1, startIndex + delta));
    f7SelectedProductId = products[nextIndex].id;
    renderF7Results();
    $("[data-f7-product].is-selected")?.scrollIntoView({ block: "nearest" });
  }

  function openProductSearch(initialValue = "", target = "sale") {
    const dialog = $("#product-search-dialog");
    if (!dialog) return;

    f7Target = target;
    if ($("#f7-add-selected")) $("#f7-add-selected").textContent = target === "purchase" ? "Обрати товар" : "Додати в чек";
    $("#f7-code").value = "";
    $("#f7-name").value = "";
    $("#f7-barcode").value = "";
    $("#f7-stock").value = "";

    const value = String(initialValue || "").trim();
    if (/^\d+$/.test(value)) {
      if (value.length >= 8) $("#f7-barcode").value = value;
      else $("#f7-code").value = value;
    } else if (value) {
      $("#f7-name").value = value;
    }

    f7SelectedProductId = null;
    renderF7Results();
    if (!dialog.open) dialog.showModal();
    window.setTimeout(() => {
      const target = value
        ? (/^\d+$/.test(value) ? (value.length >= 8 ? $("#f7-barcode") : $("#f7-code")) : $("#f7-name"))
        : $("#f7-name");
      target?.focus();
      target?.select();
    }, 20);
  }

  function addF7SelectedProduct() {
    if (!f7SelectedProductId) {
      showToast("Оберіть товар у списку.");
      return;
    }
    if (f7Target === "purchase") {
      selectPurchaseProduct(f7SelectedProductId, true);
      $("#product-search-dialog")?.close();
      return;
    }
    $("#product-search-dialog")?.close();
    addProduct(f7SelectedProductId);
  }

  function restoreSaleSearchFocus() {
    if (activeView !== "sale") return;
    window.setTimeout(() => {
      if (!$(".demo-dialog[open]")) $("#product-search")?.focus();
    }, 20);
  }

  function resumeAfterProductSearch() {
    if (f7Target === "purchase" && activeView === "purchases") {
      window.setTimeout(() => {
        if ($(".demo-dialog[open]")) return;
        const dialog = $("#purchase-item-dialog");
        if (dialog && !dialog.open) dialog.showModal();
        $("#purchase-item-barcode")?.focus();
      }, 20);
      return;
    }
    restoreSaleSearchFocus();
  }

  function selectedCartLine() {
    return cart.find(line => line.productId === selectedCartProductId) || null;
  }

  function selectCartProduct(productId) {
    selectedCartProductId = cart.some(line => line.productId === productId) ? productId : null;
    renderCart();
  }

  function updateCartToolbar() {
    const hasSelected = Boolean(selectedCartLine());
    ["#cart-dec-selected", "#cart-inc-selected", "#cart-discount-selected", "#cart-delete-selected"].forEach(selector => {
      if ($(selector)) $(selector).disabled = !hasSelected;
    });
  }

  function removeCartProduct(productId) {
    cart = cart.filter(item => item.productId !== productId);
    if (selectedCartProductId === productId) {
      selectedCartProductId = cart[0]?.productId || null;
    }
    renderCart();
  }

  function addProduct(productId) {
    const existing = cart.find(line => line.productId === productId);
    if (existing) existing.qty += 1;
    else cart.push({ productId, qty: 1, discountPercent: 0 });

    selectedCartProductId = productId;
    lastAddedProductId = productId;
    forceProductList = false;
    const input = $("#product-search");
    if (input) input.value = "";
    renderProducts();
    renderCart();
    input?.focus();
  }

  function setCartQty(productId, delta) {
    const line = cart.find(item => item.productId === productId);
    if (!line) return;
    line.qty += delta;
    if (line.qty <= 0) {
      removeCartProduct(productId);
      return;
    }
    selectedCartProductId = productId;
    renderCart();
  }

  function maxDiscountForProduct(product) {
    const retail = Number(product?.price || 0);
    const minimum = Number(product?.minimumPrice || 0);
    if (retail <= 0) return 0;
    if (minimum <= 0) return 100;
    if (minimum >= retail) return 0;
    return Math.round(((1 - minimum / retail) * 100 + Number.EPSILON) * 10000) / 10000;
  }

  function openDiscountDialog() {
    const line = selectedCartLine();
    const product = line ? productById(line.productId) : null;
    if (!line || !product) {
      showToast("Оберіть позицію чека.");
      return;
    }

    if ($("#discount-product-name")) $("#discount-product-name").textContent = product.name;
    const maxDiscount = maxDiscountForProduct(product);
    if ($("#discount-price-info")) $("#discount-price-info").textContent = "Роздрібна ціна: " + money(product.price);
    if ($("#discount-limit")) {
      $("#discount-limit").textContent = Number(product.minimumPrice || 0) > 0
        ? "Мінімальна ціна: " + money(product.minimumPrice) + " · максимальна знижка: " + maxDiscount.toLocaleString("uk-UA", { maximumFractionDigits: 2 }) + "%"
        : "Мінімальна ціна для товару не задана · максимальна знижка: 100%";
    }
    if ($("#discount-error")) $("#discount-error").textContent = "";
    if ($("#discount-percent")) $("#discount-percent").value = cartDiscountPercent(line).toFixed(2).replace(/\.00$/, "");

    const dialog = $("#discount-dialog");
    if (dialog && !dialog.open) dialog.showModal();
    window.setTimeout(() => {
      $("#discount-percent")?.focus();
      $("#discount-percent")?.select();
    }, 20);
  }

  function applyCartDiscount() {
    const line = selectedCartLine();
    const product = line ? productById(line.productId) : null;
    if (!line || !product) {
      $("#discount-dialog")?.close();
      return;
    }

    const value = Number($("#discount-percent")?.value);
    if (!Number.isFinite(value) || value < 0 || value > 100) {
      if ($("#discount-error")) $("#discount-error").textContent = "Введіть знижку від 0 до 100%.";
      $("#discount-percent")?.focus();
      $("#discount-percent")?.select();
      return;
    }
    const maxDiscount = maxDiscountForProduct(product);
    if (value > maxDiscount + 0.0001) {
      if ($("#discount-error")) $("#discount-error").textContent = "Ця знижка опустить ціну нижче мінімально дозволеної.";
      $("#discount-percent")?.focus();
      $("#discount-percent")?.select();
      return;
    }

    line.discountPercent = Math.round((value + Number.EPSILON) * 100) / 100;
    $("#discount-dialog")?.close();
    renderCart();
    showToast("Знижку " + line.discountPercent.toLocaleString("uk-UA") + "% застосовано до " + product.name + ".");
  }

  function renderCart() {
    const lines = $("#cart-lines");
    const empty = $("#cart-empty");
    const count = cartCount();
    const total = cartTotal();

    if ($("#cart-count")) $("#cart-count").textContent = `${count} поз.`;
    if ($("#cart-total")) $("#cart-total").textContent = money(total).replace("₴", "грн");

    const lastProduct = productById(lastAddedProductId);
    if ($("#cart-last-item")) $("#cart-last-item").textContent = `Додано: ${lastProduct ? lastProduct.name : "—"}`;

    if (!cart.length) {
      selectedCartProductId = null;
      lines.innerHTML = "";
      empty.hidden = false;
      updateCartToolbar();
      return;
    }

    if (!cart.some(line => line.productId === selectedCartProductId)) {
      selectedCartProductId = cart[0].productId;
    }

    empty.hidden = true;
    lines.innerHTML = cart.map(line => {
      const product = productById(line.productId);
      if (!product) return "";
      const discount = cartDiscountPercent(line);
      const discountedPrice = cartUnitPrice(line, product);
      const lineTotal = round2(discountedPrice * line.qty);
      return `
        <tr class="${line.productId === selectedCartProductId ? "is-selected" : ""}" data-cart-row="${product.id}" tabindex="0">
          <td>${product.barcode}</td>
          <td>${productCode(product)}</td>
          <td>${product.name}</td>
          <td>
            <button class="cart-line-remove" type="button" data-cart-dec="${product.id}" aria-label="Зменшити кількість">−</button>
            ${line.qty}
            <button class="cart-line-remove" type="button" data-cart-inc="${product.id}" aria-label="Збільшити кількість">+</button>
          </td>
          <td>${product.unit}</td>
          <td>${Number(product.price).toFixed(2)}</td>
          <td>${discount.toLocaleString("uk-UA", { maximumFractionDigits: 2 })}</td>
          <td>${discountedPrice.toFixed(2)}</td>
          <td>${lineTotal.toFixed(2)}</td>
          <td><button class="cart-line-remove" type="button" data-cart-remove="${product.id}" aria-label="Видалити">×</button></td>
        </tr>
      `;
    }).join("");

    $$("[data-cart-row]", lines).forEach(row => {
      row.addEventListener("click", () => {
        selectedCartProductId = row.dataset.cartRow;
        renderCart();
      });
      row.addEventListener("focus", () => {
        selectedCartProductId = row.dataset.cartRow;
        updateCartToolbar();
      });
    });
    $$("[data-cart-dec]", lines).forEach(btn => btn.addEventListener("click", event => {
      event.stopPropagation();
      selectedCartProductId = btn.dataset.cartDec;
      setCartQty(btn.dataset.cartDec, -1);
    }));
    $$("[data-cart-inc]", lines).forEach(btn => btn.addEventListener("click", event => {
      event.stopPropagation();
      selectedCartProductId = btn.dataset.cartInc;
      setCartQty(btn.dataset.cartInc, 1);
    }));
    $$("[data-cart-remove]", lines).forEach(btn => btn.addEventListener("click", event => {
      event.stopPropagation();
      removeCartProduct(btn.dataset.cartRemove);
    }));
    updateCartToolbar();
  }

  function updateCashPaymentChange() {
    const total = cartTotal();
    const received = Number($("#cash-payment-received")?.value);
    const validReceived = Number.isFinite(received) ? received : 0;
    if ($("#cash-payment-change")) {
      $("#cash-payment-change").textContent = money(Math.max(0, round2(validReceived - total)));
    }
    if ($("#cash-payment-error")) $("#cash-payment-error").textContent = "";
  }

  function openCashPayment() {
    const total = cartTotal();
    if ($("#cash-payment-total")) $("#cash-payment-total").textContent = money(total);
    if ($("#cash-payment-received")) $("#cash-payment-received").value = total.toFixed(2);
    updateCashPaymentChange();

    const dialog = $("#cash-payment-dialog");
    if (dialog && !dialog.open) dialog.showModal();

    const received = $("#cash-payment-received");
    received?.focus();
    received?.select();
  }

  function confirmCashPayment() {
    const total = cartTotal();
    const received = Number($("#cash-payment-received")?.value);

    if (!Number.isFinite(received) || received < total) {
      if ($("#cash-payment-error")) {
        $("#cash-payment-error").textContent = "Отримана сума не може бути меншою за суму чека.";
      }
      const input = $("#cash-payment-received");
      input?.focus();
      input?.select();
      return;
    }

    $("#cash-payment-dialog")?.close();
    completeSale("cash", { cash: total, card: 0 });
    $("#product-search")?.focus();
  }

  function openPayment(type) {
    if (!cart.length) {
      showToast("Спочатку додайте товар у чек.");
      return;
    }

    const total = cartTotal();
    if (type === "cash") {
      openCashPayment();
      return;
    }

    if (type === "card") {
      completeSale("card", { cash: 0, card: total });
      return;
    }

    if (type === "mixed") {
      $("#mixed-total").textContent = money(total);
      const cash = round2(total / 2);
      $("#mixed-cash").value = cash.toFixed(2);
      updateMixedRemainder();
      const dialog = $("#mixed-dialog");
      if (dialog && !dialog.open) dialog.showModal();
      window.setTimeout(() => {
        $("#mixed-cash")?.focus();
        $("#mixed-cash")?.select();
      }, 20);
      return;
    }

    if (type === "debt") {
      $("#debt-total").textContent = money(total);
      $("#debt-customer").innerHTML = state.customers.map(c => `<option value="${c.id}">${c.name} · борг ${money(c.debt)}</option>`).join("");
      const dialog = $("#debt-dialog");
      if (dialog && !dialog.open) dialog.showModal();
      window.setTimeout(() => $("#debt-customer")?.focus(), 20);
    }
  }

  function updateMixedRemainder() {
    const total = cartTotal();
    const cash = Math.max(0, Number($("#mixed-cash").value) || 0);
    $("#mixed-card").textContent = money(Math.max(0, round2(total - cash)));
  }

  function confirmMixedPayment() {
    const total = cartTotal();
    const cash = round2(Number($("#mixed-cash")?.value) || 0);
    if (cash < 0 || cash > total) {
      showToast("Сума готівки має бути від 0 до суми чека.");
      $("#mixed-cash")?.focus();
      $("#mixed-cash")?.select();
      return;
    }
    const card = round2(total - cash);
    $("#mixed-dialog")?.close();
    completeSale("mixed", { cash, card });
  }

  function confirmDebtSale() {
    const customerId = $("#debt-customer")?.value;
    if (!customerById(customerId)) {
      showToast("Оберіть клієнта.");
      $("#debt-customer")?.focus();
      return;
    }
    $("#debt-dialog")?.close();
    selectedCustomerId = customerId;
    const customer = customerById(customerId);
    if ($("#selected-client-label")) $("#selected-client-label").textContent = customer ? customer.name : "не вибрано";
    completeSale("debt", { cash: 0, card: 0 }, customerId);
  }

  function completeSale(payment, split = {}, customerId = null) {
    if (!cart.length) return;
    const total = cartTotal();
    const lines = cart.map(line => {
      const product = productById(line.productId);
      return {
        productId: line.productId,
        name: product?.name || "Товар",
        qty: line.qty,
        price: cartUnitPrice(line, product),
        retailPrice: product?.price || 0,
        discountPercent: cartDiscountPercent(line)
      };
    });

    lines.forEach(line => {
      const product = productById(line.productId);
      if (product) product.stock -= line.qty;
    });

    if (payment === "debt" && customerId) {
      const customer = customerById(customerId);
      if (customer) customer.debt = round2(customer.debt + total);
    }

    const sale = {
      id: `S${state.nextSale++}`,
      at: new Date().toISOString(),
      payment,
      total,
      itemCount: cartCount(),
      lines,
      customerId: customerId || undefined,
      cash: round2(split.cash || 0),
      card: round2(split.card || 0)
    };

    state.sales.unshift(sale);
    cart = [];
    selectedCartProductId = null;
    saveState();
    renderAll();

    const labels = { cash: "готівкою", card: "карткою", mixed: "змішаною оплатою", debt: "у борг" };
    showToast(`Продаж ${sale.id} проведено ${labels[payment]}. Сума: ${money(total)}`);
    if (activeView === "sale") window.setTimeout(() => $("#product-search")?.focus(), 20);
  }

  function renderProductsTable() {
    $("#products-table").innerHTML = state.products.map(product => {
      const cls = stockClass(product.stock);
      return `
        <tr>
          <td>${productCode(product)}</td>
          <td>${product.barcode}</td>
          <td><strong>${product.name}</strong></td>
          <td>${money(product.price)}</td>
          <td>${money(product.cost)}</td>
          <td><span class="stock-value ${cls}">${product.stock} ${product.unit}</span></td>
        </tr>
      `;
    }).join("");
  }


  function customerDebtLedger(customerId) {
    const cutoff = Date.now() - 183 * 24 * 60 * 60 * 1000;
    const rows = [];

    state.sales.forEach(sale => {
      if (sale.payment !== "debt" || String(sale.customerId || "") !== String(customerId)) return;
      const at = new Date(sale.at).getTime();
      if (!Number.isFinite(at) || at < cutoff) return;
      rows.push({ at: sale.at, type: "Продаж у борг", reference: sale.id, amount: round2(Number(sale.total || 0)) });
    });

    state.cashMovements.forEach(movement => {
      if (String(movement.type || "").toLowerCase() !== "debtrepayment") return;
      if (String(movement.customerId || "") !== String(customerId)) return;
      const at = new Date(movement.at).getTime();
      if (!Number.isFinite(at) || at < cutoff) return;
      rows.push({
        at: movement.at,
        type: "Повернення боргу",
        reference: movement.id || "—",
        amount: -round2(Number(movement.amount || 0))
      });
    });

    (state.returns || []).forEach(record => {
      if (String(record.customerId || "") !== String(customerId)) return;
      const debtAmount = round2((record.payments || [])
        .filter(payment => payment.type === "debt")
        .reduce((sum, payment) => sum + Number(payment.amount || 0), 0));
      if (debtAmount <= 0) return;
      const at = new Date(record.at).getTime();
      if (!Number.isFinite(at) || at < cutoff) return;
      rows.push({
        at: record.at,
        type: "Повернення · зменшення боргу",
        reference: record.id || "—",
        amount: -debtAmount
      });
    });

    (state.debtWriteOffs || []).forEach(record => {
      if (String(record.customerId || "") !== String(customerId)) return;
      const at = new Date(record.at).getTime();
      if (!Number.isFinite(at) || at < cutoff) return;
      rows.push({
        at: record.at,
        type: "Списання боргу",
        reference: record.id || "—",
        amount: -round2(Number(record.amount || 0))
      });
    });

    return rows.sort((a, b) => String(b.at).localeCompare(String(a.at)));
  }

  function renderCustomerDebtLedgerHtml(customerId) {
    const ledger = customerDebtLedger(customerId);
    const body = ledger.length
      ? ledger.map(row => {
          const positive = Number(row.amount) > 0;
          const amountText = (positive ? "+" : "−") + money(Math.abs(Number(row.amount)));
          return "<tr>" +
            "<td>" + formatDate(row.at) + "</td>" +
            "<td>" + row.type + "</td>" +
            "<td>" + row.reference + "</td>" +
            "<td class=\"" + (positive ? "debt-plus" : "debt-minus") + "\"><strong>" + amountText + "</strong></td>" +
            "</tr>";
        }).join("")
      : '<tr><td colspan="4" class="no-data">За останні 6 місяців операцій у демо-журналі немає.</td></tr>';

    return '<div class="debt-ledger">' +
      '<div class="pane-head debt-ledger-head"><div><h3>Операції за останні 6 місяців</h3>' +
      '<small>Поточний борг показано окремо як контрольний баланс клієнта.</small></div>' +
      '<span>' + ledger.length + ' операцій</span></div>' +
      '<div class="desktop-table-wrap debt-ledger-wrap"><table class="desktop-table">' +
      '<thead><tr><th>Дата</th><th>Операція</th><th>Документ</th><th>Сума</th></tr></thead>' +
      '<tbody id="debt-ledger-table">' + body + '</tbody></table></div></div>';
  }

  function renderCustomers() {
    const list = $("#customer-list");
    list.innerHTML = state.customers.map(customer => `
      <button class="customer-row ${selectedCustomerId === customer.id ? "is-active" : ""}" type="button" data-customer-id="${customer.id}">
        <span><strong>${customer.name}</strong><br><small class="muted">${customer.phone}</small></span>
        <span class="customer-debt ${customer.debt <= 0 ? "zero" : ""}">${money(customer.debt)}</span>
      </button>
    `).join("");

    $$("[data-customer-id]", list).forEach(btn => btn.addEventListener("click", () => {
      selectedCustomerId = btn.dataset.customerId;
      renderCustomers();
    }));

    const detail = $("#customer-detail");
    const customer = customerById(selectedCustomerId);
    if (!customer) {
      detail.innerHTML = '<div class="empty-detail">Оберіть клієнта, щоб переглянути борг.</div>';
      return;
    }

    detail.innerHTML = `
      <div class="detail-grid">
        <div>
          <p class="eyebrow">Картка клієнта</p>
          <h2>${customer.name}</h2>
          <p class="muted">${customer.phone}</p>
        </div>
        <div>
          <span class="muted">Поточний борг</span>
          <div class="detail-debt">${money(customer.debt)}</div>
        </div>
        <label class="field-label" for="repay-amount">Повернення боргу</label>
        <div class="repay-row debt-action-row">
          <input id="repay-amount" type="number" min="0.01" step="0.01" value="${customer.debt > 0 ? customer.debt.toFixed(2) : "0.00"}"/>
          <button class="primary-btn" type="button" id="repay-debt" ${customer.debt <= 0 ? "disabled" : ""}>Прийняти</button>
          <button class="win-btn debt-writeoff-btn" type="button" id="writeoff-debt" ${customer.debt <= 0 ? "disabled" : ""}>Списати борг</button>
        </div>
      </div>
    `;
    detail.insertAdjacentHTML("beforeend", renderCustomerDebtLedgerHtml(customer.id));

    $("#repay-debt")?.addEventListener("click", () => {
      const amount = round2(Number($("#repay-amount").value) || 0);
      if (amount <= 0) {
        showToast("Вкажіть суму повернення.");
        return;
      }
      const shift = window.OUTPOST_DEMO_MODULES?.getCashSummary?.();
      if (shift && !shift.isOpen) {
        showToast("Для приймання готівки спочатку відкрийте касову зміну.");
        return;
      }
      const paid = Math.min(amount, customer.debt);
      customer.debt = round2(customer.debt - paid);
      window.OUTPOST_DEMO_MODULES?.recordDebtRepayment?.(customer, paid);
      saveState();
      renderAll();
      showToast(`Прийнято повернення боргу: ${money(paid)}`);
    });

    $("#writeoff-debt")?.addEventListener("click", () => {
      if (customer.debt <= 0) return;
      const amount = round2(customer.debt);
      if (!window.confirm(`Списати борг ${customer.name} на ${money(amount)}? Це не рух готівки.`)) return;
      if (!Array.isArray(state.debtWriteOffs)) state.debtWriteOffs = [];
      const id = `DW-${String(state.debtWriteOffs.length + 1).padStart(6, "0")}`;
      state.debtWriteOffs.unshift({
        id,
        customerId: customer.id,
        customerName: customer.name,
        amount,
        at: new Date().toISOString(),
        user: "Адмін"
      });
      customer.debt = 0;
      saveState();
      renderAll();
      showToast(`Борг ${money(amount)} списано. Каса не змінювалася.`);
    });
  }

  function ensurePurchaseDraft() {
    if (!state.purchaseDraft || !Array.isArray(state.purchaseDraft.lines)) {
      state.purchaseDraft = {
        id: `SES-${String(state.nextPurchase || 204).padStart(6, "0")}`,
        supplierId: state.suppliers?.[0]?.id || "",
        lines: []
      };
    }
    return state.purchaseDraft;
  }

  function purchaseDraftTotal() {
    const draft = ensurePurchaseDraft();
    return round2(draft.lines.reduce((sum, line) => sum + Number(line.qty || 0) * Number(line.cost || 0), 0));
  }

  function renderPurchaseForm() {
    const draft = ensurePurchaseDraft();
    const supplier = $("#purchase-supplier");
    const tbody = $("#purchase-draft-lines");
    const empty = $("#purchase-draft-empty");
    if (!supplier || !tbody || !empty) return;

    supplier.innerHTML = state.suppliers.map(s => `<option value="${s.id}">${s.name}</option>`).join("");
    if (!state.suppliers.some(s => s.id === draft.supplierId)) draft.supplierId = state.suppliers[0]?.id || "";
    supplier.value = draft.supplierId;

    if ($("#purchase-session-id")) $("#purchase-session-id").textContent = draft.id;
    if ($("#purchase-draft-count")) $("#purchase-draft-count").textContent = `${draft.lines.length} поз.`;
    if ($("#purchase-draft-total")) $("#purchase-draft-total").textContent = money(purchaseDraftTotal()).replace("₴", "грн");

    if (!draft.lines.length) {
      tbody.innerHTML = "";
      empty.hidden = false;
    } else {
      empty.hidden = true;
      tbody.innerHTML = draft.lines.map((line, index) => {
        const product = productById(line.productId);
        if (!product) return "";
        return `
          <tr>
            <td>${productCode(product)}</td>
            <td><strong>${product.name}</strong></td>
            <td>${Number(line.qty).toLocaleString("uk-UA")}</td>
            <td>${product.unit}</td>
            <td>${money(line.cost)}</td>
            <td>${money(line.newPrice)}</td>
            <td>${money(round2(line.qty * line.cost))}</td>
            <td><button class="cart-line-remove" type="button" data-remove-purchase-line="${index}" aria-label="Видалити позицію">×</button></td>
          </tr>
        `;
      }).join("");

      $$("[data-remove-purchase-line]", tbody).forEach(button => {
        button.addEventListener("click", () => {
          const index = Number(button.dataset.removePurchaseLine);
          draft.lines.splice(index, 1);
          saveState();
          renderPurchaseForm();
        });
      });
    }
  }

  function selectPurchaseProduct(productId, resetValues = false) {
    const product = productById(productId);
    if (!product) return;
    purchaseSelectedProductId = product.id;

    if ($("#purchase-item-barcode")) $("#purchase-item-barcode").value = product.barcode;
    if ($("#purchase-item-code")) $("#purchase-item-code").value = productCode(product);
    if ($("#purchase-item-name")) $("#purchase-item-name").value = product.name;
    if ($("#purchase-item-unit")) $("#purchase-item-unit").value = product.unit;
    if ($("#purchase-item-current-price")) $("#purchase-item-current-price").value = product.price.toFixed(2);
    if ($("#purchase-item-note")) $("#purchase-item-note").textContent = `Існуючий товар · код ${productCode(product)} · залишок ${product.stock} ${product.unit}`;

    if (resetValues) {
      if ($("#purchase-item-qty")) $("#purchase-item-qty").value = "1";
      if ($("#purchase-item-cost")) $("#purchase-item-cost").value = product.cost.toFixed(2);
      if ($("#purchase-item-new-price")) $("#purchase-item-new-price").value = product.price.toFixed(2);
      const markup = product.cost > 0 ? ((product.price / product.cost) - 1) * 100 : 30;
      if ($("#purchase-item-markup")) $("#purchase-item-markup").value = round2(markup).toFixed(1);
    }
    updatePurchaseItemSummary();
  }

  function updatePurchaseItemSummary(source = "") {
    const qty = Math.max(0, Number($("#purchase-item-qty")?.value) || 0);
    const cost = Math.max(0, Number($("#purchase-item-cost")?.value) || 0);
    let newPrice = Math.max(0, Number($("#purchase-item-new-price")?.value) || 0);
    let markup = Number($("#purchase-item-markup")?.value);

    if (source === "markup" && cost > 0 && Number.isFinite(markup)) {
      newPrice = round2(cost * (1 + markup / 100));
      $("#purchase-item-new-price").value = newPrice.toFixed(2);
    } else if ((source === "cost" || source === "price") && cost > 0) {
      markup = ((newPrice / cost) - 1) * 100;
      $("#purchase-item-markup").value = round2(markup).toFixed(1);
    }

    if ($("#purchase-item-sum")) $("#purchase-item-sum").value = round2(qty * cost).toFixed(2);
  }

  function openPurchaseItemDialog() {
    const product = productById(purchaseSelectedProductId) || state.products[0];
    if (!product) return;
    selectPurchaseProduct(product.id, true);
    $("#purchase-item-dialog")?.showModal();
    window.setTimeout(() => $("#purchase-item-barcode")?.focus(), 20);
  }

  function addPurchaseDraftLine() {
    const draft = ensurePurchaseDraft();
    const product = productById(purchaseSelectedProductId);
    const qty = Number($("#purchase-item-qty")?.value) || 0;
    const cost = round2(Number($("#purchase-item-cost")?.value) || 0);
    const newPrice = round2(Number($("#purchase-item-new-price")?.value) || 0);

    if (!product || qty <= 0 || cost <= 0 || newPrice <= 0) {
      showToast("Перевірте товар, кількість, закупівельну та нову ціну.");
      return;
    }

    const existing = draft.lines.find(line => line.productId === product.id);
    if (existing) {
      existing.qty = round2(existing.qty + qty);
      existing.cost = cost;
      existing.newPrice = newPrice;
    } else {
      draft.lines.push({ productId: product.id, qty: round2(qty), cost, newPrice });
    }

    saveState();
    $("#purchase-item-dialog")?.close();
    renderPurchaseForm();
    showToast(`${product.name} додано в ${draft.id}`);
  }

  function openPurchasePostDialog() {
    const draft = ensurePurchaseDraft();
    if (!draft.lines.length) {
      showToast("У сесії немає позицій.");
      return;
    }
    if ($("#purchase-post-title")) $("#purchase-post-title").textContent = `Провести сесію ${draft.id}?`;
    $("#purchase-post-dialog")?.showModal();
  }

  function postPurchaseSession() {
    const draft = ensurePurchaseDraft();
    if (!draft.lines.length) return;
    const sessionId = draft.id;
    const supplierId = draft.supplierId;
    const postedAt = new Date().toISOString();

    draft.lines.forEach(line => {
      const product = productById(line.productId);
      if (!product) return;
      product.stock = round2(product.stock + line.qty);
      product.cost = line.cost;
      product.price = line.newPrice;
      state.purchases.unshift({
        id: `P${state.nextPurchase++}`,
        sessionId,
        at: postedAt,
        supplierId,
        productId: product.id,
        qty: line.qty,
        cost: line.cost,
        newPrice: line.newPrice
      });
    });

    state.purchaseDraft = {
      id: `SES-${String(state.nextPurchase).padStart(6, "0")}`,
      supplierId,
      lines: []
    };

    saveState();
    $("#purchase-post-dialog")?.close();
    renderAll();
    showToast(`${sessionId} проведено. Товари зараховано на склад.`);
  }

  function renderPurchaseHistory() {
    const root = $("#purchase-history");
    if (!root) return;
    if (!state.purchases.length) {
      root.innerHTML = '<div class="no-data">Проведених сесій ще немає.</div>';
      return;
    }

    const groups = new Map();
    state.purchases.forEach(purchase => {
      const numeric = String(purchase.id || "").replace(/\D/g, "");
      const key = purchase.sessionId || `SES-${numeric.padStart(6, "0")}`;
      if (!groups.has(key)) {
        groups.set(key, {
          id: key,
          at: purchase.at,
          supplierId: purchase.supplierId,
          positions: 0,
          qty: 0,
          total: 0
        });
      }
      const group = groups.get(key);
      group.positions += 1;
      group.qty += Number(purchase.qty || 0);
      group.total += Number(purchase.qty || 0) * Number(purchase.cost || 0);
    });

    root.innerHTML = Array.from(groups.values()).slice(0, 8).map(session => {
      const supplier = supplierById(session.supplierId);
      return `
        <div class="history-card">
          <span><strong>${session.id}</strong> · проведено<br><small>${supplier?.name || "Постачальник"} · ${formatDate(session.at)}</small></span>
          <strong>${session.positions} поз. · ${money(round2(session.total))}</strong>
        </div>
      `;
    }).join("");
  }

  function paymentLabel(payment) {
    return ({ cash: "Готівка", card: "Картка", mixed: "Змішана", debt: "Борг" })[payment] || payment;
  }

  function renderSalesHistory() {
    const tbody = $("#sales-history");
    if (!state.sales.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="no-data">Продажів ще немає.</td></tr>';
      return;
    }
    tbody.innerHTML = state.sales.slice(0, 30).map(sale => {
      const returned = window.OUTPOST_DEMO_RETURNS?.returnedAmountForSale?.(sale.id) || 0;
      const hasLineDetails = Array.isArray(sale.lines) && sale.lines.length > 0;
      const canReturn = hasLineDetails && returned < Number(sale.total || 0) - 0.004;
      return `
        <tr>
          <td><strong>${sale.id}</strong></td>
          <td>${formatDate(sale.at)}</td>
          <td>${paymentLabel(sale.payment)}</td>
          <td>${sale.itemCount}</td>
          <td><strong>${money(sale.total)}</strong></td>
          <td>${returned > 0 ? money(returned) : "—"}</td>
          <td><button class="win-btn return-action-btn" type="button" data-return-sale="${sale.id}" ${canReturn ? "" : "disabled"} title="${hasLineDetails ? (canReturn ? "Оформити повернення" : "Усе доступне вже повернено") : "Для анонімізованої історії рядки чека не публікуються"}">Повернення</button></td>
        </tr>
      `;
    }).join("");

    tbody.querySelectorAll("[data-return-sale]").forEach(button => {
      button.addEventListener("click", () => window.OUTPOST_DEMO_RETURNS?.openReturn?.(button.dataset.returnSale));
    });
  }

  function reportData() {
    const today = new Date().toDateString();
    const todaySales = state.sales.filter(s => new Date(s.at).toDateString() === today);
    const total = round2(todaySales.reduce((sum, sale) => sum + sale.total, 0));
    const debtTotal = round2(state.customers.reduce((sum, customer) => sum + customer.debt, 0));
    const lowStock = state.products.filter(p => p.stock < 5).length;
    return { todaySales, total, debtTotal, lowStock };
  }

  function renderHome() {
    const data = reportData();
    const cashSales = round2(data.todaySales.reduce((sum, sale) => sum + (sale.payment === "cash" ? sale.total : sale.payment === "mixed" ? (sale.cash || 0) : 0), 0));
    const cardSales = round2(data.todaySales.reduce((sum, sale) => sum + (sale.payment === "card" ? sale.total : sale.payment === "mixed" ? (sale.card || 0) : 0), 0));
    const openingCash = 1000;
    const expectedCash = round2(openingCash + cashSales);
    const stockValue = round2(state.products.reduce((sum, product) => sum + product.cost * product.stock, 0));
    const debtors = state.customers.filter(customer => customer.debt > 0).length;

    if ($("#home-sales")) $("#home-sales").textContent = money(data.total).replace("₴", "грн");
    if ($("#home-cash")) $("#home-cash").textContent = money(expectedCash).replace("₴", "грн");
    if ($("#home-cash-sales")) $("#home-cash-sales").textContent = money(cashSales).replace("₴", "грн");
    if ($("#home-card-sales")) $("#home-card-sales").textContent = money(cardSales).replace("₴", "грн");
    if ($("#home-checks")) $("#home-checks").textContent = String(data.todaySales.length);
    if ($("#home-stock-value")) $("#home-stock-value").textContent = money(stockValue).replace("₴", "грн");
    if ($("#home-low-stock")) $("#home-low-stock").textContent = String(data.lowStock);
    if ($("#home-low-tab")) $("#home-low-tab").textContent = String(data.lowStock);

    if ($("#extra-products")) $("#extra-products").textContent = String(state.products.length);
    if ($("#extra-active-products")) $("#extra-active-products").textContent = String(state.products.filter(product => product.stock > -50).length);
    if ($("#extra-purchases")) $("#extra-purchases").textContent = String(state.purchases.length);
    if ($("#extra-cash")) $("#extra-cash").textContent = money(expectedCash).replace("₴", "грн");
    if ($("#extra-debtors")) $("#extra-debtors").textContent = String(debtors);
    if ($("#extra-debt")) $("#extra-debt").textContent = money(data.debtTotal).replace("₴", "грн");
    window.OUTPOST_DEMO_MODULES?.syncHomeCash?.();
  }

  function renderReports() {
    const { todaySales, total, debtTotal, lowStock } = reportData();

    const stats = [
      ["Продажі сьогодні", money(total)],
      ["Кількість чеків", String(todaySales.length)],
      ["Борг клієнтів", money(debtTotal)],
      ["Мало товару", String(lowStock)]
    ];

    $("#stats-grid").innerHTML = stats.map(([label, value]) => `
      <div class="desktop-card"><span>${label}</span><strong>${value}</strong></div>
    `).join("");

    const paymentTotals = { cash: 0, card: 0, mixed: 0, debt: 0 };
    todaySales.forEach(sale => {
      paymentTotals[sale.payment] = round2((paymentTotals[sale.payment] || 0) + sale.total);
    });

    $("#payment-breakdown").innerHTML = Object.entries(paymentTotals).map(([key, value]) => `
      <div class="break-row"><span>${paymentLabel(key)}</span><strong>${money(value)}</strong></div>
    `).join("");

    const alerts = state.products.filter(p => p.stock < 5).sort((a, b) => a.stock - b.stock);
    $("#stock-alerts").innerHTML = alerts.length ? alerts.map(p => `
      <div class="alert-row"><span>${p.name}</span><strong class="stock-value ${stockClass(p.stock)}">${p.stock} ${p.unit}</strong></div>
    `).join("") : '<div class="no-data">Критичних залишків немає.</div>';

    renderHome();
  }

  window.OUTPOST_DEMO_API = {
    getState: () => state,
    getCart: () => JSON.parse(JSON.stringify(cart)),
    getCartTotal: cartTotal,
    getSelectedCartProductId: () => selectedCartProductId,
    getAppearance: () => ({ ...appearance }),
    saveState,
    renderAll,
    money,
    round2,
    productById,
    productCode,
    supplierById,
    customerById,
    showToast
  };

  function resetDemo() {
    if (!window.confirm("Скинути всі зміни та повернути початкові тестові дані?")) return;
    state = cloneSeed();
    state.purchaseDraft = {
      id: `SES-${String(state.nextPurchase || 204).padStart(6, "0")}`,
      supplierId: state.suppliers?.[0]?.id || "",
      lines: []
    };
    cart = [];
    selectedCartProductId = null;
    selectedCustomerId = null;
    f7SelectedProductId = null;
    saveState();
    renderAll();
    switchView("sale");
    showToast("Демо повернуто до початкового стану.");
  }

  Array.from(document.querySelectorAll(".demo-nav")).forEach(button => button.addEventListener("click", () => switchView(button.dataset.view)));
  Array.from(document.querySelectorAll("[data-view-link]")).forEach(button => button.addEventListener("click", () => switchView(button.dataset.viewLink)));
  $("#focus-product-search")?.addEventListener("click", () => {
    openProductSearch($("#product-search")?.value || "", "sale");
  });
  $("[data-clear-cart]")?.addEventListener("click", () => {
    cart = [];
    selectedCartProductId = null;
    renderCart();
  });
  $("#cart-dec-selected")?.addEventListener("click", () => {
    const line = selectedCartLine();
    if (line) setCartQty(line.productId, -1);
  });
  $("#cart-inc-selected")?.addEventListener("click", () => {
    const line = selectedCartLine();
    if (line) setCartQty(line.productId, 1);
  });
  $("#cart-delete-selected")?.addEventListener("click", () => {
    const line = selectedCartLine();
    if (line) removeCartProduct(line.productId);
  });
  $("#cart-discount-selected")?.addEventListener("click", openDiscountDialog);
  $("#apply-discount")?.addEventListener("click", applyCartDiscount);
  $$("[data-pay]").forEach(button => button.addEventListener("click", () => openPayment(button.dataset.pay)));
  Array.from(document.querySelectorAll("[data-reset-demo]")).forEach(button => button.addEventListener("click", resetDemo));

  $("#appearance-apply")?.addEventListener("click", applyAppearanceFromControls);

  ["#f7-code", "#f7-name", "#f7-barcode", "#f7-stock"].forEach(selector => {
    $(selector)?.addEventListener("input", renderF7Results);
  });
  $("#f7-add-selected")?.addEventListener("click", addF7SelectedProduct);
  $("#open-extra-info")?.addEventListener("click", () => {
    renderHome();
    $("#extra-info-dialog")?.showModal();
  });
  Array.from(document.querySelectorAll("[data-demo-info]")).forEach(button => button.addEventListener("click", () => {
    showToast(button.dataset.demoInfo || "Ця дія доступна у Windows-версії OutPOSt.");
  }));

  $("#product-search")?.addEventListener("input", () => {
    forceProductList = false;
  });
  $("#product-search")?.addEventListener("keydown", event => {
    if (event.key !== "Enter") return;
    const value = event.currentTarget.value.trim().toLowerCase();
    if (!value) return;
    const exact = state.products.find(product =>
      product.barcode.toLowerCase() === value ||
      productCode(product).toLowerCase() === value ||
      product.name.toLowerCase() === value
    );
    event.preventDefault();
    if (exact) {
      addProduct(exact.id);
      return;
    }
    openProductSearch(event.currentTarget.value.trim(), "sale");
  });
  $("#product-search-dialog")?.addEventListener("keydown", event => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      moveF7Selection(event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      addF7SelectedProduct();
    }
  });
  $("#cash-payment-received")?.addEventListener("input", updateCashPaymentChange);
  $("#cash-payment-received")?.addEventListener("keydown", event => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    confirmCashPayment();
  });
  $("#confirm-cash-payment")?.addEventListener("click", confirmCashPayment);
  $("#mixed-cash")?.addEventListener("input", updateMixedRemainder);
  $("#mixed-cash")?.addEventListener("keydown", event => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    confirmMixedPayment();
  });
  $("#debt-customer")?.addEventListener("keydown", event => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    confirmDebtSale();
  });
  $("#purchase-supplier")?.addEventListener("change", event => {
    const draft = ensurePurchaseDraft();
    draft.supplierId = event.currentTarget.value;
    saveState();
    renderPurchaseForm();
  });
  $("#open-purchase-item")?.addEventListener("click", openPurchaseItemDialog);
  $("#purchase-find-product")?.addEventListener("click", () => {
    $("#purchase-item-dialog")?.close();
    openProductSearch($("#purchase-item-barcode")?.value || "", "purchase");
  });
  $("#purchase-item-barcode")?.addEventListener("keydown", event => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const value = event.currentTarget.value.trim().toLowerCase();
    const product = state.products.find(item =>
      item.barcode.toLowerCase() === value || productCode(item).toLowerCase() === value
    );
    if (product) selectPurchaseProduct(product.id, true);
    else showToast("Товар за цим кодом не знайдено.");
  });
  $("#purchase-item-qty")?.addEventListener("input", () => updatePurchaseItemSummary());
  $("#purchase-item-cost")?.addEventListener("input", () => updatePurchaseItemSummary("cost"));
  $("#purchase-item-new-price")?.addEventListener("input", () => updatePurchaseItemSummary("price"));
  $("#purchase-item-markup")?.addEventListener("input", () => updatePurchaseItemSummary("markup"));
  $("#add-purchase-draft-line")?.addEventListener("click", addPurchaseDraftLine);
  $("#post-purchase-session")?.addEventListener("click", openPurchasePostDialog);
  $("#confirm-post-purchase-session")?.addEventListener("click", postPurchaseSession);

  $("#confirm-mixed")?.addEventListener("click", confirmMixedPayment);
  $("#confirm-debt")?.addEventListener("click", confirmDebtSale);

  $("#product-search-dialog")?.addEventListener("close", resumeAfterProductSearch);
  ["#seller-help-dialog", "#cash-payment-dialog", "#mixed-dialog", "#debt-dialog"].forEach(selector => {
    $(selector)?.addEventListener("close", restoreSaleSearchFocus);
  });

  function handlePaymentShortcut(type, keyLabel) {
    if (activeView !== "sale") {
      switchView("sale");
      showToast(`${keyLabel}: оплата доступна на екрані «Продаж». Натисніть ${keyLabel} ще раз.`);
      return;
    }
    openPayment(type);
  }

  document.addEventListener("keydown", event => {
    const openDialog = $(".demo-dialog[open]");
    if (openDialog && /^F[1-7]$/.test(event.key)) {
      if (event.key === "F7" && openDialog.id === "inventory-count-dialog" && window.OUTPOST_DEMO_MODULES?.handleF7?.()) {
        event.preventDefault();
        return;
      }
      event.preventDefault();
      return;
    }

    if (event.key === "F1") {
      event.preventDefault();
      const dialog = $("#seller-help-dialog");
      if (dialog && !dialog.open) dialog.showModal();
      window.setTimeout(() => $("#seller-help-dialog .dialog-close")?.focus(), 20);
    } else if (event.key === "F2") {
      event.preventDefault();
      handlePaymentShortcut("cash", "F2");
    } else if (event.key === "F3") {
      event.preventDefault();
      handlePaymentShortcut("card", "F3");
    } else if (event.key === "F4") {
      event.preventDefault();
      handlePaymentShortcut("mixed", "F4");
    } else if (event.key === "F5") {
      event.preventDefault();
      handlePaymentShortcut("debt", "F5");
    } else if (event.key === "F6") {
      event.preventDefault();
      switchView("purchases");
      window.setTimeout(() => $("#open-purchase-item")?.focus(), 20);
    } else if (event.key === "F7") {
      if (window.OUTPOST_DEMO_MODULES?.handleF7?.()) {
        event.preventDefault();
        return;
      }
      event.preventDefault();
      switchView("sale");
      openProductSearch($("#product-search")?.value || "", "sale");
    } else if (event.key === "Delete" && activeView === "sale" && !["INPUT", "TEXTAREA", "SELECT"].includes(event.target?.tagName)) {
      const line = selectedCartLine();
      if (line) {
        event.preventDefault();
        removeCartProduct(line.productId);
      }
    } else if ((event.key === "+" || event.code === "NumpadAdd") && activeView === "sale" && !["INPUT", "TEXTAREA", "SELECT"].includes(event.target?.tagName)) {
      const line = selectedCartLine();
      if (line) {
        event.preventDefault();
        setCartQty(line.productId, 1);
      }
    } else if ((event.key === "-" || event.code === "NumpadSubtract") && activeView === "sale" && !["INPUT", "TEXTAREA", "SELECT"].includes(event.target?.tagName)) {
      const line = selectedCartLine();
      if (line) {
        event.preventDefault();
        setCartQty(line.productId, -1);
      }
    } else if (event.key === "Escape") {
      $$(".demo-dialog[open]").forEach(dialog => dialog.close());
    }
  });

  applyAppearance(appearance);
  syncAppearanceControls();
  renderAll();
  switchView(activeView);
})();
