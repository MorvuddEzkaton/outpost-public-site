# Modern online demo

The `/demo` presentation follows the desktop Modern design: Segoe UI, a light
`#F4F6F8` workspace, `#17212B` navigation, `#DDE3E9` borders, 10px surface corners,
7px button corners, 26px page titles, and 36px controls (44px payment actions).
Navigation uses decorative inline SVGs and exposes the current section through
`aria-current`. The existing official logo is reused.

The Modern section at the end of `outpost-demo-v1.css` is the presentation layer
over the established workflow styles. Keeping one versioned stylesheet reuses
the existing, live-verified demo cache revalidation path. Semantic surface, field, muted-text,
selection and action colors cover light, dark and high-contrast modes. Action
background and accent text colors are separate so all four selectable accents can
meet text contrast requirements. Existing saved appearance choices and demo data
remain valid; the storage schema and business logic are unchanged.

Below 900px navigation becomes a horizontally scrollable row. Narrow layouts wrap
forms and action groups; dense tables scroll inside their own panels. Dialogs stay
within the dynamic viewport and remain scrollable with enlarged text. No additional
network service, font, framework or image dependency is introduced.

The demo remains a reduced, browser-local preview, not feature parity with the
Windows product. Its noindex metadata and visible limitations remain in place.

Validation lives in the existing browser suites: all nine sections at 1440, 780,
390 and 320px; current navigation semantics; enlarged-text search dialogs; local
appearance persistence; and WCAG A/AA scans across light, dark and contrast modes.
Payment controls retain a minimum 44px height even with the base control styles.
The existing payment, keyboard, inventory, purchase and return regressions continue
to exercise the unchanged workflow contracts.

## Modern command center

Home follows `ModernDashboardView.cs` in the desktop application: five compact
status cards, the Command Center heading, eleven default metrics in four columns,
the payment chart and attention panel, then low-stock and supplier-debt previews.
Container queries use the desktop breakpoints for smaller metric grids and stacked
panels. Seven-day metric sparklines appear only when the dashboard is at least
1000px wide. The page header and grouped navigation follow the Modern workspace.

The graph aggregates existing browser-local sales and returns, with Today, 7-,
14- and 30-day periods and stacked payment bars or a net-revenue line. Cash balance
uses the existing cash journal. Yesterday comparisons stop at the same local time.
Unavailable fiscal, Cloud, backup, supplier-payment and negative-stock incident
data are explicitly identified as demo limitations rather than invented results.

The layout dialog supports metric/panel visibility and order, keyboard navigation,
cancel and defaults. Preferences use a separate, validated local storage key;
restoring the layout retains the selected graph period and style. Chart refreshes
and layout changes do not modify the demo business records or contact a service.
Existing versioned CSS and JavaScript paths retain their production cache policy.

Browser regressions compare the 842px dashboard hierarchy against the desktop
reference, verify chart/layout persistence without business-data changes, check
modal keyboard isolation and scan the layout dialog in all three appearance modes.
