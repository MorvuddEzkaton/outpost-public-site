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

  let writeoffDraft = [];
  let selectedInventoryId = null;
  let activeInventoryId = null;
  let cashActionMode = "in";

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
    if (!Array.isArray(s.writeoffs)) { s.writeoffs = []; changed = true; }
    if (!Array.isArray(s.inventories)) { s.inventories = []; changed = true; }
    if (!Array.isArray(s.cashMovements)) { s.cashMovements = []; changed = true; }
    if (!Array.isArray(s.cashShifts)) { s.cashShifts = []; changed = true; }
    if (!Number.isFinite(Number(s.nextWriteoff)) || Number(s.nextWriteoff) < 1) { s.nextWriteoff = 1; changed = true; }
    if (!Number.isFinite(Number(s.nextInventory)) || Number(s.nextInventory) < 1) { s.nextInventory = 1; changed = true; }
    if (!Number.isFinite(Number(s.nextCashShift)) || Number(s.nextCashShift) < 1) { s.nextCashShift = 2; changed = true; }

    if (!s.cashShiftInitialized) {
      const openedAt = new Date();
      openedAt.setHours(0, 0, 0, 0);
      s.currentCashShift = {
        id: 1,
        status: "open",
        openingBalance: 1000,
        openedAt: openedAt.toISOString(),
        openedByName: "Адмін"
      };
      s.cashShiftInitialized = true;
      if (Number(s.nextCashShift) <= 1) s.nextCashShift = 2;
      changed = true;
    }

    if (changed) api.saveState();
    return s;
  }

  function currentShift() {
    return ensureState().currentCashShift || null;
  }

  function lastClosedShift() {
    return ensureState().cashShifts[0] || null;
  }

  function isAtOrAfter(value, threshold) {
    const current = new Date(value).getTime();
    const start = new Date(threshold).getTime();
    return Number.isFinite(current) && Number.isFinite(start) && current >= start;
  }

  function isWithinOpenShift(value, shift) {
    if (!shift || !isAtOrAfter(value, shift.openedAt)) return false;
    const current = new Date(value).getTime();
    return Number.isFinite(current) && current <= Date.now();
  }

  function sameLocalDay(value, reference) {
    const a = new Date(value);
    const b = reference || new Date();
    return !Number.isNaN(a.getTime()) &&
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate();
  }

  function cashDirection(movement) {
    if (movement && (movement.direction === "in" || movement.direction === "out")) return movement.direction;
    const raw = String((movement && movement.type) || "").toLowerCase();
    if (raw.includes("cashout") || raw.includes("withdraw") || raw.includes("expense") || raw.includes("supplier") || raw.includes("вилуч")) return "out";
    if (raw.includes("cashin") || raw.includes("deposit") || raw.includes("income") || raw.includes("sale") || raw.includes("debt") || raw.includes("внес")) return "in";
    return "neutral";
  }

  function cashMovementLabel(movement) {
    const raw = String((movement && movement.type) || "");
    const key = raw.toLowerCase();
    if (key === "cashin") return "Внесення";
    if (key === "cashout") return "Вилучення";
    if (key === "debtrepayment") return "Повернення боргу";
    if (key.includes("return")) return "Повернення продажу";
    if (key.includes("sale")) return "Продаж";
    if (key.includes("supplier")) return "Оплата постачальнику";
    return raw || "Рух каси";
  }

  function cashSalesForShift(shift) {
    if (!shift) return 0;
    return api.round2(ensureState().sales
      .filter(function (sale) { return isWithinOpenShift(sale.at, shift); })
      .reduce(function (sum, sale) {
        if (sale.payment === "cash") return sum + Number(sale.total || 0);
        if (sale.payment === "mixed") return sum + Number(sale.cash || 0);
        return sum;
      }, 0));
  }

  function cashSummary() {
    const s = ensureState();
    const shift = s.currentCashShift || null;

    if (!shift) {
      const last = s.cashShifts[0] || null;
      const current = api.round2(Number(last?.actualClosingBalance ?? last?.expectedClosingBalance ?? 0));
      return {
        isOpen: false,
        shift: null,
        opening: api.round2(Number(last?.openingBalance || 0)),
        sales: 0,
        inAmount: 0,
        outAmount: 0,
        expected: current
      };
    }

    const opening = api.round2(Number(shift.openingBalance || 0));
    const sales = cashSalesForShift(shift);
    let cashIn = 0;
    let cashOut = 0;

    s.cashMovements.forEach(function (movement) {
      if (movement.affectsCash !== true || !isWithinOpenShift(movement.at, shift)) return;
      const direction = cashDirection(movement);
      const amount = Number(movement.amount || 0);
      if (direction === "in") cashIn += amount;
      if (direction === "out") cashOut += amount;
    });

    cashIn = api.round2(cashIn);
    cashOut = api.round2(cashOut);
    return {
      isOpen: true,
      shift: shift,
      opening: opening,
      sales: sales,
      inAmount: cashIn,
      outAmount: cashOut,
      expected: api.round2(opening + sales + cashIn - cashOut)
    };
  }

  function shiftMetaText(shift) {
    if (!shift) return "Немає відкритої зміни";
    return "Зміна #" + shift.id + " · " + dateFmt.format(new Date(shift.openedAt));
  }

  function syncHomeCash() {
    const summary = cashSummary();
    const s = ensureState();
    const shift = s.currentCashShift || null;
    const last = s.cashShifts[0] || null;

    if ($("#home-cash")) $("#home-cash").textContent = api.money(summary.expected).replace("₴", "грн");
    if ($("#extra-cash")) $("#extra-cash").textContent = api.money(summary.expected).replace("₴", "грн");
    if ($("#home-shift-status")) $("#home-shift-status").textContent = shift ? "Відкрита" : "Закрита";
    if ($("#home-shift-meta")) {
      $("#home-shift-meta").textContent = shift
        ? shiftMetaText(shift)
        : (last ? "Остання зміна #" + last.id + " · закрито " + dateFmt.format(new Date(last.closedAt)) : "Немає відкритої зміни");
    }
    if ($("#home-shift-action")) $("#home-shift-action").textContent = shift ? "Закрити зміну" : "Відкрити зміну";
  }

  function renderShiftHistory() {
    const s = ensureState();
    const rows = [];
    if (s.currentCashShift) {
      rows.push({
        ...s.currentCashShift,
        expectedClosingBalance: null,
        actualClosingBalance: null,
        difference: null
      });
    }
    rows.push(...s.cashShifts);

    const tbody = $("#finance-shifts");
    if (tbody) {
      tbody.innerHTML = rows.length ? rows.slice(0, 12).map(function (shift) {
        const open = String(shift.status || "").toLowerCase() === "open";
        const difference = shift.difference == null ? null : Number(shift.difference);
        const differenceText = difference == null
          ? "—"
          : (difference > 0 ? "+" : "") + api.money(difference);
        return "<tr>" +
          "<td><strong>#" + esc(shift.id) + "</strong><br><small>" + (open ? "Відкрита" : "Закрита") + "</small></td>" +
          "<td>" + esc(dateFmt.format(new Date(shift.openedAt))) + "</td>" +
          "<td>" + (shift.closedAt ? esc(dateFmt.format(new Date(shift.closedAt))) : "—") + "</td>" +
          "<td>" + esc(api.money(shift.openingBalance || 0)) + "</td>" +
          "<td>" + (shift.expectedClosingBalance == null ? "—" : esc(api.money(shift.expectedClosingBalance))) + "</td>" +
          "<td>" + (shift.actualClosingBalance == null ? "—" : esc(api.money(shift.actualClosingBalance))) + "</td>" +
          "<td><strong>" + esc(differenceText) + "</strong></td>" +
          "</tr>";
      }).join("") : '<tr><td colspan="7" class="no-data">Касових змін ще немає.</td></tr>';
    }

    if ($("#finance-shift-count")) $("#finance-shift-count").textContent = rows.length + " змін";
  }

  function renderFinance() {
    const s = ensureState();
    const summary = cashSummary();
    const shift = summary.shift;

    if ($("#finance-opening")) $("#finance-opening").textContent = api.money(summary.opening).replace("₴", "грн");
    if ($("#finance-sales")) $("#finance-sales").textContent = api.money(summary.sales).replace("₴", "грн");
    if ($("#finance-in")) $("#finance-in").textContent = api.money(summary.inAmount).replace("₴", "грн");
    if ($("#finance-out")) $("#finance-out").textContent = api.money(summary.outAmount).replace("₴", "грн");
    if ($("#finance-expected")) $("#finance-expected").textContent = api.money(summary.expected).replace("₴", "грн");
    if ($("#finance-balance-label")) $("#finance-balance-label").textContent = summary.isOpen ? "Очікується в касі" : "Останній фактичний залишок";
    if ($("#finance-shift-status")) {
      $("#finance-shift-status").textContent = summary.isOpen ? "Відкрита" : "Закрита";
      $("#finance-shift-status").classList.toggle("finance-open", summary.isOpen);
      $("#finance-shift-status").classList.toggle("finance-closed", !summary.isOpen);
    }
    if ($("#finance-shift-meta")) {
      const last = s.cashShifts[0] || null;
      $("#finance-shift-meta").textContent = shift
        ? shiftMetaText(shift)
        : (last ? "Остання зміна #" + last.id + " · закрито " + dateFmt.format(new Date(last.closedAt)) : "Немає відкритої зміни");
    }
    $(".finance-shift-card")?.classList.toggle("is-closed", !summary.isOpen);
    if ($("#finance-shift-action")) $("#finance-shift-action").textContent = summary.isOpen ? "Закрити зміну" : "Відкрити зміну";
    $$("[data-cash-action]").forEach(function (button) { button.disabled = !summary.isOpen; });

    const saleRows = shift ? s.sales.filter(function (sale) {
      return isWithinOpenShift(sale.at, shift);
    }).map(function (sale) {
      let amount = 0;
      if (sale.payment === "cash") amount = Number(sale.total || 0);
      else if (sale.payment === "mixed") amount = Number(sale.cash || 0);
      if (amount <= 0) return null;
      return {
        at: sale.at,
        direction: "in",
        label: "Продаж " + sale.id,
        amount: amount,
        supplierId: "",
        comment: sale.payment === "mixed" ? "Готівкова частина комбінованої оплати" : "Готівкова оплата"
      };
    }).filter(Boolean) : [];

    const movementRows = shift ? s.cashMovements
      .filter(function (movement) {
        return isWithinOpenShift(movement.at, shift) &&
          !(String(movement.type || "").toLowerCase().includes("sale") && movement.affectsCash !== true);
      })
      .map(function (movement) {
        return {
          at: movement.at,
          direction: cashDirection(movement),
          label: cashMovementLabel(movement),
          amount: Number(movement.amount || 0),
          supplierId: movement.supplierId || "",
          comment: movement.comment || (movement.affectsCash === true ? "" : "Демонстраційний профіль рухів")
        };
      }) : [];

    const rows = saleRows.concat(movementRows)
      .sort(function (a, b) { return String(b.at || "").localeCompare(String(a.at || "")); })
      .slice(0, 50);

    const tbody = $("#finance-movements");
    if (tbody) {
      tbody.innerHTML = rows.length ? rows.map(function (row) {
        const supplier = row.supplierId ? api.supplierById(row.supplierId) : null;
        const sign = row.direction === "out" ? "−" : row.direction === "in" ? "+" : "";
        return "<tr>" +
          "<td>" + esc(dateFmt.format(new Date(row.at))) + "</td>" +
          "<td><strong>" + esc(row.label) + "</strong></td>" +
          "<td>" + sign + esc(api.money(row.amount)) + "</td>" +
          "<td>" + esc(supplier ? supplier.name : "—") + "</td>" +
          "<td>" + esc(row.comment || "—") + "</td>" +
          "</tr>";
      }).join("") : '<tr><td colspan="5" class="no-data">' + (summary.isOpen ? "Рухів цієї зміни ще немає." : "Відкрийте касову зміну, щоб почати новий журнал.") + "</td></tr>";
    }

    if ($("#finance-movement-count")) $("#finance-movement-count").textContent = rows.length + " записів";
    renderShiftHistory();
    syncHomeCash();
  }

  function updateCloseShiftDifference() {
    const summary = cashSummary();
    const actual = Number($("#close-shift-actual")?.value);
    const difference = Number.isFinite(actual) ? api.round2(actual - summary.expected) : 0;
    if ($("#close-shift-difference")) {
      $("#close-shift-difference").textContent = (difference > 0 ? "+" : "") + api.money(difference);
    }
  }

  function openCloseShiftDialog() {
    const summary = cashSummary();
    if (!summary.isOpen) {
      api.showToast("На цій касі немає відкритої зміни.");
      return;
    }
    if ($("#close-shift-expected")) $("#close-shift-expected").textContent = api.money(summary.expected);
    if ($("#close-shift-actual")) $("#close-shift-actual").value = summary.expected.toFixed(2);
    updateCloseShiftDifference();
    const dialog = $("#close-shift-dialog");
    if (dialog && !dialog.open) dialog.showModal();
    window.setTimeout(function () {
      $("#close-shift-actual")?.focus();
      $("#close-shift-actual")?.select();
    }, 20);
  }

  function confirmCloseShift() {
    const s = ensureState();
    const shift = s.currentCashShift;
    if (!shift) {
      api.showToast("На цій касі немає відкритої зміни.");
      return;
    }

    const actual = api.round2(Number($("#close-shift-actual")?.value));
    if (!Number.isFinite(actual) || actual < 0) {
      api.showToast("Фактичний залишок не може бути від’ємним.");
      return;
    }

    const summary = cashSummary();
    const closed = {
      ...shift,
      status: "closed",
      expectedClosingBalance: summary.expected,
      actualClosingBalance: actual,
      difference: api.round2(actual - summary.expected),
      closedAt: new Date().toISOString(),
      closedByName: "Адмін"
    };

    s.cashShifts.unshift(closed);
    s.currentCashShift = null;
    api.saveState();
    $("#close-shift-dialog")?.close();
    api.renderAll();
    api.showToast("Зміну #" + closed.id + " закрито. Різниця: " + (closed.difference > 0 ? "+" : "") + api.money(closed.difference) + ".");
  }

  function suggestedOpeningBalance() {
    const last = lastClosedShift();
    return api.round2(Number(last?.actualClosingBalance ?? last?.expectedClosingBalance ?? 0));
  }

  function openOpenShiftDialog() {
    if (currentShift()) {
      api.showToast("На цій касі вже є відкрита зміна.");
      return;
    }
    const suggested = suggestedOpeningBalance();
    if ($("#open-shift-opening")) $("#open-shift-opening").value = suggested.toFixed(2);
    if ($("#open-shift-info")) {
      $("#open-shift-info").textContent = lastClosedShift()
        ? "Початковий залишок підставлено з фактичного закриття попередньої зміни. Поле можна виправити вручну."
        : "Вкажіть початковий залишок каси.";
    }
    const dialog = $("#open-shift-dialog");
    if (dialog && !dialog.open) dialog.showModal();
    window.setTimeout(function () {
      $("#open-shift-opening")?.focus();
      $("#open-shift-opening")?.select();
    }, 20);
  }

  function confirmOpenShift() {
    const s = ensureState();
    if (s.currentCashShift) {
      api.showToast("На цій касі вже є відкрита зміна.");
      return;
    }
    const opening = api.round2(Number($("#open-shift-opening")?.value));
    if (!Number.isFinite(opening) || opening < 0) {
      api.showToast("Початковий залишок не може бути від’ємним.");
      return;
    }

    const shift = {
      id: Number(s.nextCashShift++),
      status: "open",
      openingBalance: opening,
      openedAt: new Date().toISOString(),
      openedByName: "Адмін"
    };
    s.currentCashShift = shift;
    api.saveState();
    $("#open-shift-dialog")?.close();
    api.renderAll();
    api.showToast("Зміну #" + shift.id + " відкрито. Початковий залишок: " + api.money(opening) + ".");
  }

  function handleShiftAction() {
    if (currentShift()) openCloseShiftDialog();
    else openOpenShiftDialog();
  }

  function openCashAction(mode) {
    cashActionMode = mode === "out" ? "out" : "in";
    const s = ensureState();
    const summary = cashSummary();

    if (!summary.isOpen) {
      api.showToast("Спочатку відкрийте касову зміну.");
      return;
    }

    if ($("#cash-action-title")) $("#cash-action-title").textContent = cashActionMode === "in" ? "Внести кошти" : "Вилучити кошти";
    if ($("#cash-action-info")) {
      $("#cash-action-info").textContent = cashActionMode === "in"
        ? "Внесення збільшить очікуваний залишок каси."
        : "Доступно в касі: " + api.money(summary.expected) + ".";
    }
    if ($("#cash-action-amount")) $("#cash-action-amount").value = "";
    if ($("#cash-action-comment")) $("#cash-action-comment").value = "";
    if ($("#cash-action-supplier")) {
      $("#cash-action-supplier").innerHTML = '<option value="">— без постачальника —</option>' +
        s.suppliers.map(function (supplier) {
          return '<option value="' + esc(supplier.id) + '">' + esc(supplier.name) + "</option>";
        }).join("");
    }
    if ($("#cash-supplier-row")) $("#cash-supplier-row").hidden = cashActionMode !== "out";

    const dialog = $("#cash-action-dialog");
    if (dialog && !dialog.open) dialog.showModal();
    $("#cash-action-amount") && $("#cash-action-amount").focus();
  }

  function confirmCashAction() {
    const s = ensureState();
    const amount = api.round2(Number($("#cash-action-amount") && $("#cash-action-amount").value) || 0);
    if (amount <= 0) {
      api.showToast("Вкажіть суму більше нуля.");
      return;
    }

    const summary = cashSummary();
    if (cashActionMode === "out" && amount > summary.expected) {
      api.showToast("У касі недостатньо коштів для такого вилучення.");
      return;
    }

    s.cashMovements.unshift({
      id: "CM-D-" + Date.now(),
      type: cashActionMode === "in" ? "CashIn" : "CashOut",
      direction: cashActionMode,
      affectsCash: true,
      amount: amount,
      at: new Date().toISOString(),
      supplierId: cashActionMode === "out" ? ($("#cash-action-supplier") ? $("#cash-action-supplier").value : "") : "",
      comment: ($("#cash-action-comment") ? $("#cash-action-comment").value.trim() : ""),
      user: "Адмін"
    });

    api.saveState();
    $("#cash-action-dialog") && $("#cash-action-dialog").close();
    api.renderAll();
    api.showToast((cashActionMode === "in" ? "Внесено " : "Вилучено ") + api.money(amount) + ".");
  }

  function showWithdrawals() {
    const s = ensureState();
    const rows = s.cashMovements
      .filter(function (movement) {
        return movement.affectsCash === true && cashDirection(movement) === "out" && sameLocalDay(movement.at);
      })
      .sort(function (a, b) { return String(b.at || "").localeCompare(String(a.at || "")); });

    const total = api.round2(rows.reduce(function (sum, movement) { return sum + Number(movement.amount || 0); }, 0));
    if ($("#withdrawals-date")) $("#withdrawals-date").textContent = new Intl.DateTimeFormat("uk-UA", { dateStyle: "long" }).format(new Date());
    if ($("#withdrawals-total")) $("#withdrawals-total").textContent = api.money(total).replace("₴", "грн");

    const tbody = $("#withdrawals-table");
    if (tbody) {
      tbody.innerHTML = rows.length ? rows.map(function (movement) {
        const supplier = movement.supplierId ? api.supplierById(movement.supplierId) : null;
        return "<tr>" +
          "<td>" + esc(dateFmt.format(new Date(movement.at))) + "</td>" +
          "<td>" + esc(api.money(movement.amount)) + "</td>" +
          "<td>" + esc(supplier ? supplier.name : "—") + "</td>" +
          "<td>" + esc(movement.comment || "—") + "</td>" +
          "<td>" + esc(movement.user || "Адмін") + "</td>" +
          "</tr>";
      }).join("") : '<tr><td colspan="5" class="no-data">Сьогодні вилучень ще не було.</td></tr>';
    }

    const dialog = $("#withdrawals-dialog");
    if (dialog && !dialog.open) dialog.showModal();
  }

  function recordDebtRepayment(customer, amount) {
    if (!customer || Number(amount) <= 0) return;
    const s = ensureState();
    s.cashMovements.unshift({
      id: "CM-DEBT-" + Date.now(),
      type: "DebtRepayment",
      direction: "in",
      affectsCash: true,
      amount: api.round2(amount),
      at: new Date().toISOString(),
      customerId: customer.id,
      customerName: customer.name,
      comment: "Повернення боргу · " + customer.name,
      user: "Адмін"
    });
  }

  function renderWriteoffDraft() {
    const tbody = $("#writeoff-draft-lines");
    if (!tbody) return;

    tbody.innerHTML = writeoffDraft.length ? writeoffDraft.map(function (line, index) {
      const product = api.productById(line.productId);
      if (!product) return "";
      return "<tr>" +
        "<td>" + esc(api.productCode(product)) + "</td>" +
        "<td><strong>" + esc(product.name) + "</strong></td>" +
        "<td>" + esc(Number(line.qty).toLocaleString("uk-UA")) + "</td>" +
        "<td>" + esc(product.unit) + "</td>" +
        "<td>" + esc(api.money(product.cost)) + "</td>" +
        "<td>" + esc(api.money(api.round2(Number(line.qty) * Number(product.cost)))) + "</td>" +
        '<td><button class="cart-line-remove" type="button" data-remove-writeoff="' + index + '" aria-label="Видалити позицію">×</button></td>' +
        "</tr>";
    }).join("") : '<tr><td colspan="7" class="no-data">Додайте хоча б одну позицію.</td></tr>';

    $$("[data-remove-writeoff]", tbody).forEach(function (button) {
      button.addEventListener("click", function () {
        writeoffDraft.splice(Number(button.dataset.removeWriteoff), 1);
        renderWriteoffDraft();
      });
    });
  }

  function renderWriteoffs() {
    const s = ensureState();
    const tbody = $("#writeoffs-table");
    if (!tbody) return;

    tbody.innerHTML = s.writeoffs.length ? s.writeoffs.slice(0, 50).map(function (doc) {
      return "<tr>" +
        "<td><strong>" + esc(doc.id) + "</strong></td>" +
        "<td>" + esc(dateFmt.format(new Date(doc.at))) + "</td>" +
        "<td>" + esc(doc.reason || "Інше") + "</td>" +
        "<td>" + esc(String((doc.lines || []).length)) + "</td>" +
        "<td>" + esc(api.money(doc.totalCost || 0)) + "</td>" +
        "<td>" + esc(doc.comment || "—") + "</td>" +
        "<td>" + esc(doc.user || "Адмін") + "</td>" +
        "</tr>";
    }).join("") : '<tr><td colspan="7" class="no-data">Документів списання ще немає.</td></tr>';

    if ($("#writeoff-count")) $("#writeoff-count").textContent = s.writeoffs.length + " документів";
  }

  function openWriteoffDialog() {
    const s = ensureState();
    writeoffDraft = [];
    if ($("#writeoff-comment")) $("#writeoff-comment").value = "";
    if ($("#writeoff-qty")) $("#writeoff-qty").value = "1";
    if ($("#writeoff-product")) {
      $("#writeoff-product").innerHTML = s.products
        .filter(function (product) { return Number(product.stock) > -50; })
        .map(function (product) {
          return '<option value="' + esc(product.id) + '">' + esc(api.productCode(product) + " · " + product.name + " · " + product.stock + " " + product.unit) + "</option>";
        }).join("");
    }
    renderWriteoffDraft();
    const dialog = $("#writeoff-dialog");
    if (dialog && !dialog.open) dialog.showModal();
  }

  function addWriteoffLine() {
    const productId = $("#writeoff-product") ? $("#writeoff-product").value : "";
    const qty = api.round2(Number($("#writeoff-qty") && $("#writeoff-qty").value) || 0);
    const product = api.productById(productId);
    if (!product || qty <= 0) {
      api.showToast("Оберіть товар і вкажіть коректну кількість.");
      return;
    }

    const existing = writeoffDraft.find(function (line) { return line.productId === productId; });
    if (existing) existing.qty = api.round2(Number(existing.qty) + qty);
    else writeoffDraft.push({ productId: productId, qty: qty });

    if ($("#writeoff-qty")) $("#writeoff-qty").value = "1";
    renderWriteoffDraft();
  }

  function saveWriteoff() {
    const s = ensureState();
    if (!writeoffDraft.length) {
      api.showToast("Додайте хоча б одну позицію списання.");
      return;
    }

    const lines = writeoffDraft.map(function (line) {
      const product = api.productById(line.productId);
      return {
        productId: line.productId,
        qty: api.round2(line.qty),
        cost: Number(product && product.cost || 0)
      };
    });

    lines.forEach(function (line) {
      const product = api.productById(line.productId);
      if (product) product.stock = api.round2(Number(product.stock || 0) - Number(line.qty || 0));
    });

    const doc = {
      id: "WO-" + String(s.nextWriteoff++).padStart(6, "0"),
      at: new Date().toISOString(),
      reason: $("#writeoff-reason") ? $("#writeoff-reason").value : "Інше",
      comment: $("#writeoff-comment") ? $("#writeoff-comment").value.trim() : "",
      user: "Адмін",
      lines: lines,
      totalCost: api.round2(lines.reduce(function (sum, line) { return sum + Number(line.qty) * Number(line.cost); }, 0))
    };

    s.writeoffs.unshift(doc);
    writeoffDraft = [];
    api.saveState();
    $("#writeoff-dialog") && $("#writeoff-dialog").close();
    api.renderAll();
    api.showToast(doc.id + " збережено. Залишки оновлено.");
  }

  function inventoryById(id) {
    return ensureState().inventories.find(function (inventory) { return inventory.id === id; }) || null;
  }

  function inventoryStats(inventory) {
    const items = Array.isArray(inventory && inventory.items) ? inventory.items : [];
    const counted = items.filter(function (item) { return item.actual !== null && item.actual !== undefined; });
    const differences = counted.filter(function (item) {
      return Math.abs(Number(item.actual) - Number(item.expected)) > 0.0001;
    });
    return { total: items.length, counted: counted.length, differences: differences.length };
  }

  function renderInventories() {
    const s = ensureState();
    if (selectedInventoryId && !inventoryById(selectedInventoryId)) selectedInventoryId = null;
    if (!selectedInventoryId && s.inventories.length) selectedInventoryId = s.inventories[0].id;

    const tbody = $("#inventories-table");
    if (tbody) {
      tbody.innerHTML = s.inventories.length ? s.inventories.map(function (inventory) {
        const stats = inventoryStats(inventory);
        const selected = inventory.id === selectedInventoryId ? " is-selected" : "";
        return '<tr class="inventory-list-row' + selected + '" data-inventory-id="' + esc(inventory.id) + '">' +
          "<td><strong>" + esc(inventory.id) + "</strong></td>" +
          "<td>" + esc(inventory.status === "posted" ? "Проведено" : "Чернетка") + "</td>" +
          "<td>" + esc(dateFmt.format(new Date(inventory.startedAt))) + "</td>" +
          "<td>" + esc(inventory.warehouseName || "Основний склад") + "</td>" +
          "<td>" + stats.counted + "</td>" +
          "<td>" + stats.total + "</td>" +
          "<td>" + stats.differences + "</td>" +
          "<td>" + esc(inventory.comment || "—") + "</td>" +
          "<td>" + esc(inventory.user || "Адмін") + "</td>" +
          "</tr>";
      }).join("") : '<tr><td colspan="9" class="no-data">Інвентаризацій ще немає.</td></tr>';

      $$("[data-inventory-id]", tbody).forEach(function (row) {
        row.addEventListener("click", function () {
          selectedInventoryId = row.dataset.inventoryId;
          renderInventories();
        });
        row.addEventListener("dblclick", function () {
          selectedInventoryId = row.dataset.inventoryId;
          openInventory(selectedInventoryId);
        });
      });
    }

    if ($("#inventory-count")) $("#inventory-count").textContent = s.inventories.length + " інвентаризацій";
    if ($("#open-selected-inventory")) $("#open-selected-inventory").disabled = !selectedInventoryId;
  }

  function createInventory() {
    const s = ensureState();
    const activeProducts = s.products.filter(function (product) { return Number(product.stock) > -50; });
    if (!activeProducts.length) {
      api.showToast("Немає активних товарів для інвентаризації.");
      return;
    }

    const inventory = {
      id: "INV-" + String(s.nextInventory++).padStart(6, "0"),
      status: "draft",
      startedAt: new Date().toISOString(),
      warehouseId: $("#inventory-warehouse") ? $("#inventory-warehouse").value : "1",
      warehouseName: "Основний склад",
      comment: $("#inventory-comment") ? $("#inventory-comment").value.trim() : "",
      user: "Адмін",
      items: activeProducts.map(function (product) {
        return {
          productId: product.id,
          expected: api.round2(Number(product.stock || 0)),
          actual: null
        };
      })
    };

    s.inventories.unshift(inventory);
    selectedInventoryId = inventory.id;
    activeInventoryId = inventory.id;
    api.saveState();
    $("#new-inventory-dialog") && $("#new-inventory-dialog").close();
    renderInventories();
    openInventory(inventory.id);
    api.showToast(inventory.id + " створено. Snapshot залишків зафіксовано.");
  }

  function filteredInventoryItems(inventory) {
    const query = ($("#inventory-filter") ? $("#inventory-filter").value : "").trim().toLowerCase();
    const items = Array.isArray(inventory.items) ? inventory.items : [];
    if (!query) return items;
    return items.filter(function (item) {
      const product = api.productById(item.productId);
      if (!product) return false;
      return String(product.name || "").toLowerCase().includes(query) ||
        String(product.barcode || "").toLowerCase().includes(query) ||
        String(api.productCode(product) || "").toLowerCase().includes(query);
    });
  }

  function saveInventoryComment(inventory) {
    if (!inventory) return;
    inventory.comment = $("#inventory-count-comment") ? $("#inventory-count-comment").value.trim() : inventory.comment || "";
  }

  function renderInventoryDialog() {
    const inventory = inventoryById(activeInventoryId);
    if (!inventory) return;
    const posted = inventory.status === "posted";
    const stats = inventoryStats(inventory);

    if ($("#inventory-dialog-title")) $("#inventory-dialog-title").textContent = inventory.id;
    if ($("#inventory-dialog-meta")) $("#inventory-dialog-meta").textContent = (inventory.warehouseName || "Основний склад") + " · початок " + dateFmt.format(new Date(inventory.startedAt));
    if ($("#inventory-status-badge")) $("#inventory-status-badge").textContent = posted ? "Проведено" : "Чернетка";
    if ($("#inventory-progress")) $("#inventory-progress").textContent = "Пораховано " + stats.counted + " з " + stats.total;
    if ($("#inventory-difference-summary")) $("#inventory-difference-summary").textContent = "Розбіжностей: " + stats.differences;
    if ($("#inventory-count-comment")) $("#inventory-count-comment").value = inventory.comment || "";

    ["#inventory-scan", "#inventory-count-scan", "#inventory-search-product"].forEach(function (selector) {
      if ($(selector)) $(selector).disabled = posted;
    });
    if ($("#inventory-post")) $("#inventory-post").disabled = posted;
    if ($("#inventory-save-close")) $("#inventory-save-close").textContent = posted ? "Закрити" : "Зберегти і закрити";

    const tbody = $("#inventory-items");
    const items = filteredInventoryItems(inventory);
    if (tbody) {
      tbody.innerHTML = items.length ? items.map(function (item) {
        const product = api.productById(item.productId);
        if (!product) return "";
        const counted = item.actual !== null && item.actual !== undefined;
        const difference = counted ? api.round2(Number(item.actual) - Number(item.expected)) : null;
        const diffText = difference === null ? "—" : (difference > 0 ? "+" : "") + Number(difference).toLocaleString("uk-UA");
        return "<tr>" +
          "<td>" + esc(api.productCode(product)) + "</td>" +
          "<td>" + esc(product.barcode || "") + "</td>" +
          "<td><strong>" + esc(product.name) + "</strong></td>" +
          "<td>" + esc(product.unit || "шт") + "</td>" +
          "<td>" + esc(Number(item.expected).toLocaleString("uk-UA")) + "</td>" +
          '<td><input class="inventory-actual-input" type="number" min="0" step="0.001" data-inventory-actual="' + esc(item.productId) + '" value="' + (counted ? esc(String(item.actual)) : "") + '"' + (posted ? " disabled" : "") + "/></td>" +
          "<td><strong>" + esc(diffText) + "</strong></td>" +
          "<td>" + (counted ? "Так" : "—") + "</td>" +
          "</tr>";
      }).join("") : '<tr><td colspan="8" class="no-data">За фільтром нічого не знайдено.</td></tr>';

      $$("[data-inventory-actual]", tbody).forEach(function (input) {
        input.addEventListener("change", function () {
          if (posted) return;
          const item = inventory.items.find(function (candidate) { return candidate.productId === input.dataset.inventoryActual; });
          if (!item) return;
          const raw = input.value.trim();
          if (raw === "") item.actual = null;
          else {
            const value = Number(raw);
            if (!Number.isFinite(value) || value < 0) {
              api.showToast("Фактична кількість не може бути від’ємною.");
              renderInventoryDialog();
              return;
            }
            item.actual = api.round2(value);
          }
          saveInventoryComment(inventory);
          api.saveState();
          renderInventoryDialog();
          renderInventories();
        });
      });
    }
  }

  function openInventory(id) {
    const inventory = inventoryById(id);
    if (!inventory) {
      api.showToast("Інвентаризацію не знайдено.");
      return;
    }
    selectedInventoryId = inventory.id;
    activeInventoryId = inventory.id;
    if ($("#inventory-filter")) $("#inventory-filter").value = "";
    if ($("#inventory-scan")) $("#inventory-scan").value = "";
    renderInventoryDialog();
    const dialog = $("#inventory-count-dialog");
    if (dialog && !dialog.open) dialog.showModal();
    window.setTimeout(function () {
      if (inventory.status === "draft" && $("#inventory-scan")) $("#inventory-scan").focus();
    }, 20);
  }

  function countInventoryByCode() {
    const inventory = inventoryById(activeInventoryId);
    if (!inventory || inventory.status !== "draft") return;
    const value = ($("#inventory-scan") ? $("#inventory-scan").value : "").trim().toLowerCase();
    if (!value) {
      api.showToast("Введіть штрих-код або код товару.");
      return;
    }

    const product = ensureState().products.find(function (candidate) {
      return String(candidate.barcode || "").toLowerCase() === value ||
        String(api.productCode(candidate) || "").toLowerCase() === value;
    });
    if (!product) {
      api.showToast("Товар за цим кодом не знайдено.");
      return;
    }

    const item = inventory.items.find(function (candidate) { return candidate.productId === product.id; });
    if (!item) {
      api.showToast("Цього товару немає у snapshot інвентаризації.");
      return;
    }

    item.actual = api.round2(Number(item.actual == null ? 0 : item.actual) + 1);
    saveInventoryComment(inventory);
    api.saveState();
    if ($("#inventory-scan")) $("#inventory-scan").value = "";
    renderInventoryDialog();
    renderInventories();
    window.setTimeout(function () { $("#inventory-scan") && $("#inventory-scan").focus(); }, 10);
  }

  function focusInventorySearch() {
    const inventory = inventoryById(activeInventoryId);
    if (!inventory || inventory.status !== "draft") return false;
    const scanValue = ($("#inventory-scan") ? $("#inventory-scan").value : "").trim();
    if (scanValue && $("#inventory-filter")) $("#inventory-filter").value = scanValue;
    renderInventoryDialog();
    window.setTimeout(function () {
      if ($("#inventory-filter")) {
        $("#inventory-filter").focus();
        $("#inventory-filter").select();
      }
    }, 10);
    return true;
  }

  function closeInventory(save) {
    const inventory = inventoryById(activeInventoryId);
    if (inventory && save && inventory.status === "draft") {
      saveInventoryComment(inventory);
      api.saveState();
    }
    $("#inventory-count-dialog") && $("#inventory-count-dialog").close();
    renderInventories();
  }

  function postInventory() {
    const inventory = inventoryById(activeInventoryId);
    if (!inventory || inventory.status !== "draft") return;
    saveInventoryComment(inventory);
    const stats = inventoryStats(inventory);
    if (!stats.counted) {
      api.showToast("Порахуйте хоча б один товар.");
      return;
    }

    if (stats.counted < stats.total) {
      const proceed = window.confirm("Пораховано не всі товари. Непораховані позиції залишаться без змін. Провести інвентаризацію?");
      if (!proceed) return;
    }

    inventory.items.forEach(function (item) {
      if (item.actual === null || item.actual === undefined) return;
      const product = api.productById(item.productId);
      if (product) product.stock = api.round2(Number(item.actual));
    });

    inventory.status = "posted";
    inventory.postedAt = new Date().toISOString();
    inventory.postedCount = stats.counted;
    api.saveState();
    $("#inventory-count-dialog") && $("#inventory-count-dialog").close();
    api.renderAll();
    api.showToast(inventory.id + " проведено. Залишки скориговано.");
  }

  function setStockTab(name) {
    $$("[data-stock-tab]").forEach(function (button) {
      button.classList.toggle("is-active", button.dataset.stockTab === name);
    });
    $$("[data-stock-panel]").forEach(function (panel) {
      panel.classList.toggle("is-active", panel.dataset.stockPanel === name);
    });
  }

  function renderStockOps() {
    ensureState();
    renderWriteoffs();
    renderInventories();
  }

  function renderView(view) {
    if (view === "finance") renderFinance();
    if (view === "stockops") renderStockOps();
  }

  function renderAll() {
    renderStockOps();
    renderFinance();
    syncHomeCash();
  }

  function handleF7() {
    const dialog = $("#inventory-count-dialog");
    if (dialog && dialog.open) return focusInventorySearch();
    return false;
  }

  function initEvents() {
    $$("[data-stock-tab]").forEach(function (button) {
      button.addEventListener("click", function () { setStockTab(button.dataset.stockTab); });
    });

    $("#new-writeoff") && $("#new-writeoff").addEventListener("click", openWriteoffDialog);
    $("#add-writeoff-line") && $("#add-writeoff-line").addEventListener("click", addWriteoffLine);
    $("#save-writeoff") && $("#save-writeoff").addEventListener("click", saveWriteoff);
    $("#refresh-writeoffs") && $("#refresh-writeoffs").addEventListener("click", function () {
      renderWriteoffs();
      api.showToast("Список списань оновлено.");
    });

    $("#new-inventory") && $("#new-inventory").addEventListener("click", function () {
      if ($("#inventory-comment")) $("#inventory-comment").value = "";
      const dialog = $("#new-inventory-dialog");
      if (dialog && !dialog.open) dialog.showModal();
    });
    $("#create-inventory") && $("#create-inventory").addEventListener("click", createInventory);
    $("#refresh-inventories") && $("#refresh-inventories").addEventListener("click", function () {
      renderInventories();
      api.showToast("Список інвентаризацій оновлено.");
    });
    $("#open-selected-inventory") && $("#open-selected-inventory").addEventListener("click", function () {
      if (selectedInventoryId) openInventory(selectedInventoryId);
    });
    $("#inventory-count-scan") && $("#inventory-count-scan").addEventListener("click", countInventoryByCode);
    $("#inventory-scan") && $("#inventory-scan").addEventListener("keydown", function (event) {
      if (event.key !== "Enter") return;
      event.preventDefault();
      countInventoryByCode();
    });
    $("#inventory-filter") && $("#inventory-filter").addEventListener("input", renderInventoryDialog);
    $("#inventory-search-product") && $("#inventory-search-product").addEventListener("click", focusInventorySearch);
    $("#inventory-save-close") && $("#inventory-save-close").addEventListener("click", function () { closeInventory(true); });
    $("#inventory-close-x") && $("#inventory-close-x").addEventListener("click", function () { closeInventory(true); });
    $("#inventory-post") && $("#inventory-post").addEventListener("click", postInventory);

    $$("[data-cash-action]").forEach(function (button) {
      button.addEventListener("click", function () { openCashAction(button.dataset.cashAction); });
    });
    $("#confirm-cash-action") && $("#confirm-cash-action").addEventListener("click", confirmCashAction);
    $("#show-withdrawals") && $("#show-withdrawals").addEventListener("click", showWithdrawals);
    $("#home-show-withdrawals") && $("#home-show-withdrawals").addEventListener("click", showWithdrawals);
    $("#home-shift-action") && $("#home-shift-action").addEventListener("click", handleShiftAction);
    $("#finance-shift-action") && $("#finance-shift-action").addEventListener("click", handleShiftAction);
    $("#close-shift-actual") && $("#close-shift-actual").addEventListener("input", updateCloseShiftDifference);
    $("#confirm-close-shift") && $("#confirm-close-shift").addEventListener("click", confirmCloseShift);
    $("#confirm-open-shift") && $("#confirm-open-shift").addEventListener("click", confirmOpenShift);
  }

  window.OUTPOST_DEMO_MODULES = {
    renderView: renderView,
    renderAll: renderAll,
    syncHomeCash: syncHomeCash,
    recordDebtRepayment: recordDebtRepayment,
    getCashSummary: cashSummary,
    handleF7: handleF7
  };

  ensureState();
  initEvents();
  renderAll();
})();