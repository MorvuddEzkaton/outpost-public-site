# OutPOSt — international English website rollout
Date: 2026-11-24. Scope: public static website only. Owner requested consideration of English localization. Budget: 0 UAH. Proposed rollout, not a published English website.

## Decision and audience

Retain every Ukrainian canonical URL and Ukrainian default. Add explicit English URLs under /en; no IP-based or Accept-Language redirect, no machine-translated overlay, no automatic rewrite of existing Ukrainian slugs. Start with Lite, since it is genuinely free, has English UI and selectable base currency, and does not promise jurisdiction-specific fiscal services. Retail is a product for Ukrainian retail with optional Ukrainian fiscal integrations; do not market it as globally tax-compliant. International availability of Store listings and English support response times are not yet verified. No USD/EUR license conversion, local tax advice, country-specific certification, or global payment integration claim.

## Proposed release sequence

| Phase | Canonical route | Purpose | Gate |
|---|---|---|---|
| 0 | none | Locale-aware source inventory and guards | No public behavior change; tests preserve current Ukrainian contracts |
| 1 | /en/lite | English equivalent of Lite product page | Real English copy, download/version/hash parity, complete relevant product and eligibility content, reciprocal language links |
| 2 | /en | English product overview | Clear Lite vs Retail distinction, Ukrainian fiscal scope, links to real localized pages |
| 3 | /en/download | English download instructions | Version and SHA parity from release source, accurate Store and unsigned installer disclosures |
| 4 | /en/support | English installation/usage guidance | Working support paths; no promise of English-speaking agents or SLA |
| 5 | /en/features, /en/license | Full product information | Verify product/market/terms, no new payment, licensing or fiscal claims |

Do not add any proposed route to sitemap, nav or hreflang until its complete page and live acceptance exist. English Lite is not yet a complete equivalent if the Ukrainian page's veteran benefit is silently removed; translate a bounded eligibility section and relevant FAQ or defer hreflang until the content pair matches. Do not mark /en/lite as alternate of the Ukrainian homepage. Keep explicit Ukrainian default link from English pages and English link on corresponding Ukrainian pages. Native anchor links, accessible names, no language-dependent JS required. Use en and uk, not invented locale codes; optional x-default may be Ukrainian equivalent if needed. Each actual pair has self-canonical and identical reciprocal absolute hreflang sets including itself. OG title, description, locale, URL and image alt localized; reuse real brand assets. No fabricated screenshots or untranslated mockups represented as English UI. Disclose Ukrainian interface images if reused.

Google Search Central: https://developers.google.com/search/docs/specialty/international/localized-versions and https://developers.google.com/search/docs/specialty/international/managing-multi-regional-sites

## Source findings and engineering prerequisites (main 971455295b587940d287c1cd59dde442c2829538)

- Sitemap currently 27 Ukrainian URLs; count is not indexed-page count. Existing Lite entity ID https://outpost.com.ua/bezkoshtovna-programa-dlya-magazynu#lite-software; v1.1.1, Windows 10/11, .NET Framework 4.8, x86, price 0 UAH, uk/en/ru. Reuse that product identity in English WebPage.about; do not create a second product just to localize the page.
- scripts/verify_public_site.py currently iterates SITE.glob("*.html") for root page checks. Sitemap route resolution supports path.html; browser runtime sourcePathForRequest also maps extensionless /en/lite to site/en/lite.html. Need explicitly validate nested public pages, not blindly include all private/admin artifacts. Review sitemap coverage and all static/live checks.
- scripts/verify_public_seo_uniqueness.py currently demands WebPage.inLanguage=uk for all sitemap pages, canonical homepage SoftwareApplication.inLanguage=uk, and treats Lite schema specially by local canonical URL. Change contracts via a small explicit locale/identity manifest, not weakening validation; ensure shared Lite ID in both languages and canonical WebPage/Breadcrumb distinct. Keep WebSite/main Ukrainian language contract intact unless a deliberate separate revision changes it. Preserve strict canonical/OG uniqueness.
- scripts/prepare_public_release.py has root-only SITE.glob("*.html") loops. Review Lite release synchronization separately (not assume Retail release updater manages Lite), release_sitemap.py path-to-URL mapping, all static version/hash and live parity checks. A nested localized page must not retain stale release metadata, old binary link or SHA after next release. Prefer shared release metadata/generation with test fixtures, or version-independent links to verified downloads until release synchronization covers nested files. No versioned link duplicated without a maintenance contract.
- No site/_redirects present; verify Cloudflare Pages clean URL behavior and existing host normalization rather than introducing redirect rules untested. Security headers apply globally; no new external scripts or form submissions. Existing browser route helper can serve nested path.html. Verify live exact clean URL and status, canonical, no duplicate .html indexes or redirect loop.
- Inspect first-party resource, asset budget, accessibility, navigation, internal links, live structured metadata, sitemap freshness, indexnow and release provenance guards. Never bypass existing checks to add English. Preserve six exact-head checks, backup before merge, protected publication and independent live verifier. New English route must be included in real live acceptance, not merely local CI.
- Confirm public Lite release metadata on day of publication. Do not change installers, package hashes, native binaries, Workers/D1, cabinet, payments or license settings.

## Ready-to-edit English Lite copy

Title: Free POS and inventory software for Windows — OutPOSt Lite
Meta description: Free desktop POS for small shops. Track sales, returns, products, purchases and stock locally on Windows 10/11. No registration or time limit.
H1: Free POS and inventory software for small shops
Lead: Manage sales, purchases, products, services and stock on your own Windows PC. OutPOSt Lite is a separate free edition with no registration, license key or time limit.
Primary CTA: Download OutPOSt Lite for Windows (link from verified release metadata, or official download page until localization release synchronization is accepted).
Secondary CTA: View OutPOSt Lite in Microsoft Store (https://apps.microsoft.com/detail/9N5K4B1229VC; verify region availability; no promise of availability everywhere).
Facts: Free to use · One local user · One inventory location · Windows 10/11.
Features:
- Sales and returns: Find products by name, code or barcode, record cash/card/mixed payments and review transaction history.
- Purchases: Maintain suppliers and purchase sessions, check quantities, and post incoming stock.
- Products and services: Manage item cards, barcodes, prices, and inactive items.
- Daily overview: Review sales statistics and cash deposits/withdrawals.
- Local data: Work without a permanent internet connection; back up and restore local data, import/export the Excel catalog.
- Language and currency: Choose Ukrainian, English or Russian and the base currency; optional PIN.
Getting started: Add a few products or review an Excel catalog before importing. Count the physical stock, test a sale and a return on separate sample data, then create a backup before introducing real operations. No import speed guarantee.
Limits: Lite supports one local user and one inventory location. Printing, fiscalization, director cabinet and online modules are unavailable. Recording a card payment is not an integrated card-terminal payment. Check local legal requirements for receipts, taxes and accounting before using any POS. Lite is not a fiscal or tax-reporting system.
Local files: Data are stored in the separate Lite local database, not shared with full Retail. Use backups to protect data. The app is not an online service.
System requirements: Windows 10 or 11, .NET Framework 4.8, x86 package. Verify release on official download page; website installer may trigger Windows SmartScreen because Authenticode signing is not yet available. Do not promise support for every Windows configuration.
Full edition: OutPOSt Retail provides additional modules and optional fiscal integrations for the Ukrainian market. Standard license is UAH 2,000 per PC, perpetual with two years of included support. Seven-day trial after activation; separate provider charges may apply. No claims about fiscal features of a Store build until accepted.
Veteran initiative: In Ukraine, eligible holders of a valid combatant-status certificate can receive one full perpetual OutPOSt license for one PC, including two years of support, after eligibility verification. This private initiative is separate from free Lite, not a government grant. Additional PCs use standard licensing terms. For current eligibility and verification steps see the Ukrainian product/initiative page. Do not send sensitive documents to unverified channels.
FAQ: Is Lite a trial? No, there is no time limit. Do I need an account? No registration or license key is required. Is fiscalization included? No. Can I use my existing catalog? Excel catalog import/export is supported; check the data before importing. How do I update? Use the current official installer; the Retail update center does not apply to Lite. Where are my data? On your Windows PC, in a separate Lite database. Can I set a PIN? Yes, an optional 4–12 digit PIN. Verify all statements against the source before actual publication.

## English overview content direction (later)

H1: OutPOSt — desktop POS and inventory software for small retailers.
Lead: Manage sales, products, purchasing and stock from a Windows desktop application. Choose free OutPOSt Lite for basic local operations, or explore full OutPOSt for Ukrainian retail.
Do not promise an English web demo: current browser preview is simplified and primarily Ukrainian. Link with language disclosure only, until truly translated. Never expose private screenshots, unsupported locale features or business data.

## Acceptance and measurement

For each locale pair: one meaningful H1; original and localized title/description; source & live self-canonical, reciprocal hreflang and matching page-language attribute; correct shared product ID, version/price/download source; English native links, keyboard and mobile checks 320/390/1440, no overflow or navigation loop; validate no accidental changes to Ukrainian canonical/content. Validate localized links resolve, no auto-redirection based on language. Add only completed indexable URLs to sitemap with actual date, verify exact SHA live publisher. Use settled Search Console page metrics segmented by /en/ and by relevant query; no claim of global search demand or ranking uplift before evidence. No translation plugin, paid ads or tracking added. Site architecture rollout requires additional implementation and CI; this document is not a live page.
