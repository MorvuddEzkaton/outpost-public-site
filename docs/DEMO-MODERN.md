# Modern online demo

The `/demo` presentation follows the desktop Modern design: Segoe UI, a light
`#F4F6F8` workspace, `#17212B` navigation, `#DDE3E9` borders, 10px surface corners,
7px button corners, 26px page titles, and 36px controls (44px payment actions).
Navigation uses decorative inline SVGs and exposes the current section through
`aria-current`. The existing official logo is reused.

`outpost-demo-modern.css` is the presentation layer over the established workflow
stylesheet. Keep it after `outpost-demo-v1.css`. Semantic surface, field, muted-text,
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
The existing payment, keyboard, inventory, purchase and return regressions continue
to exercise the unchanged workflow contracts.
