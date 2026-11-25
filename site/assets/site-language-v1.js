/* Public site locale preference. No redirects, tracking, cookies or external requests. */
(() => {
  "use strict";
  const key = "outpost.site.language.v1";
  const pairs = Object.freeze({
    "/": "/en",
    "/bezkoshtovna-programa-dlya-magazynu": "/en/lite",
    "/download": "/en/download",
    "/support": "/en/support",
    "/features": "/en/features",
    "/license": "/en/license",
    "/polityka-konfidentsiinosti-lite": "/en/lite-privacy"
  });
  const read = () => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const write = lang => { try { localStorage.setItem(key, lang); } catch (_) {} };
  const actual = document.documentElement.lang === "en" ? "en" : "uk";
  if (actual === "en") write("en");
  const preferred = actual === "en" || read() === "en" ? "en" : "uk";
  document.querySelectorAll("[data-site-language]").forEach(link => {
    link.addEventListener("click", () => {
      const lang = link.dataset.siteLanguage;
      if (lang === "uk" || lang === "en") write(lang);
    });
  });
  if (preferred !== "en") return;
  // The actual URL and document language stay authoritative. Preserve deliberate UA links,
  // installer destinations and fragment-specific links. Only map known published pairs.
  document.querySelectorAll("header a[href], main a[href], footer a[href]").forEach(link => {
    if (link.hasAttribute("data-site-language") || link.hasAttribute("download") ||
        link.getAttribute("hreflang") === "uk") return;
    const raw = link.getAttribute("href");
    if (!raw || raw.startsWith("#")) return;
    let url;
    try { url = new URL(raw, location.href); } catch (_) { return; }
    if (url.origin !== location.origin || url.hash || url.search ||
        !Object.prototype.hasOwnProperty.call(pairs, url.pathname)) return;
    link.setAttribute("href", pairs[url.pathname]);
    link.setAttribute("hreflang", "en");
    if (link.getAttribute("aria-current") === "page") link.removeAttribute("aria-current");
  });
})();
