# Confirmed Telegram releases — explicit audience, disabled by default

This is NOT production activation, a real test-bot delivery, Windows acceptance,
or permission to broadcast. Public PR code and synthetic tests are separate from
owner approval, private backup/restore and production cutover.

## Current migration state and missing notice

The protected public-repository publisher successfully deployed OutPOSt 0.24.40.
Its receipt explicitly records `release_announced: false`. Production uses the
confirmed-mode safety flag, so the old visitor-triggered sender is disabled, but
the notification workflow, scoped credentials and scheduled pump were not activated.
Successful installer publication alone therefore did not send a Telegram notice.
Do not turn the legacy sender back on or reset subscription cursors to compensate.

## Pilot and subscriber audiences

### Short-lived private capability pilot (no Pages configuration change)

The private pilot uses `/api/telegram/releases/pilot`. Its two independently random
256-bit capabilities are stored encrypted with Windows CurrentUser DPAPI locally
and as encrypted secrets in the protected GitHub production environment. Public
source contains **only SHA-256 verification digests**, distinct confirm/pump roles
and a 48-hour expiry in `_telegram-pilot-credentials.js`, never a credential or chat
ID. A verification digest cannot authenticate as a capability. Expired authority
fails before SQL. The ordinary subscriber dispatch remains OFF.

The protected workflow also supplies a private expected-administrator assertion.
The endpoint compares it to the existing configured positive private administrator;
wrong/missing values stop before any queue initialization. This is an equality
assertion, not a recipient selector. The response acknowledges the match but never
returns its value. Capability roles cannot confirm using a pump key, send using a
confirm key, select an audience, or gain permission on the normal dispatch route.
The pilot route always constructs the fixed pilot scope after authentication and
uses the existing isolated pilot journal, claim/ack and uncertainty protections.

No Pages secret/variable/configuration hash or D1 binding is changed. The accepted
rollback-compatible environment stays identical. There is no manual bootstrap,
public Cron route, paid resource or hidden replacement of a configuration pin.
The fresh Analytics backup and local encrypted restore precede real pilot delivery.
Preview remains blocked even with copied credentials. The endpoint uses the existing
bot only in the owner-authorized private chat; subscriber rows/cursors are untouched.

The workflow expects `OUTPOST_RELEASE_DELIVERY_MODE=pilot` and the private
`OUTPOST_RELEASE_PILOT_EXPECTED_CHAT_ID` production secret. `pilot` performs confirm,
one bounded tick, then aggregate status; it passes only if the matching product/version
has exactly one stored sent acknowledgement. Repeated pilot sends nothing extra.
After testing, disable the workflow switch; expiry also closes the pilot route.

Sources: [Web Crypto](https://developers.cloudflare.com/workers/runtime-apis/web-crypto/),
[key lifecycle](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html),
[GitHub secret encryption](https://docs.github.com/en/rest/guides/encrypting-secrets-for-the-rest-api).

For the **ordinary dispatch route**, `TELEGRAM_RELEASE_DELIVERY_MODE` is a second deliberate runtime boundary:
absent, `off` or invalid means no confirmation, queue writes or delivery. Only
`pilot` and `subscribers` are accepted. This PR does NOT set this variable.

Pilot delivery uses only the existing private `TELEGRAM_ADMIN_CHAT_ID`, which must
identify one positive, safe-integer private chat. The caller cannot supply a chat,
audience or list of recipients. The owner has authorized testing the existing bot
only in their private chat. No chat ID or credential is committed in source.
Pilot events, deliveries, retry controls and indexes use separate fixed technical
tables (`telegram_release_pilot_*`); subscriber tables and their cursors are not
read, imported, updated or reset. A test also works if the owner is not subscribed
or is already at the current release. The text is explicitly marked as a test.
Identical-version replay and parallel ticks retain the same claim/ack protections.
Changing the administrator does not send an old queued test to the old recipient.

Subscriber mode remains a separate activation decision. A completed pilot cannot
seed the real queue, establish its recipient cutoff, or suppress a later real
announcement. Switching modes alone sends nothing: real confirmation is still
required. There is no `all`, wildcard, request-supplied audience or broadcast API.

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
These Pages-key/configuration requirements apply to the future ordinary subscriber
dispatcher, not the short-lived fixed-scope private capability pilot described above.

When this mode is deliberately enabled, the visitor-triggered legacy sender is
disabled both in the Worker and its direct entry point. Before activation, existing
production behavior is preserved. There are never two active sending engines.

The manual `confirm-telegram-release.yml` runs only for owner-dispatched trusted
main, requires the production environment's human approval and two repository
activation switches. Default permissions are read-only; no PR/workflow_run trigger.
The workflow's `operation` defaults to `confirm` (no messages). `pilot` verifies
and confirms the current product, then performs exactly one bounded tick using
the separate pump credential; it is rejected unless both the runner's expected
audience and the endpoint's acknowledged audience are `pilot`. `tick` processes
an existing queue without creating an event. `status` returns only aggregate
states and whether uncertain deliveries need reconciliation. All operations keep
the same manual-owner, protected-main and human-production approval boundary.
It verifies the reviewed Windows receipt, immutable source artifacts and actual
live checks BEFORE using the confirmation credential. Existing historical artifacts
without a current reviewed receipt cannot become a new announcement accidentally.
The source SHA is trusted-caller provenance, not independent proof of a Cloudflare
deployment. A separate read-only `production_deployment_gate.py` now requires actual
matching successful canonical Pages metadata, exact merged PR/owner review and a
safe notification mode before live GETs or confirmation. It does not activate the
protected deployment writer, create credentials, or certify a completed release
workflow run; full deployment/live/scheduler end-to-end acceptance remains necessary.

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

## Ordinary dispatcher activation checklist (not executed by this PR)

1. Review/merge this exact change and approve its protected publication. Installer
   bytes, public product versions, existing domain and database bindings stay unchanged.
2. Approve a fresh private ANALYTICS_DB backup/restore check in a quiet window before
   the pilot's additive technical tables are first initialized. Never export raw
   subscribers or tokens into GitHub artifacts, Dropbox or public evidence.
3. Separately approve two new distinct scoped credentials: confirmation and pump.
   Store their Pages values as secrets and their GitHub counterparts only in the
   protected production environment. Keep the existing bot/webhook/setup keys.
4. Separately approve runtime mode `pilot`, workflow expectation
   `OUTPOST_RELEASE_DELIVERY_MODE=pilot`, and the confirmation workflow activation
   switch. Cron, public Worker routes and subscriber mode remain OFF. Check that
   the configured private administrator is the owner-approved recipient.
5. Owner-dispatch current `outpost` / operation `pilot`, approve the production job,
   and accept delivery only on a stored positive Telegram acknowledgement. Compare
   the test received in the private chat with the current download/changelog links.
6. Use `status` and repeat the same pilot once to prove no additional message.
   A timeout, bare 5xx or lost acknowledgement is `unknown`, not permission to
   retry. Ask the recipient whether it arrived; preserve private evidence and
   stop for a separately approved reconciliation decision. No blind SQL repair.
7. Disable pilot delivery and workflow activation after acceptance unless separately
   authorized to leave them enabled. Subscriber rollout and a Cron relay require
   their own recipient/volume/quota/rollback go/no-go decision.

## Operational limits and retention

Pilot has one recipient per product/version and no automatic Cron. Subscriber
batches remain at most three recipients, eight explicit-rejection attempts and a
persistent 429 cooldown. Unknown outcomes are quarantined, never automatically
resent. Large deployments require measured Free-plan HTTP/D1 budgets before a
five-minute schedule is enabled; a batch bound is not a guarantee of total daily
quota or completion time. No paid plan is enabled by these changes.

This preparation does not add automatic pruning. Acknowledged `(product, version,
recipient)` evidence must not be deleted while repeat confirmation is allowed:
otherwise replay could send again. Keep compact delivery/ack evidence and immutable
artifact facts; honor unsubscribe purging for the real queue. Pilot identifiers
are restricted to the private administrator; delete them only in a separately
approved post-test cleanup after pilot mode is OFF. No public status contains
recipient identifiers, keys, message text or raw Telegram errors.
