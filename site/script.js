(() => {
  "use strict";

  const header = document.querySelector("[data-header]");
  const navToggle = document.querySelector("[data-nav-toggle]");
  const nav = document.querySelector("[data-nav]");
  const toast = document.querySelector("[data-toast]");
  const copyButtons = document.querySelectorAll("[data-copy-hash]");
  let toastTimer;

  if (!document.getElementById("top")) document.documentElement.id = "top";

  const updateHeader = () => {
    if (header) header.classList.toggle("scrolled", window.scrollY > 18);
  };

  const closeNav = () => {
    if (!navToggle || !nav) return;
    navToggle.setAttribute("aria-expanded", "false");
    nav.classList.remove("open", "outpost-nav-open", "is-open");
    document.body.classList.remove("nav-open");
    document.documentElement.classList.remove("outpost-nav-lock");
  };

  const showToast = (message) => {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 2400);
  };

  const copyText = async (value) => {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      return;
    }

    const temporary = document.createElement("textarea");
    temporary.value = value;
    temporary.setAttribute("readonly", "");
    temporary.style.position = "fixed";
    temporary.style.opacity = "0";
    document.body.appendChild(temporary);
    temporary.select();
    const copied = document.execCommand("copy");
    temporary.remove();
    if (!copied) throw new Error("copy failed");
  };

  const ensureAccountingLinks = () => {
    const href = "/buhgalteriya";

    if (nav) {
      let directLink = Array.from(nav.children).find((item) => item.tagName === "A" && item.getAttribute("href") === href);
      const nestedLinks = Array.from(nav.querySelectorAll(`.nav-more a[href="${href}"]`));
      nestedLinks.forEach((link) => link.remove());

      if (!directLink) {
        const primaryPrro = Array.from(nav.children).find((item) => item.tagName === "A" && item.getAttribute("href") === "/prro" && item.textContent?.trim() === "ПРРО");
        if (primaryPrro) {
          directLink = document.createElement("a");
          directLink.href = href;
          directLink.textContent = "Бухгалтерія";
          primaryPrro.insertAdjacentElement("afterend", directLink);
        }
      }

      if (directLink) {
        if (location.pathname === href) directLink.setAttribute("aria-current", "page");
        else directLink.removeAttribute("aria-current");
      }
    }

    document.querySelectorAll(".footer-links > div").forEach((group) => {
      const heading = group.querySelector("strong")?.textContent?.trim();
      if (heading !== "Продукт" || group.querySelector(`a[href="${href}"]`)) return;
      const link = document.createElement("a");
      link.href = href;
      link.textContent = "Бухгалтерія";
      const licenseLink = group.querySelector('a[href="/#license"], a[href="#license"]');
      if (licenseLink) group.insertBefore(link, licenseLink);
      else group.appendChild(link);
    });

    const homeMore = document.querySelector(".seo-home-more");
    if (homeMore && !homeMore.querySelector(`a[href="${href}"]`)) {
      const link = document.createElement("a");
      link.href = href;
      link.textContent = "Бухгалтерія";
      homeMore.appendChild(link);
    }

    const featureToc = document.querySelector(".capabilities-page .capability-toc");
    if (featureToc && location.pathname === "/features" && !featureToc.querySelector(`a[href="${href}"]`)) {
      const link = document.createElement("a");
      link.href = href;
      link.textContent = "Бухгалтерія";
      featureToc.appendChild(link);
    }
  };

  const ensureEcosystemLinks = () => {
    const links = [
      ["/prro", "ПРРО"],
      ["/eakcyz", "еАкциз"],
      ["/buhgalteriya", "Бухгалтерія"]
    ];

    if (nav) {
      const topCheckBox = Array.from(nav.children).find((item) => item.tagName === "A" && item.getAttribute("href") === "/prro-checkbox");
      if (topCheckBox) { topCheckBox.href = "/prro"; topCheckBox.textContent = "ПРРО"; }
      const groups = Array.from(nav.querySelectorAll(".nav-more-group"));
      const about = groups.find((group) => /Про OutPOSt/i.test(group.querySelector(".nav-more-label")?.textContent || ""));
      if (about && !about.querySelector('a[href="/eakcyz"]')) {
        const a = document.createElement("a"); a.href = "/eakcyz"; a.textContent = "еАкциз"; about.appendChild(a);
      }
    }

    document.querySelectorAll(".footer-links > div").forEach((group) => {
      if (group.querySelector("strong")?.textContent?.trim() !== "Продукт") return;
      links.forEach(([href, label]) => {
        if (group.querySelector(`a[href="${href}"]`)) return;
        const a = document.createElement("a"); a.href = href; a.textContent = label; group.appendChild(a);
      });
    });
  };

  const ensureLicenseTerms = () => {
    const homeLicense = document.querySelector("#license .license-copy");
    if (homeLicense && !homeLicense.querySelector("[data-outpost-license-device-note]")) {
      const note = document.createElement("p");
      note.dataset.outpostLicenseDeviceNote = "1";
      note.innerHTML = "<strong>1 ліцензія = 1 робочий ПК.</strong> Для кожного додаткового ПК потрібна окрема ліцензія. Для замовлень понад 5 ПК діє індивідуальна знижена ціна.";
      const points = homeLicense.querySelector(".license-points");
      if (points) points.insertAdjacentElement("afterend", note);
      else homeLicense.appendChild(note);
    }

    const featureLicenseList = document.querySelector("#license-details .capability-card:first-of-type ul");
    if (featureLicenseList && !featureLicenseList.querySelector("[data-outpost-license-device-rule]")) {
      const rules = [
        "Одна ліцензія активує один робочий ПК",
        "Для кожного додаткового ПК потрібна окрема ліцензія",
        "Для замовлень понад 5 ПК діє індивідуальна знижена ціна"
      ];
      rules.forEach((text, index) => {
        const item = document.createElement("li");
        item.textContent = text;
        if (index === 0) item.dataset.outpostLicenseDeviceRule = "1";
        featureLicenseList.appendChild(item);
      });
    }
  };

  const ensureCommercialFaq = () => {
    const faqList = document.querySelector("#questions .faq-list");
    if (!faqList) return;

    const items = [
      {
        key: "license-device",
        question: "Скільки комп’ютерів покриває одна ліцензія?",
        answer: "Одна ліцензія активує один робочий ПК. Для кожного додаткового ПК потрібна окрема ліцензія. Якщо потрібно більше 5 ПК, вартість узгоджується індивідуально за зниженою ціною."
      },
      {
        key: "accounting-included",
        question: "Чи входить OutPOSt Бухгалтерія у вартість програми?",
        answer: "Так. OutPOSt Бухгалтерія входить до пакета OutPOSt без окремої ліцензії на модуль і встановлюється як окрема Windows-програма. Інсталятор пройшов Windows-перевірки; цифрового підпису Authenticode поки немає."
      }
    ];

    items.forEach((item) => {
      if (faqList.querySelector(`[data-outpost-faq="${item.key}"]`)) return;
      const details = document.createElement("details");
      details.dataset.outpostFaq = item.key;
      details.innerHTML = `<summary>${item.question}<svg aria-hidden="true"><use href="#icon-plus"></use></svg></summary><p>${item.answer}</p>`;
      faqList.appendChild(details);
    });
  };

  const ensureFopAccountingPositioning = () => {
    if (location.pathname !== "/programa-dlya-fop") return;

    const outdated = "OutPOSt відповідає за операційну роботу магазину; бухгалтерський і податковий облік залишається у ваших профільних сервісах.";
    document.querySelectorAll(".seo-check-list li").forEach((item) => {
      if (item.textContent?.trim() !== outdated) return;
      item.dataset.outpostFopAccountingNote = "1";
      item.innerHTML = 'OutPOSt уже закриває операційну роботу магазину. <a href="/buhgalteriya">OutPOSt Бухгалтерія</a> входить до основного пакета без окремої ліцензії та доступна як окрема Windows-програма. Windows-перевірки пройдено; інсталятор поки не має цифрового підпису.';
    });
  };


  const ensureTelegramContact = async () => {
    const href = "https://t.me/OutPOStUA_bot?start=site";
    let ready = false;
    try {
      const response = await fetch("/api/telegram/health", { headers: { accept: "application/json" }, cache: "no-store" });
      const state = response.ok ? await response.json() : null;
      ready = state?.enabled === true;
    } catch {
      ready = false;
    }
    if (!ready) return;

    if (!document.querySelector("[data-telegram-contact]")) {
      const link = document.createElement("a");
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener";
      link.className = "telegram-contact";
      link.dataset.telegramContact = "1";
      link.setAttribute("aria-label", "Написати в Telegram — підтримка OutPOSt");
      link.innerHTML = `<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M21.7 3.4 18.5 19c-.2 1.1-.9 1.4-1.8.9l-4.9-3.6-2.4 2.3c-.3.3-.5.5-1 .5l.4-5 9.1-8.2c.4-.4-.1-.6-.6-.2L6.1 12.8 1.3 11.3c-1-.3-1.1-1 .2-1.5L20.2 2.6c.9-.3 1.7.2 1.5.8Z"/></svg><span>Написати в Telegram</span>`;
      document.body.appendChild(link);
    }

    document.querySelectorAll(".footer-links > div").forEach((group) => {
      const heading = group.querySelector("strong")?.textContent?.trim() || "";
      if (!/Зв.?язок|Контакти/i.test(heading) || group.querySelector('[data-telegram-footer]')) return;
      const link = document.createElement("a");
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener";
      link.dataset.telegramFooter = "1";
      link.textContent = "Telegram підтримка";
      group.appendChild(link);
    });
  };

  const ensurePrivacyWording = () => {
    document.querySelectorAll(".footer-bottom span").forEach((item) => {
      const text = item.textContent?.trim();
      if (text === "Без cookies · Без аналітики · Без онлайн-платежів") {
        item.textContent = "Без cookies · Без рекламного відстеження · Без онлайн-платежів";
      }
    });
  };

  const phoneDisplay = "+380 99 321 08 72";
  const phoneHref = "tel:+380993210872";

  const isPhoneDialogTrigger = (link) => {
    if (!(link instanceof HTMLAnchorElement)) return false;
    if (!link.getAttribute("href")?.toLowerCase().startsWith("tel:")) return false;
    if (link.hasAttribute("data-phone-dial")) return false;
    return link.classList.contains("button") || /зателефонувати/i.test(link.textContent || "");
  };

  const ensurePhoneDialogStyles = () => {
    if (document.querySelector('link[data-phone-dialog-styles]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/assets/phone-dialog.css?v=20260908";
    link.dataset.phoneDialogStyles = "1";
    document.head.appendChild(link);
  };

  const ensurePhoneDialog = () => {
    let dialog = document.querySelector("[data-phone-dialog]");
    if (dialog) return dialog;

    ensurePhoneDialogStyles();
    dialog = document.createElement("dialog");
    dialog.className = "phone-dialog";
    dialog.dataset.phoneDialog = "1";
    dialog.setAttribute("aria-labelledby", "phone-dialog-title");
    dialog.innerHTML = `
      <div class="phone-dialog-card">
        <button class="phone-dialog-close" type="button" data-phone-dialog-close aria-label="Закрити">×</button>
        <span class="phone-dialog-kicker">Телефон OutPOSt</span>
        <h2 id="phone-dialog-title">Зателефонувати</h2>
        <p>Номер телефону підтримки:</p>
        <a class="phone-dialog-number" href="${phoneHref}" data-phone-dial>${phoneDisplay}</a>
        <p class="phone-dialog-hint">Натисніть на номер, якщо хочете відкрити програму для дзвінків на цьому пристрої.</p>
        <button class="button button-secondary phone-dialog-dismiss" type="button" data-phone-dialog-close>Закрити</button>
      </div>`;
    document.body.appendChild(dialog);

    dialog.querySelectorAll("[data-phone-dialog-close]").forEach((button) => {
      button.addEventListener("click", () => dialog.close());
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    return dialog;
  };

  const showPhoneDialog = () => {
    const dialog = ensurePhoneDialog();
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  };

  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target.closest('a[href^="tel:" i]') : null;
    if (!isPhoneDialogTrigger(target)) return;
    event.preventDefault();
    showPhoneDialog();
  });

  ensureAccountingLinks();
  ensureEcosystemLinks();
  ensureLicenseTerms();
  ensureCommercialFaq();
  ensureFopAccountingPositioning();
  void ensureTelegramContact();
  ensurePrivacyWording();
  updateHeader();
  window.addEventListener("scroll", updateHeader, { passive: true });

  if (navToggle && nav) {
    navToggle.addEventListener("click", () => {
      const isOpen = navToggle.getAttribute("aria-expanded") === "true";
      navToggle.setAttribute("aria-expanded", String(!isOpen));
      nav.classList.toggle("open", !isOpen);
      document.body.classList.toggle("nav-open", !isOpen);
    });

    nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeNav));
    window.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      const wasOpen = navToggle.getAttribute("aria-expanded") === "true";
      closeNav();
      if (wasOpen) navToggle.focus();
    });
  }

  copyButtons.forEach((copyButton) => {
    copyButton.addEventListener("click", async () => {
      const hash = copyButton.dataset.hashValue || document.querySelector("#setup-hash")?.textContent?.trim();
      if (!hash) return;
      const label = copyButton.querySelector("span") || copyButton;
      const originalText = label.textContent;
      try {
        await copyText(hash);
        if (toast) {
          showToast("SHA-256 скопійовано");
        } else {
          label.textContent = "Скопійовано";
          window.setTimeout(() => { label.textContent = originalText; }, 1800);
        }
      } catch {
        if (toast) {
          showToast("Не вдалося скопіювати — виділіть код вручну");
        } else {
          label.textContent = "Скопіюйте вручну";
          window.setTimeout(() => { label.textContent = originalText; }, 2200);
        }
      }
    });
  });
})();