# OutPOSt Telegram Support

Bot: `@OutPOStUA_bot`

Operational checkpoint: 2026-10-15. Future-only confirmed release notifications and
one five-minute pump are active; the old visitor-triggered sender is disabled.
Delivery/uncertainty/current cutoffs are documented in
[CONFIRMED-TELEGRAM-RELEASES.md](CONFIRMED-TELEGRAM-RELEASES.md).

The public site links directly to the bot, while Telegram Bot API traffic is handled by the isolated `site/_telegram-support.js` module. Controlled FAQ content lives in `site/_telegram-faq.js`.

Routes:

- `POST /api/telegram/webhook` — Telegram updates only;
- `POST /api/telegram/setup` — one-time/maintenance setup endpoint protected by a separate setup key;
- `GET /api/telegram/health` — public readiness state without secrets.

The Telegram module does not use Customer Portal, Director, Sync API, CMS data or customer/store financial data.

## Required Cloudflare runtime values

Configure the sensitive values as encrypted secrets for the production Pages environment. Never commit their values to GitHub.

- `TELEGRAM_BOT_TOKEN` — current BotFather token.
- `TELEGRAM_WEBHOOK_SECRET` — random 32+ character value using only `A-Z`, `a-z`, `0-9`, `_` and `-` so it is valid for Telegram `setWebhook.secret_token`.
- `TELEGRAM_SETUP_KEY` — separate random 32+ character value used only to authorize `/api/telegram/setup`.
- `TELEGRAM_ADMIN_CHAT_ID` — private Telegram chat ID of the OutPOSt support operator.
- `TELEGRAM_PUBLIC_ENABLED` — runtime switch; `1` enables the public Telegram entry and release-notification checks.

Preview/staging must not reuse production secrets. Use isolated data and no
production Telegram writes; a real private transport test needs its own narrow
authorization and cannot disable preview isolation.

## Main bot menu

`/start` and `/help` open the main menu:

- `📚 FAQ`
- `🔔 Оновлення програм`
- `⬇️ Поточні версії`
- `🐞 Повідомити про помилку`
- `👨‍💻 Написати в підтримку`

Additional commands configured by `/api/telegram/setup`:

- `/faq`
- `/updates`
- `/download`
- `/support`
- `/whoami`

Re-run the protected setup endpoint after deploying command-list changes so BotFather/Telegram receives the new command menu and descriptions.

## FAQ

FAQ answers are deterministic controlled content from `site/_telegram-faq.js`; no generative AI is used for customer-facing factual answers.

Current sections:

- Ліцензія
- ПРРО
- еАкциз
- Бухгалтерія
- MINI-T400
- Програма

Each answer provides `Допомогло / Не допомогло`. `Не допомогло` sends the user to the existing live-support routing flow.

The static guard rejects known stale product facts such as the obsolete `1000 грн` license price and prevents hard-coded current release numbers in the runtime FAQ.

## Current releases / download

The bot does not hard-code current release numbers. It reads the official static `download.html` asset through the Pages `ASSETS` binding and extracts the two product lines independently:

- stable OutPOSt from the single `OutPOSt-Setup-vX.Y.Z.exe` reference;
- OutPOSt Бухгалтерія from the single `OutPOSt-Accounting-Setup-vX.Y.Z.exe` reference when the Accounting pre-release is published.

The `⬇️ Поточні версії` action returns separate lines for OutPOSt and Бухгалтерія and separate product actions:

- `⬇️ Завантажити OutPOSt` → official download page;
- `📝 Що нового OutPOSt` → `/changelog`;
- `⬇️ Завантажити Бухгалтерію` → official download page;
- `📘 Про Бухгалтерію` → `/buhgalteriya`.

The Telegram command description for `/download` is `Поточні версії програм`. Re-run the protected setup endpoint after this description or any command-list text changes so Telegram receives the current command metadata.

## Update subscriptions

Users can opt in with `Оновлення програм → Підписатися` and opt out at any time.

Persistence uses the existing website technical `ANALYTICS_DB` binding only. The isolated table is:

`telegram_update_subscribers`

Stored fields:

- `chat_id`
- `subscribed_at`
- `updated_at`
- `last_notified_version`

No name, Telegram username, email, phone number, customer identity, license, store, sales or financial data is stored for release subscriptions.

The schema is documented in `analytics/0002_telegram_update_subscribers.sql`; runtime also uses `CREATE TABLE IF NOT EXISTS` so no manual D1 migration is required for first use.

### Subscription cursors

When a user subscribes, `last_notified_version` is initialized to a serialized two-product cursor containing the currently published OutPOSt version and, when available, the current Бухгалтерія version. This prevents an immediate retroactive notification about releases the user already sees.

Legacy rows that still contain one plain OutPOSt version are migrated silently on the next release check: the existing OutPOSt cursor is preserved and the currently published Accounting version is used as the Accounting baseline, so old subscribers do not receive a retroactive Accounting announcement.

### Historical visitor-triggered mode — disabled in accepted production

The legacy path, only when confirmed mode is OFF, schedules a background release
check on GET `/`, `/download` and `/download.html`. It is retained for historical
compatibility, not the current delivery engine. Do not re-enable it to repair a
missing notice. That legacy check:

1. reads the official OutPOSt and Бухгалтерія versions independently from the static download page;
2. compares each product against that subscriber's stored cursor;
3. sends a product-specific Telegram release notice only for products that became newer;
4. uses product-specific text and buttons so OutPOSt and Бухгалтерія cannot masquerade as one another;
5. advances only the successfully delivered product cursor; failed product delivery is restored to pending state.

Compare-and-swap cursor updates reduce parallel duplicate attempts in this legacy mode, but the cursor is claimed before sending and a lost response/recovery write cannot establish end-to-end exactly-once delivery. Do not treat this legacy behavior as confirmed-release acceptance.

The release check runs through `ctx.waitUntil` and never changes the HTTP response for the public site, CMS, public-question proxy or installer download.

### Current confirmed-release mode

The separately gated mode in [CONFIRMED-TELEGRAM-RELEASES.md](CONFIRMED-TELEGRAM-RELEASES.md)
disables legacy visitor-triggered sending in the accepted production runtime. Its additive
journal requires verified live installer bytes/versions and protected confirmation,
then advances each product cursor only after a positive Telegram acknowledgement.
A separately accepted five-minute Cron relay pumps independently of page visits;
the checked-in template stays intentionally disabled, not a replacement operational config.
Uncertain delivery is quarantined rather than automatically repeated. Source/tests
alone are not a real-bot test, production activation, or permission to broadcast.

## Bug-report flow

`Повідомити про помилку` uses Telegram ForceReply and asks for:

1. OutPOSt version, if known;
2. the action performed before the error;
3. exact error text.

The user may attach a screenshot or file. The prompt explicitly warns not to send passwords, KEP material or secret keys. The resulting message is routed to the operator as `Помилка / діагностика` through the same existing reply-card mechanism.

## Customer flow

`outpost.com.ua` → `https://t.me/OutPOStUA_bot?start=site` → main menu → FAQ/self-service or live support.

Live-support categories:

- Техпідтримка
- Покупка / ліцензія
- ПРРО
- еАкциз
- Бухгалтерія

A customer can also write directly without choosing a category; the request is routed as a general question.

## Operator reply contract

Every routing card contains a marker like `#outpost_user_123456789`. The operator must use Telegram **Reply** on that routing card. The bot reads the marker from the replied-to bot message and sends the operator response to the matching customer chat.

Text replies are sent with an `OutPOSt` reply prefix. Non-text replies are delivered using Telegram `copyMessage`. Customer photo/document messages are also copied to the operator after their routing card.

No conversation-mapping database is required for operator replies.

## Initial / maintenance setup

1. Deploy code with Telegram runtime secrets configured.
2. Call the setup endpoint with the setup key in the `X-OutPost-Telegram-Setup-Key` header.
3. The endpoint configures the canonical webhook `https://outpost.com.ua/api/telegram/webhook`, Telegram webhook secret token, commands, description and short description.
4. `/whoami` can be used to obtain an operator chat ID when needed.

Example PowerShell setup call (the setup key stays local to the operator machine):

```powershell
$setupKey = Read-Host "Telegram setup key"
Invoke-RestMethod -Method Post -Uri "https://outpost.com.ua/api/telegram/setup" -Headers @{ "X-OutPost-Telegram-Setup-Key" = $setupKey }
```

## Security contracts

- Bot token exists only in Cloudflare secret storage at runtime.
- Webhook requests must carry the matching `X-Telegram-Bot-Api-Secret-Token` header.
- Setup endpoint uses a separate secret header and accepts `POST` only.
- No Telegram secret is present in public HTML/JS, GitHub Actions or repository history by design.
- FAQ content is controlled source, not AI-generated at runtime.
- Update subscriptions use only the privacy-minimal analytics table described above.
- Telegram code must not access `CMS_DB`, Customer Portal, Director, Sync API or customer/store financial data.
- CI runs the Telegram static guard, routing/FAQ/subscription tests and JavaScript syntax checks on every related change.
