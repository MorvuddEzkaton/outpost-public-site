import worker from "../site/_worker.js";

function require(condition, message) {
  if (!condition) throw new Error(message);
}

function envFor(contentType, body = "ok") {
  return {
    ASSETS: {
      async fetch() {
        return new Response(body, {
          status: 200,
          headers: { "Content-Type": contentType },
        });
      },
    },
  };
}

const ctx = { waitUntil() {} };

async function run(request, env) {
  return worker.fetch(request, env, ctx);
}

const previewHtml = await run(
  new Request("https://staging.outpost-web.pages.dev/features"),
  envFor("text/html; charset=utf-8", "<!doctype html><title>Preview</title>"),
);
require(previewHtml.status === 200, "preview HTML status changed");
require(
  previewHtml.headers.get("x-robots-tag") === "noindex, nofollow",
  "preview static HTML is missing X-Robots-Tag noindex",
);

const previewSitemap = await run(
  new Request("https://staging.outpost-web.pages.dev/sitemap.xml"),
  envFor("application/xml; charset=utf-8", "<urlset></urlset>"),
);
require(
  previewSitemap.headers.get("x-robots-tag") === "noindex, nofollow",
  "preview static sitemap is missing X-Robots-Tag noindex",
);

const previewCss = await run(
  new Request("https://staging.outpost-web.pages.dev/assets/site.css"),
  envFor("text/css", "body{}"),
);
require(
  previewCss.headers.get("x-robots-tag") === null,
  "preview non-indexable asset unexpectedly received X-Robots-Tag",
);

const productionHtml = await run(
  new Request("https://outpost.com.ua/features"),
  envFor("text/html; charset=utf-8", "<!doctype html><title>Production</title>"),
);
require(
  productionHtml.headers.get("x-robots-tag") === null,
  "production HTML unexpectedly received preview noindex",
);

const wwwProductionHtml = await run(
  new Request("https://www.outpost.com.ua/features"),
  envFor("text/html; charset=utf-8", "<!doctype html><title>Production</title>"),
);
require(
  wwwProductionHtml.headers.get("x-robots-tag") === null,
  "www production HTML unexpectedly received preview noindex",
);

// Advanced-mode Pages does not apply _headers to Worker-generated responses.
// The five demo assets need a direct narrow response-header override.
const demoAssetPaths = [
  "/assets/outpost-demo-v1.css",
  "/assets/outpost-demo-v1.js",
  "/assets/outpost-demo-modules-v1.js",
  "/assets/outpost-demo-returns-v1.js",
  "/assets/outpost-demo-products-v1.js",
];
for (const path of demoAssetPaths) {
  const response = await run(
    new Request("https://outpost.com.ua" + path + "?v=existing-demo-version"),
    {
      ASSETS: {
        async fetch() {
          return new Response("safe demo asset", {
            status: 200,
            headers: {
              "Content-Type": path.endsWith(".css") ? "text/css" : "application/javascript",
              "Cache-Control": "max-age=14400, must-revalidate",
            },
          });
        },
      },
    },
  );
  require(
    response.headers.get("Cache-Control") === "no-cache, max-age=0, must-revalidate",
    "demo asset revalidation not enforced for " + path,
  );
}
const ordinaryCss = await run(
  new Request("https://outpost.com.ua/assets/site.css?v=stable"),
  {
    ASSETS: {
      async fetch() {
        return new Response("body{}", {
          status: 200,
          headers: { "Content-Type": "text/css", "Cache-Control": "max-age=14400, must-revalidate" },
        });
      },
    },
  },
);
require(
  ordinaryCss.headers.get("Cache-Control") === "max-age=14400, must-revalidate",
  "ordinary non-demo CSS cache policy must not change",
);
const missingDemoAsset = await run(
  new Request("https://outpost.com.ua/assets/outpost-demo-v1.js?v=missing"),
  {
    ASSETS: {
      async fetch() {
        return new Response("missing", {
          status: 404,
          headers: { "Cache-Control": "max-age=180" },
        });
      },
    },
  },
);
require(
  missingDemoAsset.headers.get("Cache-Control") === "max-age=180",
  "failed demo assets must preserve their original status/cache policy",
);

console.log("Static preview indexability regression: PASS");
console.log("  non-production static HTML and sitemap responses are noindex,nofollow");
console.log("  production outpost.com.ua and www remain indexable");
console.log("  only five valid demo static asset responses get a direct no-cache header");
console.log("  non-demo assets and failed demo asset responses retain original cache headers");
