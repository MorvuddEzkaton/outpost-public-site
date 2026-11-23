/* Full-size static screenshots, progressively enhanced native links. */
(() => {
  "use strict";
  const links = [...document.querySelectorAll(".pg-image-link")];
  if (!links.length || typeof HTMLDialogElement === "undefined") return;
  const dialog = document.createElement("dialog");
  dialog.className = "pg-lightbox";
  dialog.setAttribute("aria-labelledby", "pg-lightbox-caption");
  const top = document.createElement("div"); top.className = "pg-lightbox-top";
  const caption = document.createElement("p"); caption.id = "pg-lightbox-caption";
  const close = document.createElement("button"); close.type = "button"; close.textContent = "Закрити";
  const zoom = document.createElement("button"); zoom.type = "button";
  const buttons = document.createElement("div"); buttons.className = "pg-lightbox-buttons";
  const stage = document.createElement("div"); stage.className = "pg-lightbox-stage";
  const image = document.createElement("img");
  buttons.append(zoom, close); top.append(caption, buttons); dialog.append(top, stage); document.body.append(dialog);
  let opener;
  function setZoom(value) {
    dialog.dataset.zoomed = String(value); zoom.setAttribute("aria-pressed", String(value));
    zoom.textContent = value ? "Умістити" : "Масштаб 100%";
    stage.scrollTop = 0; stage.scrollLeft = 0;
  }
  zoom.addEventListener("click", () => setZoom(dialog.dataset.zoomed !== "true"));
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", event => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  });
  dialog.addEventListener("close", () => { if (opener) opener.focus({preventScroll:true}); });
  for (const link of links) {
    link.setAttribute("aria-haspopup", "dialog");
    link.addEventListener("click", event => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const preview = link.querySelector("img"); if (!preview) return;
      event.preventDefault(); opener = link; image.src = link.href; image.alt = preview.alt; stage.append(image);
      caption.textContent = preview.alt; setZoom(false); dialog.showModal(); close.focus();
    });
  }
})();
