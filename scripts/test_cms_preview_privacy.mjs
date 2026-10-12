import fs from "node:fs";

function require(condition, message) {
  if (!condition) throw new Error(message);
}

const runtimePath = new URL("../site/_cms-runtime.js", import.meta.url);
const runtimeSource = fs.readFileSync(runtimePath, "utf8");
const runtimeModule = await import(`data:text/javascript;base64,${Buffer.from(runtimeSource).toString("base64")}`);
const { cmsPageResponse, cmsSitemapResponse } = runtimeModule;

class MockCmsDb {
  constructor(page) {
    this.page = page;
  }

  prepare(sql) {
    const query = String(sql);
    const db = this;
    return {
      bind(...args) {
        return {
          async first() {
            if (query.includes("FROM cms_pages WHERE slug")) {
              return db.page && db.page.slug === args[0] ? db.page : null;
            }
            if (query.includes("FROM cms_redirects")) return null;
            throw new Error(`Unexpected bound first query: ${query}`);
          },
          async all() {
            return db.all(query);
          },
        };
      },
      async all() {
        return db.all(query);
      },
    };
  }

  async all(query) {
    if (query.includes("FROM cms_menus")) return { results: [] };
    if (query.includes("FROM cms_site_settings")) return { results: [] };
    if (query.includes("FROM cms_pages WHERE status='published'")) {
      return {
        results: this.page
          ? [{ slug: this.page.slug, updated_at: this.page.updated_at }]
          : [],
      };
    }
    throw new Error(`Unexpected all query: ${query}`);
  }
}

const page = {
  slug: "cms-sync-test",
  title: "CMS staging test",
  seo_title: "CMS staging test — OutPOSt",
  seo_description: "Temporary integration page for OutPOSt CMS staging.",
  canonical_url: "https://outpost.com.ua/cms-sync-test",
  robots: "index,follow",
  content_json: JSON.stringify([
    {
      type: "hero",
      heading: "Staging",
      lead: "Preview only",
      primaryLabel: "Internal",
      primaryHref: "https://outpost.com.ua/features?from=cms#top",
      secondaryLabel: "External",
      secondaryHref: "https://example.com/docs",
    },
    {
      type: "cta",
      heading: "Blocked protocol-relative link",
      text: "Must not escape through //host syntax.",
      buttonLabel: "Blocked",
      buttonHref: "//evil.example/path",
    },
    {
      type: "image",
      heading: "Blocked protocol-relative image",
      imageUrl: "//evil.example/image.png",
      imageAlt: "Blocked image",
    },
    {
      type: "image",
      heading: "Internal canonical-host image",
      imageUrl: "https://outpost.com.ua/assets/outpost-logo.png?v=cms",
      imageAlt: "Internal image",
    },
  ]),
  updated_at: "2026-09-14T06:00:00Z",
  published_at: "2026-09-14T06:00:00Z",
};

const env = { CMS_DB: new MockCmsDb(page) };

const stagingPage = await cmsPageResponse(
  new Request("https://staging.outpost-web.pages.dev/cms-sync-test"),
  env,
);
require(stagingPage?.status === 200, "staging CMS page did not render");
const stagingHtml = await stagingPage.text();
require(
  stagingHtml.includes('data-cms-build="OUTPOST-CMS-PUBLIC-0.2.3"'),
  "staging CMS page does not expose the expected 0.2.3 runtime build marker",
);
require(
  stagingHtml.includes('<meta name="robots" content="noindex,nofollow">'),
  "staging CMS page was not forced to noindex,nofollow",
);
require(
  stagingPage.headers.get("x-robots-tag") === "noindex, nofollow",
  "staging CMS page is missing X-Robots-Tag noindex",
);
require(
  stagingHtml.includes('<link rel="canonical" href="https://outpost.com.ua/cms-sync-test">'),
  "staging CMS canonical changed unexpectedly",
);
require(
  stagingHtml.includes('href="/features?from=cms#top"'),
  "staging CMS internal canonical-host link was not normalized to a relative preview-safe URL",
);
require(
  !stagingHtml.includes('href="https://outpost.com.ua/features?from=cms#top"'),
  "staging CMS leaked an absolute production internal link",
);
require(
  stagingHtml.includes('href="https://example.com/docs"'),
  "staging CMS external HTTPS link was changed unexpectedly",
);
require(
  !stagingHtml.includes("//evil.example"),
  "staging CMS allowed a protocol-relative external URL through local-path validation",
);
require(
  stagingHtml.includes('src="/assets/outpost-logo.png?v=cms"'),
  "staging CMS internal canonical-host image was not normalized to a relative preview-safe URL",
);
require(
  !stagingHtml.includes('src="https://outpost.com.ua/assets/outpost-logo.png?v=cms"'),
  "staging CMS leaked an absolute production image URL",
);

const productionPage = await cmsPageResponse(
  new Request("https://outpost.com.ua/cms-sync-test"),
  env,
);
require(productionPage?.status === 200, "production CMS page did not render");
const productionHtml = await productionPage.text();
require(
  productionHtml.includes('data-cms-build="OUTPOST-CMS-PUBLIC-0.2.3"'),
  "production CMS page does not expose the expected 0.2.3 runtime build marker",
);
require(
  productionHtml.includes('<meta name="robots" content="index,follow">'),
  "production CMS robots directive changed unexpectedly",
);
require(
  productionPage.headers.get("x-robots-tag") === null,
  "production CMS page unexpectedly received preview X-Robots-Tag",
);
require(
  productionHtml.includes('href="/features?from=cms#top"'),
  "production CMS internal canonical-host link was not normalized consistently",
);
require(
  productionHtml.includes('href="https://example.com/docs"'),
  "production CMS external HTTPS link was changed unexpectedly",
);
require(
  !productionHtml.includes("//evil.example"),
  "production CMS allowed a protocol-relative external URL through local-path validation",
);
require(
  productionHtml.includes('src="/assets/outpost-logo.png?v=cms"'),
  "production CMS internal canonical-host image was not normalized consistently",
);

const externalCanonicalPage = {
  ...page,
  slug: "bad-canonical",
  canonical_url: "https://example.com/steal-this-page",
};
const externalCanonicalResponse = await cmsPageResponse(
  new Request("https://outpost.com.ua/bad-canonical"),
  { CMS_DB: new MockCmsDb(externalCanonicalPage) },
);
require(externalCanonicalResponse?.status === 200, "production CMS page with bad canonical did not render");
const externalCanonicalHtml = await externalCanonicalResponse.text();
require(
  externalCanonicalHtml.includes('<link rel="canonical" href="https://outpost.com.ua/bad-canonical">'),
  "external CMS canonical did not fail closed to the page production URL",
);
require(
  externalCanonicalHtml.includes('<meta property="og:url" content="https://outpost.com.ua/bad-canonical">'),
  "external CMS canonical did not keep og:url aligned with the safe fallback",
);
require(
  !externalCanonicalHtml.includes("https://example.com/steal-this-page"),
  "external CMS canonical leaked into public SEO metadata",
);

const previewFallbackPage = {
  ...page,
  slug: "preview-canonical-fallback",
  canonical_url: "",
};
const previewFallbackResponse = await cmsPageResponse(
  new Request("https://staging.outpost-web.pages.dev/preview-canonical-fallback"),
  { CMS_DB: new MockCmsDb(previewFallbackPage) },
);
require(previewFallbackResponse?.status === 200, "preview CMS page without canonical did not render");
const previewFallbackHtml = await previewFallbackResponse.text();
require(
  previewFallbackHtml.includes('<link rel="canonical" href="https://outpost.com.ua/preview-canonical-fallback">'),
  "preview CMS canonical fallback must point at the production origin, not the preview host",
);
require(
  previewFallbackResponse.headers.get("x-robots-tag") === "noindex, nofollow",
  "preview canonical fallback page lost its X-Robots-Tag privacy guard",
);

const wwwCanonicalPage = {
  ...page,
  slug: "www-canonical",
  canonical_url: "https://www.outpost.com.ua/www-canonical",
};
const wwwCanonicalResponse = await cmsPageResponse(
  new Request("https://outpost.com.ua/www-canonical"),
  { CMS_DB: new MockCmsDb(wwwCanonicalPage) },
);
require(wwwCanonicalResponse?.status === 200, "CMS page with www canonical did not render");
const wwwCanonicalHtml = await wwwCanonicalResponse.text();
require(
  wwwCanonicalHtml.includes('<link rel="canonical" href="https://outpost.com.ua/www-canonical">'),
  "www CMS canonical was not normalized to the primary production host",
);

const queryCanonicalPage = {
  ...page,
  slug: "query-canonical",
  canonical_url: "https://outpost.com.ua/features?source=cms#fragment",
};
const queryCanonicalResponse = await cmsPageResponse(
  new Request("https://outpost.com.ua/query-canonical"),
  { CMS_DB: new MockCmsDb(queryCanonicalPage) },
);
require(queryCanonicalResponse?.status === 200, "CMS page with query/hash canonical did not render");
const queryCanonicalHtml = await queryCanonicalResponse.text();
require(
  queryCanonicalHtml.includes('<link rel="canonical" href="https://outpost.com.ua/query-canonical">'),
  "query/hash CMS canonical did not fail closed to the clean page production URL",
);

const staticSitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://outpost.com.ua/</loc><lastmod>2026-09-14</lastmod></url>
</urlset>`;

const previewSitemap = await cmsSitemapResponse(
  new Request("https://staging.outpost-web.pages.dev/sitemap.xml"),
  env,
  new Response(staticSitemap, {
    status: 200,
    headers: { "content-type": "application/xml; charset=utf-8" },
  }),
);
require(
  previewSitemap === null,
  "preview CMS sitemap should fall back to the static sitemap without dynamic CMS URLs",
);

const productionSitemap = await cmsSitemapResponse(
  new Request("https://outpost.com.ua/sitemap.xml"),
  env,
  new Response(staticSitemap, {
    status: 200,
    headers: { "content-type": "application/xml; charset=utf-8" },
  }),
);
require(productionSitemap?.status === 200, "production CMS sitemap did not render");
const productionSitemapText = await productionSitemap.text();
require(
  productionSitemapText.includes("<loc>https://outpost.com.ua/cms-sync-test</loc>"),
  "production CMS sitemap did not merge the published CMS page",
);
require(
  productionSitemapText.includes("<lastmod>2026-09-14</lastmod>"),
  "production CMS sitemap lost the CMS updated date",
);

console.log("CMS preview privacy regression: PASS");
console.log("  runtime build marker: OUTPOST-CMS-PUBLIC-0.2.3");
console.log("  preview CMS pages are meta/header noindex");
console.log("  preview sitemap does not merge dynamic CMS pages");
console.log("  canonical production host keeps published CMS behavior");
console.log("  canonical-host CMS anchors normalize to relative preview-safe URLs while external HTTPS stays absolute");
console.log("  protocol-relative CMS links/images are rejected instead of being treated as local paths");
console.log("  canonical-host CMS image URLs normalize to relative paths so staging validates its own assets");
console.log("  invalid/external CMS canonical metadata fails closed to clean production URLs");
console.log("  preview canonical fallback never points at the preview host");
