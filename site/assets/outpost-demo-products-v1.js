(() => {
  "use strict";

  const api = window.OUTPOST_DEMO_API;
  if (!api) return;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const dateFmt = new Intl.DateTimeFormat("uk-UA", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });

  let selectedProductId = null;

  function state() {
    return api.getState();
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char];
    });
  }

  function ensureState() {
    const s = state();
    let changed = false;
    if (!Number.isFinite(Number(s.nextDemoProduct)) || Number(s.nextDemoProduct) < 1) {
      s.nextDemoProduct = 1;
      changed = true;
    }
    if (changed) api.saveState();
    return s;
  }

  function nextInternalCode() {
    const max = ensureState().products.reduce(function (current, product) {
      const numeric = Number(String(product.code || "").replace(/\D/g, ""));
      return Number.isFinite(numeric) ? Math.max(current, numeric) : current;
    }, 10000);
    return String(max + 1);
  }

  function filteredProducts() {
    const s = ensureState();
    const query = ($("#product-stock-search")?.value || "").trim().toLowerCase();
    const items = s.products.filter(function (product) {
      if (!query) return true;
      return String(product.name || "").toLowerCase().includes(query) ||
        String(product.barcode || "").toLowerCase().includes(query) ||
        String(api.productCode(product) || "").toLowerCase().includes(query) ||
        String(product.category || "").toLowerCase().includes(query);
    });
    return items.sort(function (a, b) {
      const ac = Number(String(api.productCode(a)).replace(/\D/g, ""));
      const bc = Number(String(api.productCode(b)).replace(/\D/g, ""));
      if (Number.isFinite(ac) && Number.isFinite(bc)) return ac - bc;
      return String(a.name || "").localeCompare(String(b.name || ""), "uk");
    });
  }

  function renderTable() {
    const tbody = $("#products-table");
    if (!tbody) return;

    const items = filteredProducts();
    if (selectedProductId && !items.some(function (item) { return item.id === selectedProductId; })) {
      selectedProductId = null;
    }

    tbody.innerHTML = items.length ? items.map(function (product) {
      const selected = product.id === selectedProductId ? " is-selected" : "";
      const stockClass = Number(product.stock) <= 0 ? "critical" : Number(product.stock) < 5 ? "low" : "";
      return '<tr class="product-stock-row' + selected + '" data-product-stock-row="' + esc(product.id) + '">' +
        "<td>" + esc(api.productCode(product)) + "</td>" +
        "<td>" + esc(product.barcode || "") + "</td>" +
        "<td><strong>" + esc(product.name) + "</strong><br><small>" + esc(product.category || "—") + "</small></td>" +
        "<td>" + esc(api.money(product.price)) + "</td>" +
        "<td>" + esc(api.money(product.cost)) + "</td>" +
        '<td><span class="stock-value ' + stockClass + '">' + esc(Number(product.stock).toLocaleString("uk-UA")) + " " + esc(product.unit || "шт") + "</span></td>" +
        "</tr>";
    }).join("") : '<tr><td colspan="6" class="no-data">Товарів за цим фільтром не знайдено.</td></tr>';

    $$("[data-product-stock-row]", tbody).forEach(function (row) {
      row.addEventListener("click", function () {
        selectedProductId = row.dataset.productStockRow;
        renderTable();
      });
      row.addEventListener("dblclick", function () {
        selectedProductId = row.dataset.productStockRow;
        openMovements();
      });
    });

    if ($("#product-stock-count")) $("#product-stock-count").textContent = items.length + " із " + ensureState().products.length;
    if ($("#product-movements")) $("#product-movements").disabled = !selectedProductId;
  }

  function productMovements(productId) {
    const s = ensureState();
    const product = api.productById(productId);
    if (!product) return [];
    const movements = [];

    (s.purchases || []).forEach(function (purchase) {
      if (purchase.productId !== productId) return;
      movements.push({
        at: purchase.at,
        type: "Прихід",
        qty: Number(purchase.qty || 0),
        cost: Number(purchase.cost || product.cost || 0),
        referenceType: "Закупівля",
        referenceId: purchase.sessionId || purchase.id || "—",
        user: "Адмін"
      });
    });

    (s.sales || []).forEach(function (sale) {
      (sale.lines || []).forEach(function (line) {
        if (line.productId !== productId) return;
        movements.push({
          at: sale.at,
          type: "Продаж",
          qty: -Number(line.qty || 0),
          cost: Number(product.cost || 0),
          referenceType: "Продаж",
          referenceId: sale.id || "—",
          user: "Адмін"
        });
      });
    });

    (s.returns || []).forEach(function (record) {
      (record.lines || []).forEach(function (line) {
        if (line.productId !== productId) return;
        movements.push({
          at: record.at,
          type: "Повернення",
          qty: Number(line.qty || 0),
          cost: Number(product.cost || 0),
          referenceType: "Повернення",
          referenceId: record.id || "—",
          user: "Адмін"
        });
      });
    });

    (s.writeoffs || []).forEach(function (document) {
      (document.lines || []).forEach(function (line) {
        if (line.productId !== productId) return;
        movements.push({
          at: document.at,
          type: "Списання",
          qty: -Number(line.qty || 0),
          cost: Number(line.cost || product.cost || 0),
          referenceType: "Списання",
          referenceId: document.id || "—",
          user: document.user || "Адмін"
        });
      });
    });

    (s.inventories || []).forEach(function (inventory) {
      if (inventory.status !== "posted") return;
      const item = (inventory.items || []).find(function (candidate) { return candidate.productId === productId; });
      if (!item || item.actual == null) return;
      const difference = api.round2(Number(item.actual) - Number(item.expected));
      if (Math.abs(difference) < 0.0001) return;
      movements.push({
        at: inventory.postedAt || inventory.startedAt,
        type: "Інвентаризація",
        qty: difference,
        cost: Number(product.cost || 0),
        referenceType: "Інвентаризація",
        referenceId: inventory.id || "—",
        user: inventory.user || "Адмін"
      });
    });

    return movements.sort(function (a, b) {
      return String(b.at || "").localeCompare(String(a.at || ""));
    });
  }

  function openMovements() {
    const product = api.productById(selectedProductId);
    if (!product) {
      api.showToast("Оберіть товар.");
      return;
    }

    const movements = productMovements(product.id);
    if ($("#stock-movements-title")) $("#stock-movements-title").textContent = "Рух товару — " + product.name;
    if ($("#stock-movements-count")) $("#stock-movements-count").textContent = "Операцій: " + movements.length;

    const tbody = $("#stock-movements-table");
    if (tbody) {
      tbody.innerHTML = movements.length ? movements.map(function (movement) {
        const qty = Number(movement.qty || 0);
        const qtyText = (qty > 0 ? "+" : "") + qty.toLocaleString("uk-UA", { maximumFractionDigits: 3 });
        return "<tr>" +
          "<td>" + esc(dateFmt.format(new Date(movement.at))) + "</td>" +
          "<td><strong>" + esc(product.name) + "</strong></td>" +
          "<td>" + esc(movement.type) + "</td>" +
          "<td><strong>" + esc(qtyText) + "</strong></td>" +
          "<td>" + esc(api.money(movement.cost)) + "</td>" +
          "<td>" + esc(movement.referenceType) + "</td>" +
          "<td>" + esc(movement.referenceId) + "</td>" +
          "<td>" + esc(movement.user || "Адмін") + "</td>" +
          "</tr>";
      }).join("") : '<tr><td colspan="8" class="no-data">Для цього товару в поточному демо-сеансі рухів ще немає.</td></tr>';
    }

    const dialog = $("#stock-movements-dialog");
    if (dialog && !dialog.open) dialog.showModal();
  }

  function fillCategoryChoices() {
    const select = $("#product-new-category");
    if (!select) return;
    const categories = Array.from(new Set(ensureState().products.map(function (product) {
      return String(product.category || "").trim();
    }).filter(Boolean))).sort(function (a, b) { return a.localeCompare(b, "uk"); });
    select.innerHTML = '<option value="">— без категорії —</option>' +
      categories.map(function (category) {
        return '<option value="' + esc(category) + '">' + esc(category) + "</option>";
      }).join("");
  }

  function openNewProduct() {
    fillCategoryChoices();
    if ($("#product-new-code")) $("#product-new-code").value = nextInternalCode();
    if ($("#product-new-name")) $("#product-new-name").value = "";
    if ($("#product-new-barcode")) $("#product-new-barcode").value = "";
    if ($("#product-new-category")) $("#product-new-category").value = "";
    if ($("#product-new-unit")) $("#product-new-unit").value = "шт";
    if ($("#product-new-cost")) $("#product-new-cost").value = "0";
    if ($("#product-new-price")) $("#product-new-price").value = "0";
    if ($("#product-new-min-price")) $("#product-new-min-price").value = "0";
    if ($("#product-new-min-stock")) $("#product-new-min-stock").value = "0";
    if ($("#product-new-error")) $("#product-new-error").textContent = "";

    const dialog = $("#product-new-dialog");
    if (dialog && !dialog.open) dialog.showModal();
    $("#product-new-name")?.focus();
  }

  function saveNewProduct() {
    const s = ensureState();
    const name = ($("#product-new-name")?.value || "").trim();
    const barcode = ($("#product-new-barcode")?.value || "").trim();
    const code = ($("#product-new-code")?.value || nextInternalCode()).trim();
    const category = $("#product-new-category")?.value || "";
    const unit = $("#product-new-unit")?.value || "шт";
    const cost = api.round2(Number($("#product-new-cost")?.value) || 0);
    const price = api.round2(Number($("#product-new-price")?.value) || 0);
    const minimumPrice = api.round2(Number($("#product-new-min-price")?.value) || 0);
    const minimumStock = Math.round(((Number($("#product-new-min-stock")?.value) || 0) + Number.EPSILON) * 1000) / 1000;
    const error = $("#product-new-error");

    if (!name) {
      if (error) error.textContent = "Вкажіть назву товару.";
      $("#product-new-name")?.focus();
      return;
    }
    if (cost < 0 || price < 0 || minimumPrice < 0 || minimumStock < 0) {
      if (error) error.textContent = "Ціни та мінімальний залишок не можуть бути від’ємними.";
      return;
    }
    if (minimumPrice > price && price >= 0) {
      if (error) error.textContent = "Мінімальна ціна не може бути більшою за роздрібну.";
      return;
    }
    if (barcode && s.products.some(function (product) {
      return String(product.barcode || "").toLowerCase() === barcode.toLowerCase();
    })) {
      if (error) error.textContent = "Такий штрих-код уже використовується іншим товаром.";
      $("#product-new-barcode")?.focus();
      $("#product-new-barcode")?.select();
      return;
    }

    const id = "pd" + String(s.nextDemoProduct++).padStart(4, "0");
    const product = {
      id: id,
      code: code,
      name: name,
      category: category,
      barcode: barcode,
      price: price,
      cost: cost,
      minimumPrice: minimumPrice,
      minimumStock: minimumStock,
      stock: 0,
      unit: unit,
      demoCreated: true
    };

    s.products.push(product);
    selectedProductId = id;
    if ($("#product-stock-search")) $("#product-stock-search").value = "";
    api.saveState();
    $("#product-new-dialog")?.close();
    api.renderAll();
    api.showToast("Товар «" + name + "» додано до демо. Початковий залишок: 0 " + unit + ".");
  }

  function renderAll() {
    ensureState();
    renderTable();
  }

  function renderView(view) {
    if (view === "products") renderTable();
  }

  function initEvents() {
    $("#product-stock-search")?.addEventListener("input", renderTable);
    $("#new-product")?.addEventListener("click", openNewProduct);
    $("#product-movements")?.addEventListener("click", openMovements);
    $("#save-new-product")?.addEventListener("click", saveNewProduct);
  }

  window.OUTPOST_DEMO_PRODUCTS_MODULE = {
    renderAll: renderAll,
    renderView: renderView,
    productMovements: productMovements
  };

  ensureState();
  initEvents();
  api.renderAll();
})();