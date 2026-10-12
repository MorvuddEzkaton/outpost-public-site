(() => {
  "use strict";
  const BUILD = "OUTPOST-PUBLIC-QUESTION-0.24.4.12";
  const ENDPOINT = "/api/public-question";
  let lastTrigger = null;

  function makeDialog() {
    let dialog = document.getElementById("outpost-public-question-dialog");
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.id = "outpost-public-question-dialog";
    dialog.className = "outpost-question-dialog";
    dialog.setAttribute("aria-labelledby", "outpost-question-title");
    dialog.setAttribute("data-build", BUILD);
    dialog.innerHTML = `
      <div class="outpost-question-card">
        <button class="outpost-question-x" type="button" aria-label="Закрити">×</button>
        <div class="outpost-question-form-view">
          <div class="outpost-question-eyebrow">ЗВ’ЯЗОК З OUTPOST</div>
          <h2 id="outpost-question-title">Поставити своє питання</h2>
          <p class="outpost-question-intro">Напишіть нам безпосередньо із сайту. Відповідь надійде на вказану електронну адресу.</p>
          <form class="outpost-question-form" novalidate>
            <label>Ім’я<input name="name" type="text" autocomplete="name" maxlength="120" required></label>
            <label>Email<input name="email" type="email" autocomplete="email" maxlength="254" required></label>
            <label>Тема<input name="subject" type="text" maxlength="160" required></label>
            <label>Питання<textarea name="message" rows="6" maxlength="4000" required></textarea></label>
            <label class="outpost-question-hp" aria-hidden="true">Website<input name="website" type="text" tabindex="-1" autocomplete="off"></label>
            <div class="outpost-question-status" role="status" aria-live="polite" hidden></div>
            <div class="outpost-question-actions">
              <button class="outpost-question-cancel" type="button">Скасувати</button>
              <button class="outpost-question-submit" type="submit">Надіслати питання</button>
            </div>
          </form>
        </div>
        <div class="outpost-question-success" hidden>
          <div class="outpost-question-success-icon" aria-hidden="true">✓</div>
          <h2>Питання надіслано</h2>
          <p>Дякуємо. Ми отримали ваше повідомлення і відповімо на вказану електронну адресу.</p>
          <button class="outpost-question-done" type="button">Закрити</button>
        </div>
      </div>`;
    document.body.appendChild(dialog);

    const form = dialog.querySelector(".outpost-question-form");
    const status = dialog.querySelector(".outpost-question-status");
    const submit = dialog.querySelector(".outpost-question-submit");
    const formView = dialog.querySelector(".outpost-question-form-view");
    const success = dialog.querySelector(".outpost-question-success");
    let busy = false;

    const close = () => { if (!busy) dialog.close(); };
    dialog.querySelector(".outpost-question-x").addEventListener("click", close);
    dialog.querySelector(".outpost-question-cancel").addEventListener("click", close);
    dialog.querySelector(".outpost-question-done").addEventListener("click", close);
    dialog.addEventListener("click", e => { if (e.target === dialog) close(); });
    dialog.addEventListener("close", () => { if (lastTrigger) lastTrigger.focus(); });

    form.addEventListener("submit", async e => {
      e.preventDefault();
      if (busy) return;
      if (!form.reportValidity()) return;
      status.hidden = true;
      status.classList.remove("is-error");
      busy = true;
      submit.disabled = true;
      submit.textContent = "Надсилаємо…";
      const data = new FormData(form);
      try {
        const response = await fetch(ENDPOINT, {
          method: "POST",
          mode: "cors",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: String(data.get("name") || "").trim(),
            email: String(data.get("email") || "").trim(),
            subject: String(data.get("subject") || "").trim(),
            message: String(data.get("message") || "").trim(),
            website: String(data.get("website") || "").trim(),
          }),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.ok) throw new Error(result.error || "Не вдалося надіслати питання.");
        form.reset();
        formView.hidden = true;
        success.hidden = false;
        success.querySelector(".outpost-question-done").focus();
      } catch (err) {
        status.textContent = err instanceof Error ? err.message : "Не вдалося надіслати питання. Спробуйте ще раз трохи пізніше.";
        status.classList.add("is-error");
        status.hidden = false;
      } finally {
        busy = false;
        submit.disabled = false;
        submit.textContent = "Надіслати питання";
      }
    });
    return dialog;
  }

  function openFrom(trigger) {
    lastTrigger = trigger;
    const dialog = makeDialog();
    dialog.querySelector(".outpost-question-form-view").hidden = false;
    dialog.querySelector(".outpost-question-success").hidden = true;
    const status = dialog.querySelector(".outpost-question-status");
    status.hidden = true;
    status.classList.remove("is-error");
    if (!dialog.open) dialog.showModal();
    requestAnimationFrame(() => dialog.querySelector('input[name="name"]')?.focus());
  }

  document.addEventListener("click", e => {
    const trigger = e.target.closest?.("[data-outpost-open-question]");
    if (!trigger) return;
    e.preventDefault();
    openFrom(trigger);
  });
})();
