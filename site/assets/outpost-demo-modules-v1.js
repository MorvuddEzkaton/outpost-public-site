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
    window.OUTPOST_DEMO_DASHBOARD?.render();
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

// Browser-local counterpart of the desktop Modern command center.
(() => {
  "use strict";
  const api = window.OUTPOST_DEMO_API;
  const root = document.querySelector("#command-center");
  if (!api || !root) return;
  const KEY = "outpost_online_demo_dashboard_v1";
  const $ = selector => document.querySelector(selector);
  const all = selector => Array.from(document.querySelectorAll(selector));
  const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
  const money = value => api.money(api.round2(number(value))).replace("₴", "грн");
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  const date = value => { const d = new Date(value); return Number.isFinite(d.getTime()) ? d : null; };
  const dayKey = d => d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate();
  const METRICS = [
    ["CashBalance","Сума в касі","₴","success","finance"],
    ["Revenue","Виручка сьогодні","↗","accent","history"],
    ["Receipts","Чеків","▤","accent","history"],
    ["Cash","Готівкові продажі","₴","success","finance"],
    ["Card","Продажі карткою","▣","accent","history"],
    ["Returns","Повернення сьогодні","↶","danger","history"],
    ["StockValue","Вартість залишку","▦","accent","products"],
    ["LowStock","Скоро закінчиться","!","warning","products"],
    ["NegativeStock","Продажі понад залишок","↘","danger",null],
    ["SupplierDebt","Борги постачальникам","♙","warning",null],
    ["FiscalProblems","Фіскальні проблеми","✓","success",null],
    ["AverageReceipt","Середній чек","≈","accent","history"],
    ["OtherPayments","Інші оплати","▣","muted","history"],
    ["PendingDocuments","Фіскальна черга","▤","warning",null]
  ];
  const SECTIONS = [["Chart","Графік продажів"],["Attention","Потребує уваги"],["LowStockTable","Список товарів, що закінчуються"],["SupplierDebtTable","Список боргів постачальникам"]];
  const defaults = () => ({metrics:METRICS.map(x=>x[0]),sections:SECTIONS.map(x=>x[0]),hiddenMetrics:["AverageReceipt","OtherPayments","PendingDocuments"],hiddenSections:[],period:7,chart:"bars"});
  function normalize(raw) {
    const value = raw && typeof raw === "object" ? raw : {};
    const ordered = (items, allowed) => [...new Set([...(Array.isArray(items) ? items : []),...allowed])].filter(x=>allowed.includes(x));
    const ids = METRICS.map(x=>x[0]), sections = SECTIONS.map(x=>x[0]);
    return {metrics:ordered(value.metrics,ids),sections:ordered(value.sections,sections),
      hiddenMetrics:(Array.isArray(value.hiddenMetrics)?value.hiddenMetrics:defaults().hiddenMetrics).filter(x=>ids.includes(x)),
      hiddenSections:(Array.isArray(value.hiddenSections)?value.hiddenSections:[]).filter(x=>sections.includes(x)),
      period:[1,7,14,30].includes(value.period)?value.period:7,chart:value.chart==="line"?"line":"bars"};
  }
  let prefs;
  try { prefs = normalize(JSON.parse(localStorage.getItem(KEY) || "null")); } catch { prefs = defaults(); }
  let draft = null;
  let settingsTab = "metrics";
  const copy = value => JSON.parse(JSON.stringify(value));
  function persist(value) {
    const next = normalize(value);
    try { localStorage.setItem(KEY,JSON.stringify(next)); prefs=next;return true; }
    catch { api.showToast("Не вдалося зберегти вигляд головної у браузері.");return false; }
  }
  function snapshot() {
    const state = api.getState(), now = new Date(), today = dayKey(now);
    const yesterdayAt = new Date(now); yesterdayAt.setDate(now.getDate()-1);
    const previousKey = dayKey(yesterdayAt);
    const daily = new Map(), hours = new Map();
    const empty = () => ({revenue:0,cash:0,card:0,other:0,receipts:0,returns:0});
    const bucket = (map,key) => {if(!map.has(key))map.set(key,empty());return map.get(key);};
    const previous = empty();
    for (const sale of state.sales || []) {
      const at = date(sale.at); if(!at)continue;
      const total = number(sale.total);
      const cash = sale.payment==="cash"?total:sale.payment==="mixed"?number(sale.cash):0;
      const card = sale.payment==="card"?total:sale.payment==="mixed"?number(sale.card):0;
      const parts = {revenue:total,cash,card,other:total-cash-card,receipts:1};
      const targets = [bucket(daily,dayKey(at))];
      if(dayKey(at)===today)targets.push(bucket(hours,at.getHours()));
      if(dayKey(at)===previousKey && at<=yesterdayAt)targets.push(previous);
      for(const target of targets)for(const key of Object.keys(parts))target[key]+=parts[key];
    }
    for (const record of state.returns || []) {
      const at = date(record.at);if(!at)continue;
      const targets=[bucket(daily,dayKey(at))];
      if(dayKey(at)===today)targets.push(bucket(hours,at.getHours()));
      if(dayKey(at)===previousKey && at<=yesterdayAt)targets.push(previous);
      for(const target of targets){
        target.revenue-=number(record.total);target.returns+=number(record.total);
        for(const payment of record.payments || [])target[payment.type==="cash"?"cash":payment.type==="card"?"card":"other"]-=number(payment.amount);
      }
    }
    const products=Array.isArray(state.products)?state.products:[];
    const low=products.filter(p=>number(p.stock)<5).sort((a,b)=>number(a.stock)-number(b.stock));
    const suppliers=(state.suppliers || []).filter(s=>Number.isFinite(Number(s.debt)) && s.debt!=null);
    const debts=suppliers.filter(s=>number(s.debt)>0);
    const cash=window.OUTPOST_DEMO_MODULES.getCashSummary();
    return {state,now,today,previous,daily,hours,current:daily.get(today)||empty(),cash,low,debts,supplierData:suppliers.length>0,
      stockValue:products.reduce((sum,p)=>sum+number(p.cost)*number(p.stock),0)};
  }
  function delta(value, previous) {
    const diff=api.round2(value-previous),sign=diff>0?"+":"";
    return {text:sign+diff.toLocaleString("uk-UA",{minimumFractionDigits:2,maximumFractionDigits:2})+(previous===0?" · учора 0":" ("+sign+(diff/Math.abs(previous)*100).toLocaleString("uk-UA",{maximumFractionDigits:1})+"%)"),tone:diff>0?"is-positive":diff<0?"is-negative":"is-muted"};
  }
  function values(s) {
    const c=s.current, debt=s.debts.reduce((sum,row)=>sum+number(row.debt),0);
    const unavailable=["—","Доступно у Windows-версії","is-muted"];
    const comparison=key=>{const d=delta(c[key],s.previous[key]);return [key==="receipts"?String(c[key]):money(c[key]),d.text,d.tone];};
    return {
      CashBalance:[money(s.cash.expected),"За журналом касових рухів · каса №1","is-positive","home-cash"],
      Revenue:[...comparison("revenue"),"home-sales"],Receipts:[...comparison("receipts"),"home-checks"],
      Cash:[...comparison("cash"),"home-cash-sales"],Card:[...comparison("card"),"home-card-sales"],
      Returns:[money(c.returns),"Проведені повернення товарів","is-negative","home-returns"],
      StockValue:[money(s.stockValue),"За собівартістю · основний склад","","home-stock-value"],
      LowStock:[s.low.length+" товарів","Потребують перевірки залишку","is-muted","home-low-stock"],
      NegativeStock:unavailable,SupplierDebt:s.supplierData?[money(debt),s.debts.length+" постачальників","is-muted"]:["—","Немає даних про оплати","is-muted"],
      FiscalProblems:["—","Пристрої не підключені · демо","is-muted"],
      AverageReceipt:[money(c.receipts?(c.revenue+c.returns)/c.receipts:0),"Продажі до повернень / кількість чеків",""],
      OtherPayments:[money(c.other),"Інші способи оплати сьогодні","is-muted"],PendingDocuments:["—","Фіскалізація не підключена","is-muted"]
    };
  }
  function info(key) {
    const messages={fiscal:"У веб-демо фіскальні пристрої не підключені. Фіскалізація й перевірка черги доступні у Windows-версії.",cloud:"У веб-демо Cloud не підключено. Показники обчислюються з тестових даних у цьому браузері.",backup:"Демо-дані зберігаються у цьому браузері. Автоматичні резервні копії магазину налаштовуються у Windows-версії.",supplier:"Облік оплат і боргів постачальникам доступний у Windows-версії. У цьому демо даних про такі оплати немає.",negative:"Журнал продажів понад залишок доступний у Windows-версії. У веб-демо цей журнал не ведеться."};
    api.showToast(messages[key]||messages.fiscal);
  }
  function renderMetrics(s) {
    const data=values(s);
    $("#dashboard-kpis").innerHTML=prefs.metrics.filter(id=>!prefs.hiddenMetrics.includes(id)).map(id=>{
      const metric=METRICS.find(m=>m[0]===id),value=data[id],route=metric[4];
      const target=route?'data-dashboard-view="'+route+'"':'data-dashboard-info="'+(id==="SupplierDebt"?"supplier":id==="NegativeStock"?"negative":"fiscal")+'"';
      const seriesKey={Revenue:'revenue',Receipts:'receipts',Cash:'cash',Card:'card'}[id];
      let spark='';
      if(seriesKey){
        const series=Array.from({length:7},(_,i)=>{const at=new Date(s.now);at.setDate(at.getDate()+i-6);return number(s.daily.get(dayKey(at))?.[seriesKey]);});
        const min=Math.min(0,...series),range=Math.max(1,Math.max(...series)-min);
        spark='<svg class="dashboard-spark" viewBox="0 0 160 19" preserveAspectRatio="none" aria-hidden="true"><polyline points="'+series.map((v,i)=>(i*156/6).toFixed(2)+','+(17-(v-min)/range*15).toFixed(2)).join(' ')+'"/></svg>';
      }
      return '<button class="dashboard-kpi" type="button" data-dashboard-metric="'+id+'" data-tone="'+metric[3]+'" '+target+' title="'+escape(metric[1]+": "+value[0]+" · "+value[1])+'"><span class="dashboard-kpi-icon" aria-hidden="true">'+metric[2]+'</span><span class="dashboard-kpi-body"><span class="dashboard-kpi-label">'+metric[1]+'</span><strong'+(value[3]?' id="'+value[3]+'"':'')+'>'+escape(value[0])+'</strong><small class="'+(value[2]||'')+'">'+escape(value[1])+'</small>'+spark+'</span></button>';
    }).join("");
  }
  function renderChart(s) {
    const points=[];
    if(prefs.period===1){
      const hours=Array.from(s.hours.keys()),first=Math.min(8,...hours),last=Math.max(first+1,s.now.getHours(),...hours);
      for(let h=first;h<=last;h++)points.push({label:String(h).padStart(2,"0")+":00",...(s.hours.get(h)||{cash:0,card:0,other:0,revenue:0})});
    }else for(let i=1-prefs.period;i<=0;i++){
      const at=new Date(s.now);at.setDate(at.getDate()+i);
      points.push({label:at.toLocaleDateString("uk-UA",{day:"2-digit",month:"2-digit"}),...(s.daily.get(dayKey(at))||{cash:0,card:0,other:0,revenue:0})});
    }
    const line=prefs.chart==="line",height=111,left=48,width=582;
    const maximum=Math.max(1,...points.map(p=>line?p.revenue:Math.max(0,p.cash)+Math.max(0,p.card)+Math.max(0,p.other)));
    const minimum=line?Math.min(0,...points.map(p=>p.revenue)):0,range=maximum-minimum;
    let svg='';
    for(let tick=0;tick<=3;tick++){
      const y=10+tick*height/3;
      svg+='<line class="dashboard-chart-grid" x1="'+left+'" x2="635" y1="'+y+'" y2="'+y+'"/><text class="dashboard-chart-label" x="0" y="'+(y+4)+'">'+Math.round(maximum-tick*range/3)+'</text>';
    }
    const path=[];points.forEach((point,index)=>{
      const slot=width/points.length,x=left+slot*(index+.5),y=10+height-(point.revenue-minimum)/range*height;
      if(line){path.push(x.toFixed(2)+','+y.toFixed(2));}
      else{let bottom=10+height;for(const key of ['cash','card','other']){
        const h=Math.max(0,number(point[key]))/maximum*height;if(h<=0)continue;bottom-=h;
        svg+='<rect class="chart-'+key+'" x="'+(x-slot*.29).toFixed(2)+'" y="'+bottom.toFixed(2)+'" width="'+(slot*.58).toFixed(2)+'" height="'+h.toFixed(2)+'"><title>'+escape(point.label+' · '+money(point[key]))+'</title></rect>';
      }}
      if(index%Math.max(1,Math.ceil(points.length/10))===0)svg+='<text class="dashboard-chart-label" text-anchor="middle" x="'+x.toFixed(2)+'" y="144">'+point.label+'</text>';
    });
    if(line)svg+='<polyline class="dashboard-chart-line" points="'+path.join(' ')+'"/>';
    $("#dashboard-chart").innerHTML='<svg viewBox="0 0 640 150" role="img" aria-label="'+(line?'Чиста виручка':'Оплати продажів')+' за '+(prefs.period===1?'сьогодні':prefs.period+' днів')+'">'+svg+'</svg>';
    $("#dashboard-chart-subtitle").textContent=line?"Чиста виручка з урахуванням повернень":"Оплати продажів за способами оплати";
    const total=points.reduce((sum,p)=>sum+p.revenue,0);
    $("#dashboard-chart-summary").textContent="Чиста виручка за період: "+money(total)+". Готівка: "+money(points.reduce((a,p)=>a+p.cash,0))+". Картка: "+money(points.reduce((a,p)=>a+p.card,0))+".";
    all('[data-dashboard-period]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.dashboardPeriod)===prefs.period)));
    all('[data-dashboard-chart]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.dashboardChart===prefs.chart)));
  }
  function renderPanels(s) {
    const debt=s.debts.reduce((sum,row)=>sum+number(row.debt),0);
    const rows=[['Товари скоро закінчаться',String(s.low.length),'view','products',s.low.length>0],['Продажі понад залишок','Немає журналу в демо','info','negative',false],['Борги постачальникам',s.supplierData?money(debt):'Немає даних','info','supplier',debt>0],['Фіскальні документи','Не підключено · демо','info','fiscal',false],['Локальна резервна копія','Дані у браузері','info','backup',false]];
    $('#dashboard-attention').innerHTML=rows.map(row=>'<button class="dashboard-attention-row'+(row[4]?' is-warning':'')+'" type="button" data-dashboard-'+row[2]+'="'+row[3]+'"><span>'+row[0]+'</span><strong>'+escape(row[1])+' ›</strong></button>').join('');
    $('#dashboard-low-stock').innerHTML=s.low.slice(0,5).map(p=>'<tr><td>'+escape(p.code||p.id)+'</td><td>'+escape(p.name)+'</td><td>'+number(p.stock).toLocaleString('uk-UA',{maximumFractionDigits:3})+'</td><td>'+money(p.price)+'</td></tr>').join('')||'<tr><td colspan="4" class="no-data">Товарів із малим залишком немає.</td></tr>';
    $('#dashboard-suppliers').innerHTML=s.debts.slice(0,5).map(supplier=>'<tr><td>'+escape(supplier.name)+'</td><td>'+(supplier.paidAmount==null?'—':money(supplier.paidAmount))+'</td><td>'+money(supplier.debt)+'</td></tr>').join('')||'<tr><td colspan="3" class="no-data">'+(s.supplierData?'Боргів постачальникам немає.':'У демо-наборі немає даних про оплати постачальникам.')+'</td></tr>';
    const parent=$('#dashboard-sections'),visible=[];
    for(const id of prefs.sections){const panel=$('[data-dashboard-section="'+id+'"]');panel.hidden=prefs.hiddenSections.includes(id);panel.classList.remove('is-full-width');parent.append(panel);if(!panel.hidden)visible.push(panel);}
    if(visible.length%2)visible[visible.length-1].classList.add('is-full-width');
  }
  function render() {
    const s=snapshot();renderMetrics(s);renderChart(s);renderPanels(s);
    $('#home-shift-status').textContent=s.cash.isOpen?'Відкрита #'+s.cash.shift.id:'Закрита';
    $('#dashboard-shift-card').classList.toggle('is-closed',!s.cash.isOpen);
    $('#dashboard-updated').textContent='Оновлено '+s.now.toLocaleTimeString('uk-UA')+' · Порівняння: з учорашнім днем до цього самого часу';
  }
  function renderSettings() {
    for(const [kind,definitions] of [['metrics',METRICS],['sections',SECTIONS]]){
      const hidden=kind==='metrics'?'hiddenMetrics':'hiddenSections';
      $('#dashboard-'+(kind==='metrics'?'metrics':'panels')+'-options').innerHTML=draft[kind].map((id,index)=>{
        const label=definitions.find(x=>x[0]===id)[1];
        return '<div class="dashboard-layout-row" data-layout-kind="'+kind+'" data-layout-id="'+id+'"><label><input type="checkbox" '+(!draft[hidden].includes(id)?'checked':'')+'/> '+label+'</label><button class="win-btn" type="button" data-layout-move="-1" aria-label="'+escape(label+': вище')+'" '+(index===0?'disabled':'')+'>↑</button><button class="win-btn" type="button" data-layout-move="1" aria-label="'+escape(label+': нижче')+'" '+(index===draft[kind].length-1?'disabled':'')+'>↓</button></div>';
      }).join('');
    }
    selectSettingsTab(settingsTab,false);
  }
  function selectSettingsTab(kind,focus) {
    settingsTab=kind;
    all('[data-dashboard-settings-tab]').forEach(tab=>{const active=tab.dataset.dashboardSettingsTab===kind;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;if(active&&focus)tab.focus();});
    $('#dashboard-metrics-options').hidden=kind!=='metrics';$('#dashboard-panels-options').hidden=kind!=='sections';
  }
  function move(row,offset) {
    const kind=row.dataset.layoutKind,id=row.dataset.layoutId,index=draft[kind].indexOf(id),next=index+offset;
    if(next<0||next>=draft[kind].length)return;
    [draft[kind][index],draft[kind][next]]=[draft[kind][next],draft[kind][index]];renderSettings();
    $('[data-layout-kind="'+kind+'"][data-layout-id="'+id+'"] input').focus();
  }
  root.addEventListener('click',event=>{
    const target=event.target.closest('button');if(!target)return;
    if(target.dataset.dashboardView){api.navigate(target.dataset.dashboardView);return;}
    if(target.dataset.dashboardInfo){info(target.dataset.dashboardInfo);return;}
    if(target.dataset.dashboardPeriod && persist({...prefs,period:Number(target.dataset.dashboardPeriod)}))render();
    if(target.dataset.dashboardChart && persist({...prefs,chart:target.dataset.dashboardChart}))render();
  });
  $('#dashboard-refresh').addEventListener('click',()=>api.renderAll());
  const dialog=$('#dashboard-layout-dialog');
  $('#dashboard-configure').addEventListener('click',()=>{draft=copy(prefs);settingsTab='metrics';renderSettings();dialog.showModal();$('#dashboard-metrics-tab').focus();});
  for(const id of ['dashboard-layout-close','dashboard-layout-cancel'])$('#'+id).addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>$('#dashboard-configure').focus());
  $('#dashboard-layout-defaults').addEventListener('click',()=>{draft={...defaults(),period:prefs.period,chart:prefs.chart};renderSettings();});
  $('#dashboard-layout-save').addEventListener('click',()=>{if(persist(draft)){dialog.close();render();}});
  dialog.addEventListener('change',event=>{const row=event.target.closest('.dashboard-layout-row');if(!row)return;const key=row.dataset.layoutKind==='metrics'?'hiddenMetrics':'hiddenSections',id=row.dataset.layoutId;draft[key]=draft[key].filter(x=>x!==id);if(!event.target.checked)draft[key].push(id);});
  dialog.addEventListener('click',event=>{const button=event.target.closest('[data-layout-move]');if(button)move(button.closest('.dashboard-layout-row'),Number(button.dataset.layoutMove));const tab=event.target.closest('[data-dashboard-settings-tab]');if(tab)selectSettingsTab(tab.dataset.dashboardSettingsTab,true);});
  dialog.addEventListener('keydown',event=>{
    const row=event.target.closest('.dashboard-layout-row');
    if(row&&event.altKey&&['ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();move(row,event.key==='ArrowUp'?-1:1);}
    if(event.target.matches('[role="tab"]')&&['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();selectSettingsTab(event.key==='Home'?'metrics':event.key==='End'?'sections':settingsTab==='metrics'?'sections':'metrics',true);}
  });
  window.OUTPOST_DEMO_DASHBOARD={render,getPreferences:()=>copy(prefs)};
  render();
  window.setInterval(()=>{if($('[data-view-panel="home"]').classList.contains('is-active')&&!document.querySelector('dialog[open]')&&document.visibilityState==='visible')render();},30000);
})();
