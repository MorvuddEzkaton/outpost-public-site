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

  let activeSaleId = null;
  let returnDraft = new Map();
  let paymentTotal = 0;
  let debtLimit = 0;

  function state() {
    return api.getState();
  }

  function ensureState() {
    const s = state();
    let changed = false;
    if (!Array.isArray(s.returns)) { s.returns = []; changed = true; }
    if (!Number.isFinite(Number(s.nextReturn)) || Number(s.nextReturn) < 1) { s.nextReturn = 1; changed = true; }
    if (changed) api.saveState();
    return s;
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char];
    });
  }

  function roundQty(value) {
    return Math.round((Number(value) + Number.EPSILON) * 1000) / 1000;
  }

  function saleById(id) {
    return ensureState().sales.find(function (sale) { return String(sale.id) === String(id); }) || null;
  }

  function sameLocalDay(value, reference) {
    const a = new Date(value);
    const b = reference || new Date();
    return !Number.isNaN(a.getTime()) &&
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate();
  }

  function returnedLinesForSale(saleId) {
    return ensureState().returns
      .filter(function (record) { return String(record.saleId) === String(saleId); })
      .flatMap(function (record) { return Array.isArray(record.lines) ? record.lines : []; });
  }

  function alreadyReturnedQty(saleId, productId) {
    return roundQty(returnedLinesForSale(saleId)
      .filter(function (line) { return line.productId === productId; })
      .reduce(function (sum, line) { return sum + Number(line.qty || 0); }, 0));
  }

  function returnedAmountForSale(saleId) {
    return api.round2(ensureState().returns
      .filter(function (record) { return String(record.saleId) === String(saleId); })
      .reduce(function (sum, record) { return sum + Number(record.total || 0); }, 0));
  }

  function returnableItems(sale) {
    if (!sale || !Array.isArray(sale.lines)) return [];
    return sale.lines.map(function (line) {
      const sold = roundQty(Number(line.qty || 0));
      const returned = alreadyReturnedQty(sale.id, line.productId);
      return {
        productId: line.productId,
        name: line.name || api.productById(line.productId)?.name || "Товар",
        sold: sold,
        returned: returned,
        available: roundQty(Math.max(0, sold - returned)),
        price: api.round2(Number(line.price || 0))
      };
    }).filter(function (item) { return item.sold > 0; });
  }

  function draftTotal() {
    const sale = saleById(activeSaleId);
    if (!sale) return 0;
    const items = returnableItems(sale);
    return api.round2(items.reduce(function (sum, item) {
      const qty = roundQty(Number(returnDraft.get(item.productId) || 0));
      return sum + qty * item.price;
    }, 0));
  }

  function renderReturnDialog() {
    const sale = saleById(activeSaleId);
    if (!sale) return;

    const items = returnableItems(sale);
    if ($("#sale-return-title")) $("#sale-return-title").textContent = "Повернення з чека " + sale.id;
    if ($("#sale-return-meta")) {
      const customer = sale.customerId ? api.customerById(sale.customerId) : null;
      $("#sale-return-meta").textContent = dateFmt.format(new Date(sale.at)) + (customer ? " · " + customer.name : "");
    }

    const tbody = $("#sale-return-items");
    if (tbody) {
      tbody.innerHTML = items.length ? items.map(function (item) {
        const qty = Number(returnDraft.get(item.productId) || 0);
        return "<tr>" +
          "<td><strong>" + esc(item.name) + "</strong></td>" +
          "<td>" + item.sold.toLocaleString("uk-UA") + "</td>" +
          "<td>" + item.returned.toLocaleString("uk-UA") + "</td>" +
          "<td>" + item.available.toLocaleString("uk-UA") + "</td>" +
          '<td><input class="return-qty-input" type="number" min="0" step="0.001" max="' + esc(item.available) + '" data-return-qty="' + esc(item.productId) + '" value="' + esc(qty || "") + '"' + (item.available <= 0 ? " disabled" : "") + "/></td>" +
          "<td>" + esc(api.money(item.price)) + "</td>" +
          "</tr>";
      }).join("") : '<tr><td colspan="6" class="no-data">У цьому чеку немає доступних позицій для повернення.</td></tr>';

      $$("[data-return-qty]", tbody).forEach(function (input) {
        input.addEventListener("input", function () {
          const item = items.find(function (candidate) { return candidate.productId === input.dataset.returnQty; });
          if (!item) return;
          const raw = input.value.trim();
          let qty = raw === "" ? 0 : Number(raw);
          if (!Number.isFinite(qty) || qty < 0) qty = 0;
          qty = roundQty(Math.min(qty, item.available));
          returnDraft.set(item.productId, qty);
          if (raw !== "" && Number(raw) !== qty) input.value = String(qty);
          if ($("#sale-return-total")) $("#sale-return-total").textContent = api.money(draftTotal()).replace("₴", "грн");
        });
      });
    }

    if ($("#sale-return-total")) $("#sale-return-total").textContent = api.money(draftTotal()).replace("₴", "грн");
    if ($("#open-return-payment")) $("#open-return-payment").disabled = !items.some(function (item) { return item.available > 0; });
  }

  function openReturn(saleId) {
    const sale = saleById(saleId);
    if (!sale) {
      api.showToast("Продаж не знайдено.");
      return;
    }
    if (!Array.isArray(sale.lines) || !sale.lines.length) {
      api.showToast("Для анонімізованої історії рядки чека не публікуються. Створіть новий продаж у демо й поверніть його.");
      return;
    }

    const items = returnableItems(sale);
    if (!items.some(function (item) { return item.available > 0; })) {
      api.showToast("Усі доступні товари цього чека вже повернено.");
      return;
    }

    activeSaleId = sale.id;
    returnDraft = new Map(items.map(function (item) { return [item.productId, 0]; }));
    renderReturnDialog();
    const dialog = $("#sale-return-dialog");
    if (dialog && !dialog.open) dialog.showModal();
  }

  function returnAllAvailable() {
    const sale = saleById(activeSaleId);
    if (!sale) return;
    returnableItems(sale).forEach(function (item) {
      returnDraft.set(item.productId, item.available);
    });
    renderReturnDialog();
  }

  function selectedReturnLines() {
    const sale = saleById(activeSaleId);
    if (!sale) return [];
    return returnableItems(sale).map(function (item) {
      const qty = roundQty(Number(returnDraft.get(item.productId) || 0));
      return {
        productId: item.productId,
        name: item.name,
        qty: Math.min(qty, item.available),
        price: item.price
      };
    }).filter(function (line) { return line.qty > 0; });
  }

  function updatePaymentStatus() {
    const cash = api.round2(Number($("#return-payment-cash")?.value) || 0);
    const card = api.round2(Number($("#return-payment-card")?.value) || 0);
    const debt = api.round2(Number($("#return-payment-debt")?.value) || 0);
    const sum = api.round2(cash + card + debt);
    const difference = api.round2(paymentTotal - sum);
    if ($("#return-payment-status")) {
      $("#return-payment-status").textContent = "Вказано: " + api.money(sum) + " · різниця: " + api.money(difference);
    }
  }

  function openReturnPayment() {
    const lines = selectedReturnLines();
    if (!lines.length) {
      api.showToast("Вкажіть кількість хоча б одного товару.");
      return;
    }

    paymentTotal = api.round2(lines.reduce(function (sum, line) {
      return sum + Number(line.qty) * Number(line.price);
    }, 0));
    const sale = saleById(activeSaleId);
    const customer = sale?.customerId ? api.customerById(sale.customerId) : null;
    debtLimit = customer ? api.round2(Math.min(Number(customer.debt || 0), paymentTotal)) : 0;

    if ($("#return-payment-total")) $("#return-payment-total").textContent = "До повернення: " + api.money(paymentTotal);
    if ($("#return-payment-cash")) $("#return-payment-cash").value = paymentTotal.toFixed(2);
    if ($("#return-payment-card")) $("#return-payment-card").value = "0";
    if ($("#return-payment-debt")) {
      $("#return-payment-debt").value = "0";
      $("#return-payment-debt").disabled = !customer;
    }
    if ($("#return-debt-hint")) {
      $("#return-debt-hint").textContent = customer
        ? "Максимально доступне зменшення боргу для цього демо-повернення: " + api.money(debtLimit) + "."
        : "Продаж не прив’язаний до клієнта — зменшення боргу недоступне.";
    }
    updatePaymentStatus();
    $("#sale-return-dialog")?.close();
    const dialog = $("#return-payment-dialog");
    if (dialog && !dialog.open) dialog.showModal();
    window.setTimeout(function () {
      $("#return-payment-cash")?.focus();
      $("#return-payment-cash")?.select();
    }, 20);
  }

  function backToItems() {
    $("#return-payment-dialog")?.close();
    renderReturnDialog();
    const dialog = $("#sale-return-dialog");
    if (dialog && !dialog.open) dialog.showModal();
  }

  function paymentSummary(payments) {
    const labels = { cash: "Готівка", card: "Картка", debt: "Зменшення боргу" };
    return payments.map(function (payment) {
      return (labels[payment.type] || payment.type) + " " + api.money(payment.amount);
    }).join(" · ");
  }

  function confirmReturn() {
    const s = ensureState();
    const sale = saleById(activeSaleId);
    const lines = selectedReturnLines();
    if (!sale || !lines.length) {
      api.showToast("Немає позицій для повернення.");
      return;
    }

    const cash = api.round2(Number($("#return-payment-cash")?.value) || 0);
    const card = api.round2(Number($("#return-payment-card")?.value) || 0);
    const debt = api.round2(Number($("#return-payment-debt")?.value) || 0);
    if (cash < 0 || card < 0 || debt < 0) {
      api.showToast("Суми повернення не можуть бути від’ємними.");
      return;
    }
    if (api.round2(cash + card + debt) !== paymentTotal) {
      api.showToast("Сума способів повернення повинна дорівнювати " + api.money(paymentTotal) + ".");
      return;
    }

    const customer = sale.customerId ? api.customerById(sale.customerId) : null;
    if (!customer && debt > 0) {
      api.showToast("Зменшення боргу недоступне без клієнта.");
      return;
    }
    if (debt > debtLimit + 0.004) {
      api.showToast("Зменшення боргу перевищує доступний ліміт.");
      return;
    }

    if (cash > 0) {
      const summary = window.OUTPOST_DEMO_MODULES?.getCashSummary?.();
      if (!summary?.isOpen) {
        api.showToast("Для повернення готівкою спочатку відкрийте касову зміну.");
        return;
      }
      if (cash > Number(summary.expected || 0) + 0.004) {
        api.showToast("У касі недостатньо готівки для повернення.");
        return;
      }
    }

    lines.forEach(function (line) {
      const product = api.productById(line.productId);
      if (product) product.stock = api.round2(Number(product.stock || 0) + Number(line.qty || 0));
    });

    if (debt > 0 && customer) {
      customer.debt = api.round2(Math.max(0, Number(customer.debt || 0) - debt));
    }

    const id = "RET-" + String(s.nextReturn++).padStart(6, "0");
    const at = new Date().toISOString();
    const payments = [];
    if (cash > 0) payments.push({ type: "cash", amount: cash });
    if (card > 0) payments.push({ type: "card", amount: card });
    if (debt > 0) payments.push({ type: "debt", amount: debt });

    const record = {
      id: id,
      saleId: sale.id,
      saleNumber: sale.id,
      at: at,
      total: paymentTotal,
      customerId: sale.customerId || null,
      customerName: customer?.name || "",
      payments: payments,
      lines: lines.map(function (line) {
        return {
          productId: line.productId,
          name: line.name,
          qty: roundQty(line.qty),
          price: api.round2(line.price),
          amount: api.round2(line.qty * line.price)
        };
      }),
      status: "local"
    };
    s.returns.unshift(record);

    if (cash > 0) {
      s.cashMovements.unshift({
        id: "CM-RET-" + Date.now(),
        type: "SaleReturn",
        direction: "out",
        affectsCash: true,
        amount: cash,
        at: at,
        comment: "Повернення " + id + " · чек " + sale.id,
        user: "Адмін"
      });
    }

    api.saveState();
    $("#return-payment-dialog")?.close();
    $("#sale-return-dialog")?.close();
    activeSaleId = null;
    returnDraft = new Map();
    api.renderAll();
    api.showToast("Повернення " + id + " проведено на " + api.money(paymentTotal) + ".");
  }

  function renderReturnHistory() {
    const s = ensureState();
    const tbody = $("#returns-history");
    if (tbody) {
      tbody.innerHTML = s.returns.length ? s.returns.slice(0, 20).map(function (record) {
        return "<tr>" +
          "<td><strong>" + esc(record.id) + "</strong></td>" +
          "<td>" + esc(record.saleNumber || record.saleId) + "</td>" +
          "<td>" + esc(dateFmt.format(new Date(record.at))) + "</td>" +
          "<td><strong>" + esc(api.money(record.total)) + "</strong></td>" +
          "<td>" + esc(record.customerName || "—") + "</td>" +
          "<td>" + esc(paymentSummary(record.payments || [])) + "</td>" +
          "<td>Локально · демо</td>" +
          "</tr>";
      }).join("") : '<tr><td colspan="7" class="no-data">Повернень ще немає.</td></tr>';
    }
    if ($("#returns-history-count")) $("#returns-history-count").textContent = s.returns.length + " повернень";
  }

  function renderHomeReturns() {
    const total = api.round2(ensureState().returns
      .filter(function (record) { return sameLocalDay(record.at); })
      .reduce(function (sum, record) { return sum + Number(record.total || 0); }, 0));
    if ($("#home-returns")) $("#home-returns").textContent = api.money(total).replace("₴", "грн");
  }

  function renderAll() {
    ensureState();
    renderReturnHistory();
    renderHomeReturns();
  }

  function renderView(view) {
    if (view === "history") {
      renderReturnHistory();
      renderHomeReturns();
    }
  }

  function initEvents() {
    $("#return-all-available")?.addEventListener("click", returnAllAvailable);
    $("#open-return-payment")?.addEventListener("click", openReturnPayment);
    $("#back-to-return-items")?.addEventListener("click", backToItems);
    $("#confirm-sale-return")?.addEventListener("click", confirmReturn);
    ["#return-payment-cash", "#return-payment-card", "#return-payment-debt"].forEach(function (selector) {
      $(selector)?.addEventListener("input", updatePaymentStatus);
    });
  }

  window.OUTPOST_DEMO_RETURNS = {
    openReturn: openReturn,
    returnedAmountForSale: returnedAmountForSale,
    renderAll: renderAll,
    renderView: renderView
  };

  ensureState();
  initEvents();
  api.renderAll();
})();