(() => {
  'use strict';

  const btn = document.querySelector('.menu-toggle:not([data-nav-toggle])');
  const nav = document.querySelector('.nav');
  const actions = document.querySelector('.nav-actions');

  if (nav) {
    if (actions && !nav.querySelector('.mobile-nav-actions')) {
      const mobile = document.createElement('div');
      mobile.className = 'mobile-nav-actions';
      const cabinet = actions.querySelector('.cabinet-link');
      const download = actions.querySelector('.download-small');
      if (cabinet) {
        const a = cabinet.cloneNode(true); a.className = 'mobile-cabinet'; mobile.appendChild(a);
      }
      if (download) {
        const a = download.cloneNode(true); a.className = 'mobile-download'; mobile.appendChild(a);
      }
      nav.appendChild(mobile);
    }

    const current = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
    nav.querySelectorAll(':scope > a[href]').forEach(a => {
      const href = a.getAttribute('href').split('#')[0].split('/').pop().toLowerCase();
      if (href === current || (current === '' && href === 'index.html')) a.setAttribute('aria-current', 'page');
    });

    const closeMenu = () => {
      nav.classList.remove('open');
      if (btn) { btn.setAttribute('aria-expanded','false'); btn.setAttribute('aria-label','Відкрити меню'); btn.textContent='☰'; }
    };
    const openMenu = () => {
      nav.classList.add('open');
      if (btn) { btn.setAttribute('aria-expanded','true'); btn.setAttribute('aria-label','Закрити меню'); btn.textContent='×'; }
    };
    if (btn) btn.addEventListener('click', e => { e.stopPropagation(); nav.classList.contains('open') ? closeMenu() : openMenu(); });
    nav.addEventListener('click', e => { if (e.target.closest('a')) closeMenu(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenu(); });
    document.addEventListener('click', e => { if (nav.classList.contains('open') && !nav.contains(e.target) && (!btn || !btn.contains(e.target))) closeMenu(); });
    window.addEventListener('resize', () => { if (window.innerWidth > 1080) closeMenu(); }, {passive:true});
  }

  // All disclosure blocks start closed and visibly advertise that they can be expanded.
  const initDisclosures = () => {
    document.querySelectorAll('main details').forEach(details => {
      details.open = false;
      const summary = details.querySelector(':scope > summary');
      if (!summary) return;
      summary.classList.add('disclosure-summary');

      let affordance = null;
      if (summary.classList.contains('release-head')) {
        affordance = summary.querySelector('.release-toggle');
        if (!affordance) {
          affordance = document.createElement('span');
          affordance.className = 'release-toggle';
          summary.appendChild(affordance);
        }
      } else {
        affordance = summary.querySelector(':scope > .disclosure-affordance');
        if (!affordance) {
          affordance = document.createElement('span');
          summary.appendChild(affordance);
        }
      }
      affordance.classList.add('disclosure-affordance');

      const sync = () => {
        affordance.innerHTML = `<span class="disclosure-label">${details.open ? 'Згорнути' : 'Розгорнути'}</span><span class="disclosure-chevron" aria-hidden="true">⌄</span>`;
      };
      sync();
      details.addEventListener('toggle', sync);
    });
  };
  initDisclosures();
  // Some browsers may restore <details> state from history. Reset the initial view on pageshow too.
  window.addEventListener('pageshow', event => {
    if (!event.persisted) return;
    document.querySelectorAll('main details').forEach(details => { details.open = false; });
  });

  // Production-compatible contact form. In a local file:// preview it opens normally,
  // but does not pretend that the production API is available.
  let lastQuestionTrigger = null;
  const makeQuestionDialog = () => {
    let dialog = document.getElementById('outpost-public-question-dialog');
    if (dialog) return dialog;

    dialog = document.createElement('dialog');
    dialog.id = 'outpost-public-question-dialog';
    dialog.className = 'outpost-question-dialog';
    dialog.setAttribute('aria-labelledby','outpost-question-title');
    dialog.innerHTML = `
      <div class="outpost-question-card">
        <button class="outpost-question-x" type="button" aria-label="Закрити">×</button>
        <div class="outpost-question-form-view">
          <div class="outpost-question-eyebrow">ЗВОРОТНИЙ ЗВ’ЯЗОК</div>
          <h2 id="outpost-question-title">Написати в OutPOSt</h2>
          <p class="outpost-question-intro">Надішліть повідомлення прямо із сайту. Відповідь надійде на вказану електронну адресу.</p>
          <form class="outpost-question-form" novalidate>
            <label>Ім’я<input name="name" type="text" autocomplete="name" maxlength="120" required></label>
            <label>Email<input name="email" type="email" autocomplete="email" maxlength="254" required></label>
            <label>Тема<input name="subject" type="text" maxlength="160" required></label>
            <label>Повідомлення<textarea name="message" rows="6" maxlength="4000" required></textarea></label>
            <label class="outpost-question-hp" aria-hidden="true">Website<input name="website" type="text" tabindex="-1" autocomplete="off"></label>
            <div class="outpost-question-status" role="status" aria-live="polite" hidden></div>
            <div class="outpost-question-actions">
              <button class="outpost-question-cancel" type="button">Скасувати</button>
              <button class="outpost-question-submit" type="submit">Надіслати</button>
            </div>
          </form>
        </div>
        <div class="outpost-question-success" hidden>
          <div class="outpost-question-success-icon" aria-hidden="true">✓</div>
          <h2>Повідомлення надіслано</h2>
          <p>Дя�;уємо. Ми отримали ваше повідомлення і відповімо на вказану електронну адресу.</p>
          <button class="outpost-question-done" type="button">Закрити</button>
        </div>
      </div>`;
    document.body.appendChild(dialog);

    const form = dialog.querySelector('.outpost-question-form');
    const status = dialog.querySelector('.outpost-question-status');
    const submit = dialog.querySelector('.outpost-question-submit');
    const formView = dialog.querySelector('.outpost-question-form-view');
    const success = dialog.querySelector('.outpost-question-success');
    let busy = false;

    const close = () => { if (!busy) dialog.close(); };
    dialog.querySelector('.outpost-question-x').addEventListener('click', close);
    dialog.querySelector('.outpost-question-cancel').addEventListener('click', close);
    dialog.querySelector('.outpost-question-done').addEventListener('click', close);
    dialog.addEventListener('click', e => { if (e.target === dialog) close(); });
    dialog.addEventListener('close', () => { lastQuestionTrigger?.focus?.(); });

    form.addEventListener('submit', async e => {
      e.preventDefault();
      if (busy || !form.reportValidity()) return;
      status.hidden = true;
      status.classList.remove('is-error');

      if (location.protocol === 'file:') {
        status.textContent = 'Локальний HTML-прототип: форма повністю відтворена, але надсилання вимкнене. Після розміщення на outpost.com.ua вона використовуватиме чинний /api/public-question.';
        status.hidden = false;
        return;
      }

      busy = true;
      submit.disabled = true;
      submit.textContent = 'Надсилаємо…';
      const data = new FormData(form);
      try {
        const response = await fetch('/api/public-question', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({
            name:String(data.get('name')||'').trim(),
            email:String(data.get('email')||'').trim(),
            subject:String(data.get('subject')||'').trim(),
            message:String(data.get('message')||'').trim(),
            website:String(data.get('website')||'').trim()
          })
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.ok) throw new Error(result.error || 'Не вдалося надіслати повідомлення.');
        form.reset();
        formView.hidden = true;
        success.hidden = false;
        success.querySelector('.outpost-question-done').focus();
      } catch (err) {
        status.textContent = err instanceof Error ? err.message : 'Не вдалося надіслати повідомлення. Спробуйте ще раз трохи пізніше.';
        status.classList.add('is-error');
        status.hidden = false;
      } finally {
        busy = false;
        submit.disabled = false;
        submit.textContent = 'Надіслати';
      }
    });
    return dialog;
  };

  document.addEventListener('click', e => {
    const trigger = e.target.closest?.('[data-outpost-open-question]');
    if (!trigger) return;
    e.preventDefault();
    lastQuestionTrigger = trigger;
    const dialog = makeQuestionDialog();
    dialog.querySelector('.outpost-question-form-view').hidden = false;
    dialog.querySelector('.outpost-question-success').hidden = true;
    const status = dialog.querySelector('.outpost-question-status');
    status.hidden = true;
    status.classList.remove('is-error');
    if (!dialog.open) dialog.showModal();
    requestAnimationFrame(() => dialog.querySelector('input[name="name"]')?.focus());
  });

  // Floating Telegram button: always visible in the redesign prototype.
  if (!document.querySelector('[data-telegram-contact]')) {
    const link = document.createElement('a');
    link.href = 'https://t.me/OutPOStUA_bot?start=site';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.className = 'telegram-contact';
    link.dataset.telegramContact = '1';
    link.setAttribute('aria-label','Написати в Telegram — підтримка OutPOSt');
    link.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M21.7 3.4 18.5 19c-.2 1.1-.9 1.4-1.8.9l-4.9-3.6-2.4 2.3c-.3.3-.5.5-1 .5l.4-5 9.1-8.2c.4-.4-.1-.6-.6-.2L6.1 12.8 1.3 11.3c-1-.3-1.1-1 .2-1.5L20.2 2.6c.9-.3 1.7.2 1.5.8Z"/></svg><span>Написати в Telegram</span>';
    document.body.appendChild(link);
  }
})();


/* OUTPOST_V20_NAV_OWNER */
(() => {
  const toggle = document.querySelector('[data-nav-toggle]');
  const nav = document.querySelector('[data-nav]');
  if (!toggle || !nav) return;

  const isOpen = () => toggle.getAttribute('aria-expanded') === 'true';
  const sync = (open) => {
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    nav.classList.toggle('open', open);
    document.body.classList.toggle('nav-open', open);
    document.documentElement.classList.toggle('outpost-nav-lock', open);
  };

  toggle.addEventListener('click', (event) => {
    event.stopPropagation();
    event.stopImmediatePropagation();
    sync(!isOpen());
  });

  nav.addEventListener('click', (event) => {
    if (event.target.closest('a')) sync(false);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const wasOpen = isOpen();
    sync(false);
    if (wasOpen) toggle.focus();
  });

  document.addEventListener('click', (event) => {
    if (!isOpen()) return;
    if (nav.contains(event.target) || toggle.contains(event.target)) return;
    sync(false);
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 1080 && isOpen()) sync(false);
  }, { passive: true });
})();
