# Fictional month and functional demo scope

The demo generates a reproducible, fictional 30-day scenario ending today: about
1,600 itemized receipts, all four payment methods, purchase sessions and partial
supplier settlements, customer debt/repayments, returns, write-offs, completed
inventories, one inventory draft and 29 closed cash shifts plus the current shift.
The existing public demo assortment and rounded aggregate activity proportions
inform the scenario. No private database, original receipt, customer/supplier
identity, phone number, actual document amount or original timestamp is included.

Opening stock plus purchases, returns, sales, write-offs and inventory adjustments
reconciles with closing stock. Receipts reconcile with line amounts and payment
splits; supplier/customer balances reconcile with their documents. Quantities use
three decimals and money two. Reports use captured sale/return unit costs, split
mixed payments, and clearly distinguish gross profit from net business profit.

Reports support today, seven days, thirty days and custom dates, daily drill-down,
category totals and top products. History supports dates, payment/search filters,
pagination, itemized documents and returns. Purchase history supports dates,
pagination and document details. Current balances are labelled separately from
period activity.

Functional browser scenarios: cash/card/mixed/debt sales, fractional quantities,
discounts, up to eight independent persisted checkout carts, product creation and
movements, multiple saved purchase drafts, posting sessions, returns, debt payment
and write-off, cash deposits/withdrawals/supplier payments, closing/opening shifts,
saved write-off drafts and posting, inventory drafts and posting. Inventory posting
applies the counted difference to current stock, preserving intervening sales.

The remaining `data-demo-info` controls explain Windows-only users/permissions,
external database import, real filesystem access and service stock correction.
Real fiscal devices, fiscal receipts, Cloud and real store backup are unavailable
and explicitly labelled. The demo does not send financial records to a service.

A pristine scenario refreshes to the current month on a new day. Edited scenarios
and unfinished drafts remain intact. Settings offers a confirmed fresh month.
The prior 5% legacy profile upgrades only after its exact browser-local backup is
saved successfully; Settings can restore it. Storage failure preserves the prior
scenario. Appearance and dashboard layout use their existing separate keys.

`test_demo_month.mjs` checks money, stock, debt, shifts, timestamps, deterministic
generation and storage size across ordinary dates, a DST boundary and New Year.
Browser suites exercise all available business workflows, persistence, legacy
recovery, navigation, responsive layouts and three appearance modes.
