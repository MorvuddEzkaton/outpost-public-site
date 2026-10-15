# Confirmed Telegram releases — operations and delivery evidence

Operational checkpoint: 2026-10-15. Future-only subscriber confirmation and the
five-minute scheduled pump are active. The manual private-pilot workflow is OFF.
This document describes the accepted operation, not permission to replay the pilot,
announce an old version, change recipients, rotate keys or enable another sender.

## Current state and the earlier missing notice

OutPOSt 0.24.40 was published before the notification workflow/ordinary credentials
and scheduler were active. The code writer's `release_announced:false` did not prove
a message had been sent. The owner chose **future releases only**, not a catch-up
announcement. Shared `site/_telegram-release-policy.json` therefore excludes
OutPOSt 0.24.40 and Accounting 1.0.2 and older versions.

The accepted private OutPOSt pilot received one positive stored acknowledgement;
its repeat sent nothing additional. Pilot events remain in an isolated namespace.
Two new scoped ordinary keys, fresh encrypted analytics backup/independent local
restore and the compatible runtime configuration were separately accepted. One
actual scheduled invocation completed successfully with an empty ordinary queue,
no messages and unchanged subscriber cursor aggregate.

Earlier isolated local-journal transport tests also obtained real test-message
acknowledgements for both products; they used a local live/artifact adapter, not
the protected production release chain. None of these tests proves a future
subscriber announcement. Genuine new-release delivery acceptance remains pending for
each product. Never invent a Windows release, reset cursors or replay old notices
to close that acceptance item.

## Active boundaries and switches

- Runtime: `TELEGRAM_CONFIRMED_RELEASES_ENABLED=1`,
  `TELEGRAM_RELEASE_DELIVERY_MODE=subscribers`, existing `TELEGRAM_PUBLIC_ENABLED=1`.
- GitHub: `OUTPOST_AUTOMATIC_RELEASE_CONFIRMATION_ENABLED=1`,
  `OUTPOST_RELEASE_DELIVERY_MODE=subscribers`; normal protected publisher enabled.
- Manual pilot: `OUTPOST_CONFIRMED_RELEASE_PUBLICATION_ENABLED=0`.
- Scheduled relay: one private operational configuration with
  `OUTPOST_RELEASE_SCHEDULER_ENABLED=1`, Cron `*/5 * * * *`; no public routes,
  workers.dev or preview URL. The checked-in template intentionally stays OFF
  with no Cron. Do not deploy that disabled template over the active relay.
- Preview: isolated test D1 and empty production vars; release dispatch blocked
  even if credentials are copied. No production-bot testing from preview.

These are dated operational facts, not settings a documentation update may change.
The existing bot/webhook/setup credentials remain unchanged. Confirmation and pump
keys are separate encrypted secrets, not the bot token or expiring pilot capabilities.
The relay has only its pump key, no D1 binding, subscriber data or bot token.
No billing/plan changes were made; do not infer a Free plan from conservative limits.

## Confirmation after accepted publication

The trusted push-main publisher performs confirmation only after all live contracts
PASS **and** its final immutable result has been saved. It checks exact source/run,
owner review, current canonical deployment, unchanged package/configuration,
Windows receipt, immutable registry and future-only cutoff. It cannot choose a
recipient, pump the queue, create a release from a filename or fabricate Windows PASS.

The ordinary endpoint `/api/telegram/releases/dispatch` is canonical HTTPS/POST only,
with an 8 KiB input bound. The confirm key can confirm a verified product; the pump
key can tick/read aggregate status. Neither can impersonate the other role. No PR,
untrusted workflow trigger or preview gets production credentials. Current baseline
versions require no confirmation key/network/SQL from the publisher.

Notification acceptance is separate from code acceptance. Known blocks or lost/
mismatched replies produce an explicit safe `ok:false` warning/summary and operator
attention, not fake delivery success or rollback of accepted website code. The code
journal's `release_announced:false` remains truthful: its writer does not itself
send Telegram. Only a later persisted positive acknowledgement proves delivery.

## Independent five-minute pump

`scripts/telegram_release_scheduler.mjs` makes one bounded request to the fixed
canonical tick endpoint, with native-compatible `redirect:manual`, a fixed honest
API identifier and 45-second timeout. It never follows redirects, retries immediately,
confirms a release or accepts a request-selected recipient. Public fetch is 404.
Its 8 KiB response bound and at-most-three-recipient counters are checked; unknown,
failed or integrity-blocked work produces attention, not a false success.

Cron uses UTC; a five-minute interval is timezone independent. Large audiences may
take several ticks. Explicit retry/cooldown belongs to the journal, not the relay.
Idle ticks make small technical-state checks without downloading installers or
sending Telegram. Capacity/retention and observed delivery latency need continued
operational review; a batch limit is not a daily quota or delivery-time guarantee.

## Delivery semantics and uncertainty

The additive ANALYTICS_DB journal binds product/version events and recipient
deliveries; it does not access CMS/customer/store records. Existing subscribers
and their two-product cursors are preserved. Atomic conditional claims keyed by
`(product,version,chat_id)` prevent concurrent pumps sending the same pending row.

The cursor advances only after a positive Telegram `message_id` is persisted.
Cursor CAS repair must not resend. New subscribers do not receive historical events;
legacy single-product cursors retain OutPOSt and silently baseline Accounting.
Unsubscribe does not recreate recipients and purges queued identifiers. Already
in-flight requests cannot be recalled.

Explicit Telegram `ok:false` is rejection: 429 respects `retry_after` and persistent
global cooldown; explicitly rejected 5xx uses backoff, at most eight attempts.
Permanent rejection does not advance the cursor. Bare 5xx, invalid/lost responses,
transport timeout, lost acknowledgement writes and expired sending leases are
**unknown** and never automatically replayed. SQL and Telegram cannot atomically
commit a send; no mathematical end-to-end exactly-once guarantee is claimed.

Status exposes aggregate product/version/state counters only. Do not log chat IDs,
credentials, raw API bodies or database rows. There is no generic resend/reconcile
endpoint that turns unknown into pending. Inspect safely, retain the evidence and
obtain an exact-scope reconciliation decision before any repair/repeat. Do not
reset subscriber cursors merely to make the queue appear complete.

## Verification and next real release

Credential-free tests cover real in-memory SQLite, synthetic HTTP, both products,
parallel claims, replay, rollback/live blocks, unsubscribe, retries and uncertainty.
The mandatory actual-workerd suite bundles the shared cutoff policy and relay with
all outbound requests intercepted; Node-only mocks are not native-runtime proof.

For the next genuinely new approved release of each product, retain separately:

1. Actual Windows/package evidence and an exact-head approved release PR.
2. Accepted live installer SHA/size, pages/changelog/metadata and immutable journals.
3. Matching future-product confirmation result.
4. A stored positive Telegram acknowledgement and no additional send on normal
   repeated ticks; verify links/product/version without exposing recipient data.

No fake version, subscriber-wide test, old announcement or private-pilot replay is
needed. Current site health/offline tests/empty Cron cannot replace these four facts.
A successful deployment alone is not a message acknowledgement.

## Historical pilot and recovery limits

The completed private capability route `/api/telegram/releases/pilot` used two
independent expiring capabilities with only verification digests in public source.
It fixed the recipient to the existing private administrator and required a private
expected-administrator assertion. It could not select subscribers or authenticate
the ordinary route. Expiry rejects before SQL. Its isolated `telegram_release_pilot_*`
tables never reset subscribers; changing modes does not import old pilot events.
Do not promote its keys or re-enable its manual workflow to repair ordinary delivery.

Encrypted recovery copies stay outside GitHub and Dropbox. Local CurrentUser-DPAPI
restore was tested on the same Windows profile; portable/offsite restore is not
claimed. Code rollback must never overwrite newer subscription data. Preserve
resolved publisher evidence before its seven-day retention expires; unknown work
remains quarantined. See [ROLLBACK-RUNBOOK.md](ROLLBACK-RUNBOOK.md).

Sources: [Telegram responses](https://core.telegram.org/bots/api#making-requests),
[retry_after](https://core.telegram.org/bots/api#responseparameters),
[D1 conditional statements](https://developers.cloudflare.com/d1/worker-api/d1-database/),
[Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/).
