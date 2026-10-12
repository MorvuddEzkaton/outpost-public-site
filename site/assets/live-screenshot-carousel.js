/* Shared in-page carousel + lightbox for real OutPOSt product screenshots.
   Native links remain functional same-tab when JavaScript is disabled. */
(() => {
  "use strict";
  const tracks = [...document.querySelectorAll(".feature-tour .debt-story-sequence, .feature-tour .tour-shots")];
  if (!tracks.length) return;
  const originalTracks = new WeakMap();
  let modal, bigImage, modalTitle, modalCount, modalPrev, modalNext, modalClose;
  let active = null;
  const mod = (n, len) => (n % len + len) % len;
  function makeButton(label, className, text) {
    const button = document.createElement("button");
    button.type = "button"; button.className = className;
    button.setAttribute("aria-label", label); button.textContent = text;
    return button;
  }
  function setupModal() {
    if (modal) return !!modal.showModal;
    modal = document.createElement("dialog");
    modal.className = "live-shot-dialog";
    modal.setAttribute("aria-label", "Перегляд скріншотів");
    const shell = document.createElement("div");
    shell.className = "live-shot-dialog-inner";
    const bar = document.createElement("div");
    bar.className = "live-shot-dialog-toolbar";
    modalTitle = document.createElement("p"); modalTitle.className = "live-shot-dialog-title";
    modalCount = document.createElement("span"); modalCount.className = "live-shot-dialog-count";
    modalClose = makeButton("Закрити перегляд", "live-shot-dialog-close", "Закрити ×");
    // Balanced toolbar: the current screenshot title remains visually centered
    // regardless of counter or close-button width (shared across all galleries).
    const rightControls = document.createElement("div");
    rightControls.className = "live-shot-dialog-toolbar-actions";
    rightControls.append(modalCount, modalClose);
    bar.append(modalTitle, rightControls);
    const stage = document.createElement("div"); stage.className = "live-shot-dialog-stage";
    modalPrev = makeButton("Попередній скріншот", "live-shot-modal-prev", "←");
    bigImage = document.createElement("img"); bigImage.alt = "";
    modalNext = makeButton("Наступний скріншот", "live-shot-modal-next", "→");
    stage.append(modalPrev, bigImage, modalNext);
    shell.append(bar, stage); modal.append(shell); document.body.append(modal);
    modalClose.addEventListener("click", () => modal.close());
    modalPrev.addEventListener("click", () => moveModal(-1));
    modalNext.addEventListener("click", () => moveModal(1));
    modal.addEventListener("keydown", e => {
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault(); moveModal(e.key === "ArrowLeft" ? -1 : 1);
      }
    });
    modal.addEventListener("click", e => { if (e.target === modal) modal.close(); });
    modal.addEventListener("close", () => {
      document.documentElement.classList.remove("live-shot-modal-open");
      if (active?.opener?.isConnected) active.opener.focus({ preventScroll: true });
      active = null;
    });
    return typeof modal.showModal === "function";
  }
  function showModalImage() {
    if (!active) return;
    const {records, index} = active;
    const shot = records[index];
    bigImage.src = shot.url;
    bigImage.alt = shot.alt;
    modalTitle.textContent = shot.title;
    modalCount.textContent = (index + 1) + " / " + records.length;
    modalPrev.disabled = records.length < 2;
    modalNext.disabled = records.length < 2;
  }
  function moveModal(delta) {
    if (!active) return;
    active.index = mod(active.index + delta, active.records.length);
    showModalImage();
  }
  tracks.forEach((track, groupIndex) => {
    const slides = [...track.children].filter(el =>
      el.matches("figure.tour-shot, figure.debt-story-item"));
    if (!slides.length) return;
    const records = slides.map(slide => {
      const link = slide.querySelector("a:has(img)");
      const img = link?.querySelector("img");
      return {url: link?.getAttribute("href") || img?.src || "",
        alt: img?.getAttribute("alt") || "Скріншот OutPOSt",
        title: slide.querySelector("h3,h4")?.textContent || "Скріншот OutPOSt",
        slide};
    });
    // Carousel behavior is applied only after the controls have been prepared.
    const wrapper = document.createElement("div");
    wrapper.className = "live-shot-carousel";
    wrapper.tabIndex = 0;
    wrapper.setAttribute("role", "region");
    wrapper.setAttribute("aria-roledescription", "карусель");
    const heading = track.closest(".debt-story-chapter")?.querySelector("h3") ||
                    track.closest(".feature-tour")?.querySelector(".tour-intro h2");
    if (heading) {
      if (!heading.id) heading.id = "live-shot-heading-" + (groupIndex + 1);
      wrapper.setAttribute("aria-labelledby", heading.id);
    }
    const actions = document.createElement("div"); actions.className = "live-shot-controls";
    const prev = makeButton("Попередній крок", "live-shot-prev", "←");
    const counter = document.createElement("span"); counter.className = "live-shot-counter";
    counter.setAttribute("role", "status"); counter.setAttribute("aria-live", "polite");
    const next = makeButton("Наступний крок", "live-shot-next", "→");
    actions.append(prev, counter, next);
    const dots = document.createElement("div"); dots.className = "live-shot-dots";
    dots.setAttribute("role", "group"); dots.setAttribute("aria-label", "Вибір кроку");
    const buttons = slides.map((slide, i) => {
      const b = makeButton("Крок " + (i + 1) + ": " + records[i].title,
        "live-shot-dot", String(i + 1));
      b.addEventListener("click", () => show(i));
      dots.append(b); return b;
    });
    track.parentNode.insertBefore(wrapper, track);
    wrapper.append(track);
    const isSingleStage = !!track.closest(".debt-single-slider, .single-shot-slider");
    if (isSingleStage) {
      // One continuous 7-step walkthrough: overlay arrows on the image itself,
      // with a compact counter below. Other feature tours retain regular controls.
      actions.removeChild(counter);
      track.append(actions);
      wrapper.append(counter);
      wrapper.classList.add("single-overlay-carousel", "debt-overlay-carousel");
    } else if (slides.length > 1) {
      wrapper.append(actions, dots);
    }
    let current = 0;
    let xStart = null;
    function show(index) {
      current = mod(index, slides.length);
      slides.forEach((slide, i) => {
        const shown = i === current;
        slide.hidden = !shown; slide.inert = !shown;
        slide.setAttribute("aria-hidden", shown ? "false" : "true");
      });
      if (slides.length > 1) {
        counter.textContent = "Крок " + (current + 1) + " із " + slides.length;
        buttons.forEach((button, i) => {
          button.setAttribute("aria-current", i === current ? "step" : "false");
          if (i === current) button.title = "Поточний крок";
          else button.removeAttribute("title");
        });
        prev.disabled = current === 0; next.disabled = current === slides.length - 1;
      }
    }
    prev.addEventListener("click", () => show(Math.max(0, current - 1)));
    next.addEventListener("click", () => show(Math.min(slides.length - 1, current + 1)));
    wrapper.addEventListener("keydown", e => {
      if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && !e.target.closest("a")) {
        e.preventDefault(); show(Math.min(slides.length - 1, Math.max(0, current + (e.key === "ArrowLeft" ? -1 : 1))));
      }
    });
    track.addEventListener("touchstart", e => { if (e.touches.length === 1) xStart = e.touches[0].clientX; }, {passive:true});
    track.addEventListener("touchend", e => {
      if (xStart === null || e.changedTouches.length !== 1) return;
      const delta = e.changedTouches[0].clientX - xStart; xStart = null;
      if (Math.abs(delta) > 60) show(Math.min(slides.length - 1, Math.max(0, current + (delta < 0 ? 1 : -1))));
    }, {passive:true});
    slides.forEach((slide, i) => {
      slide.querySelectorAll('a[href$=".webp"], a[href$=".png"], a[href$=".jpg"]').forEach(link => {
        link.removeAttribute("target"); link.removeAttribute("rel");
        link.addEventListener("click", event => {
          if (event.defaultPrevented || event.button !== 0 || event.metaKey ||
              event.ctrlKey || event.shiftKey || event.altKey) return;
          if (!setupModal()) return; // same-tab image fallback
          event.preventDefault();
          active = {records, index: i, opener: link};
          showModalImage(); modal.showModal();
          document.documentElement.classList.add("live-shot-modal-open");
          modalClose.focus();
        });
      });
    });
    // Establish the final carousel layout while every slide is still measurable,
    // then lock this group to the tallest natural step. This keeps captions of
    // different lengths from making the carousel jump between steps.
    wrapper.classList.add("live-shot-ready");
    if (!isSingleStage && slides.length > 1) {
      const tallest = Math.ceil(Math.max(...slides.map(slide => slide.getBoundingClientRect().height)));
      if (tallest > 0) track.style.setProperty("--live-shot-stage-height", tallest + "px");
    }
    show(0);
    originalTracks.set(track, {show});
  });
})();
