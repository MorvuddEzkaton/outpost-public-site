/* Accessible in-page gallery for the real OutPOSt v0.24.10 screenshots.
   All links retain their original href as a same-tab fallback if JS is disabled. */
(() => {
  "use strict";
  const dialog = document.querySelector("[data-tour-lightbox]");
  const links = [...document.querySelectorAll("a[data-tour-gallery]")];
  if (!dialog || !links.length || typeof dialog.showModal !== "function") return;

  const largeImage = dialog.querySelector("[data-tour-image]");
  const caption = dialog.querySelector("[data-tour-caption]");
  const count = dialog.querySelector("[data-tour-count]");
  const thumbnails = dialog.querySelector("[data-tour-thumbs]");
  const previous = dialog.querySelector("[data-tour-prev]");
  const next = dialog.querySelector("[data-tour-next]");
  const close = dialog.querySelector("[data-tour-close]");
  const stage = dialog.querySelector("[data-tour-stage]");
  const records = links.map(link => ({
    url: link.getAttribute("href"),
    alt: link.querySelector("img")?.alt?.trim() || "Скріншот OutPOSt",
    opener: link
  }));
  const thumbButtons = [];
  let position = 0;
  let lastOpener = null;
  let pointerStart = null;

  function show(index) {
    position = (index + records.length) % records.length;
    const image = records[position];
    largeImage.src = image.url;
    largeImage.alt = image.alt;
    caption.textContent = image.alt;
    count.textContent = "Скріншот " + (position + 1) + " із " + records.length;
    thumbButtons.forEach((button, i) => {
      const active = i === position;
      button.setAttribute("aria-current", active ? "true" : "false");
      button.classList.toggle("is-current", active);
    });
    // Keep the selected thumbnail visible without scrolling the whole page.
    const selected = thumbButtons[position];
    if (selected) {
      const r = selected.getBoundingClientRect();
      const box = thumbnails.getBoundingClientRect();
      if (r.left < box.left || r.right > box.right) {
        thumbnails.scrollLeft += r.left - box.left - (box.width - r.width) / 2;
      }
    }
  }

  for (const [index, record] of records.entries()) {
    const thumb = document.createElement("button");
    thumb.type = "button";
    thumb.className = "tour-lightbox-thumb";
    thumb.setAttribute("aria-label", "Показати " + (index + 1) + ": " + record.alt);
    const preview = document.createElement("img");
    preview.src = record.url;
    preview.alt = "";
    preview.loading = "lazy";
    preview.width = 108;
    preview.height = 68;
    thumb.append(preview);
    thumb.addEventListener("click", () => show(index));
    thumbnails.append(thumb);
    thumbButtons.push(thumb);
  }

  links.forEach((link, index) => link.addEventListener("click", event => {
    if (event.defaultPrevented || event.button !== 0 ||
        event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    event.preventDefault();
    lastOpener = link;
    dialog.showModal();
    show(index);
    close.focus();
    document.documentElement.classList.add("tour-dialog-open");
  }));

  previous.addEventListener("click", () => show(position - 1));
  next.addEventListener("click", () => show(position + 1));
  close.addEventListener("click", () => dialog.close());

  dialog.addEventListener("keydown", event => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      show(position - 1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      show(position + 1);
    }
    // Esc and focus-trapping are native <dialog> behavior.
  });
  dialog.addEventListener("click", event => {
    if (event.target === dialog) dialog.close();
  });
  stage.addEventListener("touchstart", event => {
    if (event.touches.length === 1) pointerStart = event.touches[0].clientX;
  }, {passive:true});
  stage.addEventListener("touchend", event => {
    if (pointerStart === null || event.changedTouches.length !== 1) return;
    const delta = event.changedTouches[0].clientX - pointerStart;
    pointerStart = null;
    if (Math.abs(delta) >= 55) show(position + (delta < 0 ? 1 : -1));
  }, {passive:true});
  dialog.addEventListener("close", () => {
    document.documentElement.classList.remove("tour-dialog-open");
    if (lastOpener?.isConnected) lastOpener.focus({preventScroll:true});
    lastOpener = null;
  });
})();
