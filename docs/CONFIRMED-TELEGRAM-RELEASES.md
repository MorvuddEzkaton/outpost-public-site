# Confirmed Telegram releases — prepared, disabled by default

This is NOT production activation, a real test-bot delivery, Windows acceptance,
or permission to broadcast. Public PR code and synthetic tests are separate from
owner approval, private backup/restore and production cutover.

## Architecture and activation boundary

An additive journal in ANALYTICS_DB owns confirmed `(product, version)` events and
per-recipient deliveries. No customer/store/CMS data is accessed. Existing subscriber
rows and serialized two-product cursors are preserved; no cursor reset/mass import.
The Pages endpoint is `/api/telegram/releases/dispatch`, canonical HTTPS only,
POST only, with an 8 KiB body limit. Preview and explicit OUTPOST_PREVIEW_ONLY=1
remain blocked regardless of copied credentials.

Production requires deliberate `TELEGRAM_CONFIRMED_RELEASES_ENABLED=1` and the
existing `TELEGRAM_PUBLIC_ENABLED=1`. Two NEW distinct encrypted keys are required:
`TELEGRAM_RELEASE_CONFIRM_KEY` can only confirm a verified product;
`TELEGRAM_RELEASE_PUMP_KEY` can only tick/read aggregate status. They cannot be
the bot, webhook or setup key. Do not create/copy/rotate keys without the agreed
activation plan. They never enter source, args, logs, screenshots or receipts.

When this mode is deliberately enabled, the visitor-triggered legacy sender is
disabled both in the Worker and its direct entry point. Before activation, existing
production behavior is preserved. There are never two active sending engines.

The manual `confirm-telegram-release.yml` runs only for owner-dispatched trusted
main, requires the production environment's human approval and two repository
activation switches. Default permissions are read-only; no PR/workflow_run trigger.
It verifies the reviewed Windows receipt, immutable source artifacts and actual
live checks BEFORE using the confirmation credential. Existing historical artifacts
without a current reviewed receipt cannot become a new announcement accidentally.
The source SHA is trusted-caller provenance, not independent proof of a Cloudflare
deployment. Separate deployment/live provenance gates remain necessary.

The endpoint rechecks source/static current version, canonical live download page,
checksum, exact bounded PE bytes and SHA-256 before creating an event, and again
before each active delivery batch. Redirects, unavailable/changed bytes, ambiguous
versions and rollbacks block dispatch. Confirmation itself sends NO messages.
Idempotent confirmation keeps the original recipient cutoff and immutable artifact
facts. A redeploy of identical bytes does not create another announcement.

## Independent scheduled pump

`scripts/telegram_release_scheduler.mjs` is a separate Cron Worker relay with no
database/subscriber access or bot token. It can call only the fixed canonical tick
endpoint using the pump key. `release/telegram-scheduler.template.json` has the
switch OFF, no cron triggers and no public Worker route. It has not been deployed.

After separate owner approval and quota checks, a private operational config may
enable `OUTPOST_RELEASE_SCHEDULER_ENABLED=1` and `*/5 * * * *`. Cron expressions use
UTC; this five-minute interval does not depend on local timezone. Each tick handles
at most three recipients to preserve a conservative Workers Free D1/HTTP budget.
Delivery may take multiple ticks for a large audience. Tune only after measured
quota/volume review; do not silently activate a paid plan. Idle ticks make only small
technical-state checks and do not re-download installers or send Telegram requests.

## Delivery semantics and the exactly-once limit

The SQL key is `(product,version,chat_id)`. Atomic conditional claims prevent
concurrent pumps from sending the same pending delivery twice. The subscriber
cursor advances only AFTER a positive Telegram message_id is persisted. A cursor
CAS conflict can be repaired without resending. Both products remain independent.
Subscribers added after confirmation are excluded; current baselines suppress
retroactive notices. Legacy single-product cursors preserve the OutPOSt value and
baseline Accounting silently. Unsubscribed rows are never recreated; queue identifiers
are purged by the confirmed-mode unsubscribe path. Already in-flight requests cannot
be recalled by removing a subscription.

Telegram's documented `ok:false` is rejection. Explicit 429 respects `retry_after`
plus persistent global cooldown; explicit rejected 5xx uses exponential backoff.
At most eight attempts, no busy loop. Permanent rejections do not advance cursors.
Bare 5xx, invalid responses, transport timeouts, lost acknowledgement writes and
expired sending leases are **unknown**, never automatically replayed. This avoids
duplicate messages but may require operator reconciliation before a notice completes.
There is NO claim of mathematical end-to-end exactly-once: sendMessage has no
client idempotency key, so SQL cannot atomically commit Telegram delivery.

`status` returns aggregate product/version/state counts only; no chat IDs or raw API
errors. Unknown/failed rows are visible in the operational report, not disguised as
success. This preparation intentionally has NO automatic/manual resend endpoint for
unknown rows: design and approval of reconciliation is a separate operational step.
No cursor is reset just to make a queue look complete.

## Verification and remaining activation work

Offline tests use real in-memory SQLite and synthetic HTTP fixtures. Tests of both
products, concurrent claims, queue replay, blocked live/rollback, unsubscribe,
legacy/new baselines, acknowledgements, retries and uncertainty do not call real
Telegram, production databases or private services. Website CI PASS is not Windows
acceptance or real-bot end-to-end acceptance.

Before any activation: exact-head human review; production D1 backup plus private
restore drill in an agreed quiet window; separate test bot/private test recipients
for real delivery without production subscribers; protected environment/credentials;
quota and retention review; reconciliation runbook; explicit owner go/no-go. Do not
disable preview isolation or reuse the production bot merely to obtain a green test.

Sources: [Telegram responses](https://core.telegram.org/bots/api#making-requests),
[retry_after](https://core.telegram.org/bots/api#responseparameters),
[D1 conditional statements](https://developers.cloudflare.com/d1/worker-api/d1-database/),
[Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/).
