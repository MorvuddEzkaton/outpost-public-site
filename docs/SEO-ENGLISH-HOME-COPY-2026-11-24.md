# English homepage — source-reviewed implementation brief

24 November 2026 · Issue #122 · Draft for phase 2 after accepted English Lite (#151).
Source: site/index.html at 51f8bc4c94172665deaa7376136d47249b9348e0; Ukrainian homepage remains canonical/default. This document is not a live landing page. No release version or checksum is duplicated as visible copy. Re-audit source at implementation.

## Metadata and audience

Canonical: https://outpost.com.ua/en (site/en.html, extensionless). Title: OutPOSt — POS and inventory software for Windows. Description: Manage sales, stock, purchasing and customers on Windows. Choose free OutPOSt Lite or full OutPOSt Retail for Ukrainian stores. H1: POS and inventory software for everyday retail. English overview must explain the complete ecosystem, not compete with the free-product query assigned to /en/lite. No country-specific pages, payment processing promises or translated URL stubs.

## Ready-to-edit copy

### POS and inventory software for everyday retail

OutPOSt brings checkout, products and services, purchasing, inventory, customers and reporting together in a local Windows application. Choose a free edition for basic inventory and sales, or the full edition with advanced workflows for Ukrainian retail.

Primary: Explore free OutPOSt Lite (/en/lite, only after live acceptance). Secondary: Full edition download (/download, Ukrainian); try online demo (/demo, Ukrainian). Windows 10/11; core data on your PC; no recurring license subscription.

### Choose your edition

**OutPOSt Lite** — Free to use, with no registration, license key or time limit. Manage products, services, sales, returns, purchasing and basic statistics on one local PC, with one user and one stock location. No receipt/label printing, fiscalization or online modules. English, Ukrainian and Russian interface. Explore Lite → /en/lite. Microsoft Store → https://apps.microsoft.com/detail/9N5K4B1229VC (market availability varies).

**OutPOSt Retail** — Full Windows program for Ukrainian retailers. Checkout with barcode lookup, discounts and loyalty; multiple warehouses, inventory batches and FEFO; purchasing in 12 base currencies, orders, replenishment and receiving; customer and supplier debts including partial payments; reporting and optional integrations. UAH 2,000 per PC, perpetual license, two years of included technical support. Trial: seven days from first online activation. Full details → /features (Ukrainian). Store → https://apps.microsoft.com/detail/9N3ZC6Z3PDWZ (do not assume website/Store feature parity).

### From the first item to the daily report

Full Retail offers modern and classic interfaces, keyboard shortcuts, access rights for cashiers and administrators, compact checkout, and configurable navigation. Products and services may appear on the same receipt; services do not create stock movements. Interface and help are available in Ukrainian, Russian and English. Link to /interfeis (Ukrainian); any reused screenshot must be the real product and labeled if Ukrainian UI or sample data.

Advanced analytics includes date comparisons, returns, categories, products, ABC analysis, stock risks, saved filters and CSV. The director portal includes ten areas: overview, trends, products, categories, cashiers, cash, stock, debts, managerial payroll and local network status, subject to access rights. Core operations and history are local. Extra services may require internet. Database remains separate from program files; local/network backups, integrity checks, controlled recovery and diagnostic support package are available. Link /features, /modules and /support (Ukrainian).

### Fiscal integrations for the Ukrainian market

Three independent options: direct MINI-T400ME hardware integration over USB/COM (item database, price updates, missing items, receipts/returns and X/Z reports); optional Checkbox service integration; the full Windows edition's native online Ukrainian tax-service PRRO with file-based electronic signature, six-step configuration, receipt history and controlled recovery. Current native scenario: UAH transactions for non-excise goods and services. See /prro and /mini-t400 (Ukrainian). Provider fees, equipment and electronic signatures may cost extra. These features do not establish compliance outside Ukraine. No live transaction tests or payment processing claims.

### Separate accounting application

OutPOSt Accounting is a separate Windows application, included without a separate module license, with documents, bank, cash and inventory workflows. It is a pre-release: installer checks completed, Authenticode signing is not available, real PC acceptance is separate. See /buhgalteriya (Ukrainian). Do not market as finished or globally compliant accounting.

### Licensing and support

Full edition: UAH 2,000 once per licensed working PC, no monthly subscription, current and future functionality and updates, two years of included technical support. Separate licenses for additional PCs; individually arranged discount for six or more. The perpetual license remains valid after included support ends. Third-party services/equipment may have separate charges. No online checkout on the website. /license and /support (Ukrainian).

Private Ukrainian veteran initiative: one free perpetual full-edition license for one PC after verifying a valid Ukrainian combatant-status certificate (UBD), same functionality and two years included technical support. Additional PCs standard terms. Not a government grant. Eligibility section → /en/lite#veterans only if that exact anchor is verified; otherwise /en/lite.

### Getting started

1. Download the current Windows installer from /download (Ukrainian); current package, requirements and SHA-256 are maintained there.
2. For full Retail, activate seven-day trial online in Settings → License and test on your own PC.
3. Contact support to arrange licensing. Computer ID may be requested.
4. Sign in within Settings → License with an email code or password after issuance. Existing PC license and available online services connect; manual license file import remains available where supported.

Windows 10/11, .NET Framework 4.8, x86. Website installer is currently not Authenticode-signed; SmartScreen may warn. Use official source and verify SHA-256. No duplicated release version/hash, no claim every device is supported. Distinguish bootstrapper from full installer on download page. Store controls Store updates.

### Daily workflows

Small shops: sales, purchases, stock, customers and reports. Inventory: item cards, barcodes, receiving, stocktaking and Excel. Credit sales: item/date history, customer balance and partial/full settlement. Further workflows and market-specific information (Ukrainian): /programa-dlya-nevelykogo-magazynu, /oblik-tovariv-u-magazyni, /prodazh-v-borg, /programa-dlya-fop, /prro, /eakcyz, /buhgalteriya, /avtomatyzatsiya-magazynu, /offline-programa-dlya-magazynu, /programa-dlya-kasy-windows, /tsinnyky-ta-etyketky. Verify routes against live sitemap before authoring links. Avoid claims about unfinished e-excise/XTrace.

## FAQ parity — all 16 visible Ukrainian homepage questions

1. **How does the seven-day trial work?** Activate trial online in Settings → License. Seven days start at the first activation on that PC. Test sales, purchases and available modules; core work can then be local. After expiry new business operations are unavailable until licensed; data, history, viewing, exports and backups remain accessible.
2. **Do I need a permanent internet connection?** No, core accounting and sales are local. Optional services may need internet.
3. **Can OutPOSt control MINI-T400ME?** Full Retail connects via USB/COM, checks device status, reads item database, updates prices, adds missing cards, prints fiscal receipts/returns and produces X/Z reports. Ukrainian hardware/fiscal scenario.
4. **Where is my shop data stored?** Database, settings and backups are stored on your PC separately from program files. Normal update or uninstall does not erase the database.
5. **How many computers does one license cover?** One working PC. Additional PCs need separate licenses; individually arranged discounted terms for six or more.
6. **How do I buy OutPOSt?** Full perpetual license is UAH 2,000 per PC and includes two years of technical support. No checkout or payment on the website. Install trial, contact the author by official email or Telegram, provide Computer ID if requested; payment and issuance are arranged individually.
7. **Is there a free license for Ukrainian veterans?** A verified valid UBD certificate qualifies for one full perpetual license on one PC, same functions and two years of support. Private initiative, not government benefit.
8. **What happens after the two included years?** Program remains active and perpetual license remains valid. The period concerns included technical support.
9. **Can I move my shop database to another PC?** Use controlled backup and restore. Activation is tied to a working PC; replacement of the licensed computer is arranged separately.
10. **Do I need Microsoft Office to use Excel files?** No; XLSX import/export does not require Office. Excel helps move or bulk-edit data and does not replace the local database.
11. **What happens to stock after a sale or purchase?** Posted sales decrease actual stock; posted purchases increase it. Returns, write-offs and stocktake corrections have their own movement history.
12. **Can I use a regular shop laptop?** Designed for Windows 10/11 without separate server infrastructure. Keyboard and barcode workflows are optimized for ordinary work PCs, including lower-powered machines; test your own device.
13. **How do the fiscal integrations differ?** MINI-T400ME is physical USB/COM hardware. Checkbox is a separate PRRO service. Native PRRO is in the full Windows edition, online with file-based electronic signature, guided setup, receipt history and recovery. Current supported scenario is UAH/non-excise goods and services in Ukraine.
14. **Can I try the demo first?** Yes. Seven-day trial requires internet for first activation; reinstalling does not reset it. At expiry, new business operations stop until licensed. Login, viewing, history, reprinting, export, backups and closing an already open local shift remain available. Existing perpetual licenses are unchanged.
15. **Does the full license include future functions?** Full edition is not divided into Standard and Pro. Current and future functions on the licensed PC are included; third-party services/equipment may cost extra.
16. **How are data protected before risky operations?** Maintenance, repair and important migrations use checks and a backup before writing; integrity and critical invariants checked afterward, reject or roll back changes when violated.

## Implementation contract (do not relax existing gates)

- Add registry pair UK root / ↔ /en only when both complete pages exist; reciprocal self hreflang. Preserve independent existing Lite pair. /en is not alternate of /en/lite. Self canonical, localized WebPage/OG, real shared WebSite identity. Current Retail SoftwareApplication on Ukrainian home has inLanguage=uk; app UI languages are verified in visible copy but schema modification needs separate evidence-backed policy and parity validation. Avoid duplicating or creating another Retail software identity.
- Extend source/accessibility/support/navigation/locale/price/Cabinet/browser checks for explicit /en.html route, no broad language exceptions. Keep fiscal and Accounting direct links labeled Ukrainian; maintain exact current external Cabinet URL. Test no JS, keyboard, WCAG and 320–1440 widths. Use existing tested header pattern with native fallback links. Change /en/lite breadcrumb to real English home only when /en is accepted; update matching structured breadcrumb and primary brand link.
- /en needs three distinct contextual main-area inlinks. Candidate real links: UK home language selector, English Lite contextual overview, download page contextual English overview. Check all source/target URLs and style contrast. Add sitemap with actual edit date, no blanket lastmod reset, no index directives on policy pages.
- Keep shared product/version metadata tied to official reviewed receipts, and release tooling simulations passing. English root page is scanned by existing root glob but its translated pricing/FAQ/footer must be audited explicitly. No stale version link or hash. Keep UK guard strict; use exact language-specific markers rather than broad exclusions.
- No external tracking, backend, protected service, installer, Workers, D1 or production credential changes. Actual implementation requires accepted #151, exact six CI, backup, protected publish and independent live verifier. Canonical, redirects, hreflang, links and noindex verified live; actual Google indexing not inferred from HTTP success.
- English help and download pages remain future phases. Clearly label remaining Ukrainian destinations. Update Store website URL only after live verification, not with this draft.

## Acceptance

Use this as copy source and checklist, not as proof of completed implementation. Review any source drift after #151; validate all 16 FAQs against current homepage, and every link/feature before publication.
