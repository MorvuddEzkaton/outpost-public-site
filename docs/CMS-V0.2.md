# OutPOSt public CMS runtime v0.2

Current public runtime build marker: `OUTPOST-CMS-PUBLIC-0.2.3`.

`site/_worker.js` keeps all existing static Pages behavior and installer analytics. When the optional `CMS_DB` binding exists it additionally:

- resolves active redirects;
- renders only published CMS pages;
- reads navigation and site identity settings;
- renders semantic, sanitized blocks;
- merges published CMS pages into the existing sitemap;
- falls back to static assets if D1 is unavailable;
- preserves a real HTTP 404 for unknown paths.

Preview deployments use `outpost-cms-staging`. Production must use its own CMS D1 binding and keep the production analytics binding.


## Preview indexability safety

CMS pages served from non-canonical hosts (for example Cloudflare Pages staging/preview domains) are forced to `noindex,nofollow` and receive an `X-Robots-Tag: noindex, nofollow` response header. Dynamic CMS pages are not merged into preview-host sitemaps; preview sitemaps fall back to the static production-URL sitemap. Normal production indexability behavior on `outpost.com.ua` remains unchanged; v0.2.3 additionally fails closed when stored canonical metadata is invalid or points outside the public production host.


## Preview link and asset safety

CMS content may store normal relative links, anchors, `mailto:`, `tel:`, or external HTTPS URLs. Absolute internal URLs that point to `outpost.com.ua` or `www.outpost.com.ua` are normalized to relative paths before rendering, including their query string and fragment. The same normalization is applied to canonical-host CMS image URLs, so a staging preview loads its own site assets instead of silently falling back to production assets.

Protocol-relative values such as `//example.com/path` are not treated as local paths: CMS links fall back to `#` and CMS images are omitted. External explicit `https://...` links/images remain supported. Canonical/OG metadata remains absolute where required; this rule applies to rendered clickable/content URLs, not SEO canonical metadata.

CMS canonical metadata is fail-closed at render time: only clean HTTPS canonicals on `outpost.com.ua` or `www.outpost.com.ua` are accepted, `www` is normalized to the primary `https://outpost.com.ua` origin, and canonical values with query/fragment, credentials, preview hosts or external hosts fall back to the page's own clean production URL. A preview page with an empty canonical therefore still points at the production URL while remaining `noindex,nofollow`.
