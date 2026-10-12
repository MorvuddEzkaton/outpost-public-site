import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const faqSource = fs.readFileSync(path.join(root, "site", "_telegram-faq.js"), "utf8");
const faqUrl = `data:text/javascript;base64,${Buffer.from(faqSource).toString("base64")}`;
const supportSource = fs
  .readFileSync(path.join(root, "site", "_telegram-support.js"), "utf8")
  .replace('from "./_telegram-faq.js"', `from "${faqUrl}"`);
const moduleUrl = `data:text/javascript;base64,${Buffer.from(supportSource).toString("base64")}`;
const telegram = await import(moduleUrl);

class FakeStatement {
  constructor(db, sql) {
    this.db = db;
    this.sql = String(sql).replace(/\s+/g, " ").trim();
    this.args = [];
  }

  bind(...args) {
    this.args = args;
    return this;
  }

  async run() {
    if (this.sql.startsWith("CREATE TABLE IF NOT EXISTS telegram_update_subscribers")) {
      return { success: true, meta: { changes: 0 } };
    }

    if (this.sql.startsWith("INSERT INTO telegram_update_subscribers")) {
      const [chatId, subscribedAt, updatedAt, version] = this.args.map(String);
      const existing = this.db.subscribers.get(chatId);
      this.db.subscribers.set(chatId, {
        chat_id: chatId,
        subscribed_at: existing?.subscribed_at || subscribedAt,
        updated_at: updatedAt,
        last_notified_version: version
      });
      return { success: true, meta: { changes: 1 } };
    }

    if (this.sql.startsWith("DELETE FROM telegram_update_subscribers")) {
      const changed = this.db.subscribers.delete(String(this.args[0])) ? 1 : 0;
      return { success: true, meta: { changes: changed } };
    }

    if (this.sql.startsWith("UPDATE telegram_update_subscribers")) {
      const [version, updatedAt, chatId, expectedVersion] = this.args.map(String);
      const row = this.db.subscribers.get(chatId);
      const compareAndSwap = this.sql.includes("AND last_notified_version = ?");
      const matches = row && (!compareAndSwap || row.last_notified_version === expectedVersion);
      if (matches) {
        row.last_notified_version = version;
        row.updated_at = updatedAt;
      }
      return { success: true, meta: { changes: matches ? 1 : 0 } };
    }

    throw new Error(`Unexpected D1 run SQL: ${this.sql}`);
  }

  async first() {
    if (this.sql.includes("FROM telegram_update_subscribers") && this.sql.includes("WHERE chat_id = ?")) {
      return this.db.subscribers.get(String(this.args[0])) || null;
    }
    throw new Error(`Unexpected D1 first SQL: ${this.sql}`);
  }

  async all() {
    if (this.sql.includes("FROM telegram_update_subscribers") && this.sql.includes("last_notified_version <> ?")) {
      const version = String(this.args[0]);
      return {
        results: [...this.db.subscribers.values()]
          .filter((row) => row.last_notified_version !== version)
          .slice(0, 100)
          .map((row) => ({ chat_id: row.chat_id, last_notified_version: row.last_notified_version }))
      };
    }
    throw new Error(`Unexpected D1 all SQL: ${this.sql}`);
  }
}

class FakeAnalyticsDb {
  constructor() {
    this.subscribers = new Map();
  }

  prepare(sql) {
    return new FakeStatement(this, sql);
  }
}

let currentVersion = "0.24.2";
let currentAccountingVersion = "0.402.3";
const analyticsDb = new FakeAnalyticsDb();
const assets = {
  async fetch() {
    return new Response(
      `<section data-download-product="outpost"><a href="/downloads/OutPOSt-Setup-v${currentVersion}.exe">download</a></section>` +
      `<section data-download-product="accounting"><a href="/downloads/OutPOSt-Accounting-Setup-v${currentAccountingVersion}.exe">accounting</a></section>`,
      {
        status: 200,
        headers: { "content-type": "text/html; charset=utf-8" }
      }
    );
  }
};

const env = {
  TELEGRAM_BOT_TOKEN: "test-token",
  TELEGRAM_WEBHOOK_SECRET: "test-webhook-secret",
  TELEGRAM_SETUP_KEY: "test-setup-key",
  TELEGRAM_ADMIN_CHAT_ID: "9001",
  ANALYTICS_DB: analyticsDb,
  ASSETS: assets
};

const calls = [];
globalThis.fetch = async (url, init = {}) => {
  if (!String(url).startsWith("https://api.telegram.org/")) throw new Error(`Unexpected fetch: ${url}`);
  const method = String(url).split("/").pop();
  const payload = init.body ? JSON.parse(init.body) : {};
  calls.push({ method, payload });
  const result = method === "getWebhookInfo"
    ? { url: "https://outpost.com.ua/api/telegram/webhook", pending_update_count: 0 }
    : method === "sendMessage"
      ? { message_id: calls.length }
      : true;
  return new Response(JSON.stringify({ ok: true, result }), {
    status: 200,
    headers: { "content-type": "application/json" }
  });
};

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function webhookRequest(update, secret = env.TELEGRAM_WEBHOOK_SECRET) {
  return new Request("https://outpost.com.ua/api/telegram/webhook", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-telegram-bot-api-secret-token": secret
    },
    body: JSON.stringify(update)
  });
}

function callbackUpdate(id, chatId, data) {
  return {
    update_id: 1000 + id,
    callback_query: {
      id: String(id),
      from: { id: chatId, first_name: "Client", is_bot: false },
      data,
      message: { message_id: id, chat: { id: chatId, type: "private" }, text: "menu" }
    }
  };
}

async function responseJson(response) {
  return JSON.parse(await response.text());
}

// Unauthorized webhook must not touch Telegram API.
calls.length = 0;
let response = await telegram.handleTelegramWebhook(webhookRequest({ update_id: 1 }, "wrong-secret"), env);
assert(response.status === 401, "wrong webhook secret must be rejected");
assert(calls.length === 0, "unauthorized webhook must not call Telegram API");

// /whoami returns the sender chat ID without any admin state.
calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest({
  update_id: 2,
  message: {
    message_id: 10,
    from: { id: 123, first_name: "Roman", is_bot: false },
    chat: { id: 123, type: "private" },
    text: "/whoami"
  }
}), env);
assert(response.status === 200, "/whoami webhook must succeed");
assert(calls.some((call) => call.method === "sendMessage" && call.payload.chat_id === "123" && /123/.test(call.payload.text)), "/whoami must return chat ID");

// /start exposes FAQ, updates, current release, bug report and live support actions.
calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest({
  update_id: 3,
  message: {
    message_id: 11,
    from: { id: 321, first_name: "Client", is_bot: false },
    chat: { id: 321, type: "private" },
    text: "/start"
  }
}), env);
assert(response.status === 200, "/start must succeed");
const startCall = calls.find((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "321");
const startButtons = JSON.stringify(startCall?.payload?.reply_markup || {});
assert(startButtons.includes("nav:faq"), "start menu must expose FAQ");
assert(startButtons.includes("updates:menu"), "start menu must expose update subscriptions");
assert(startButtons.includes("download:current"), "start menu must expose current release");
assert(startButtons.includes("error:start"), "start menu must expose bug report flow");
assert(startButtons.includes("nav:support"), "start menu must preserve live support");

// Current-version action must present OutPOSt and Accounting as two distinct products.
calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest(callbackUpdate(19, 321, "download:current")), env);
assert(response.status === 200, "current-version callback must succeed");
const currentVersionsMessage = calls.find((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "321");
assert(/OutPOSt: v0\.24\.2/.test(currentVersionsMessage?.payload?.text || ""), "current versions must name the OutPOSt version");
assert(/Бухгалтерія: v0\.402\.3/.test(currentVersionsMessage?.payload?.text || ""), "current versions must name the Accounting version separately");
const currentVersionsButtons = JSON.stringify(currentVersionsMessage?.payload?.reply_markup || {});
assert(currentVersionsButtons.includes("Завантажити OutPOSt"), "current versions must expose an OutPOSt-specific download action");
assert(currentVersionsButtons.includes("Що нового OutPOSt"), "current versions must expose OutPOSt changelog action");
assert(currentVersionsButtons.includes("Завантажити Бухгалтерію"), "current versions must expose an Accounting-specific download action");
assert(currentVersionsButtons.includes("Про Бухгалтерію"), "current versions must expose an Accounting details action");
assert(currentVersionsButtons.includes("https://outpost.com.ua/buhgalteriya"), "Accounting details action must point to /buhgalteriya");

// FAQ navigation copy must match the current multi-product bot labels.
calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest(callbackUpdate(18, 321, "faq:program_download")), env);
assert(response.status === 200, "program_download FAQ callback must succeed");
const downloadFaqAnswer = calls.find((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "321");
assert(/Поточні версії/.test(downloadFaqAnswer?.payload?.text || ""), "download FAQ must use the current 'Поточні версії' label");
assert(/OutPOSt/.test(downloadFaqAnswer?.payload?.text || "") && /Бухгалтерії/.test(downloadFaqAnswer?.payload?.text || ""), "download FAQ must explain that OutPOSt and Accounting versions are shown separately");
assert(!/Поточна версія\s*\/\s*завантажити/.test(downloadFaqAnswer?.payload?.text || ""), "download FAQ must not regress to the old singular menu label");

calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest(callbackUpdate(17, 321, "faq:program_update")), env);
assert(response.status === 200, "program_update FAQ callback must succeed");
const updatesFaqAnswer = calls.find((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "321");
assert(/Оновлення програм/.test(updatesFaqAnswer?.payload?.text || ""), "updates FAQ must use the current multi-product updates menu label");
assert(/Підписатися/.test(updatesFaqAnswer?.payload?.text || ""), "updates FAQ must point to the subscription action");

// FAQ answer must come from controlled content and keep a live-support fallback.
calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest(callbackUpdate(20, 321, "faq:license_price")), env);
assert(response.status === 200, "FAQ callback must succeed");
const faqAnswer = calls.find((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "321");
assert(faqAnswer?.payload?.text?.includes("2000 грн"), "license FAQ must expose the current 2000 UAH price");
assert(JSON.stringify(faqAnswer?.payload?.reply_markup || {}).includes("faq:no"), "FAQ answer must offer support fallback");

// Director/payroll FAQ must be discoverable and preserve its safety boundary.
calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest(callbackUpdate(23, 321, "nav:faq")), env);
assert(response.status === 200, "FAQ menu callback must succeed");
const faqMenu = calls.find((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "321");
assert(JSON.stringify(faqMenu?.payload?.reply_markup || {}).includes("faqsec:management"), "FAQ menu must expose director/payroll section");
assert(JSON.stringify(faqMenu?.payload?.reply_markup || {}).includes("Директор і зарплатня"), "FAQ menu must label director/payroll section");

calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest(callbackUpdate(24, 321, "faq:management_payroll")), env);
assert(response.status === 200, "management payroll FAQ callback must succeed");
const managementPayrollAnswer = calls.find((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "321");
assert(/ставку за період/.test(managementPayrollAnswer?.payload?.text || ""), "payroll FAQ must describe the current remuneration options");
assert(/касову зміну/.test(managementPayrollAnswer?.payload?.text || ""), "payroll FAQ must explain shift-based working time");
assert(/не податковий або регламентований кадровий розрахунок/.test(managementPayrollAnswer?.payload?.text || ""), "payroll FAQ must preserve the management-only boundary");

// Bug-report action must request useful diagnostics without requesting secrets.
calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest(callbackUpdate(21, 321, "error:start")), env);
assert(response.status === 200, "bug-report callback must succeed");
const bugPrompt = calls.find((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "321");
assert(/версію OutPOSt/i.test(bugPrompt?.payload?.text || ""), "bug prompt must request OutPOSt version");
assert(/Не надсилайте паролі/i.test(bugPrompt?.payload?.text || ""), "bug prompt must warn against secrets");
assert(bugPrompt?.payload?.reply_markup?.force_reply === true, "bug prompt must use ForceReply");

// Update subscription stores only the technical chat ID and baselines both product versions.
calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest(callbackUpdate(22, 555, "updates:subscribe")), env);
assert(response.status === 200, "update subscription must succeed");
assert(analyticsDb.subscribers.has("555"), "subscriber chat ID must be persisted");
let releaseCursor = JSON.parse(analyticsDb.subscribers.get("555").last_notified_version);
assert(releaseCursor.outpost === "0.24.2", "subscription must baseline current OutPOSt release");
assert(releaseCursor.accounting === "0.402.3", "subscription must baseline current Accounting release");
const subscriptionMessage = calls.find((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "555");
assert(/Підписку активовано/.test(subscriptionMessage?.payload?.text || ""), "subscriber must receive confirmation");
assert(/OutPOSt: v0\.24\.2/.test(subscriptionMessage?.payload?.text || ""), "subscription confirmation must name OutPOSt version");
assert(/Бухгалтерія: v0\.402\.3/.test(subscriptionMessage?.payload?.text || ""), "subscription confirmation must name Accounting version separately");

// Same versions must never notify the subscriber again.
calls.length = 0;
let releaseResult = await telegram.maybeNotifyTelegramRelease({ ...env, TELEGRAM_PUBLIC_ENABLED: "1" });
assert(releaseResult.version === "0.24.2", "release checker must preserve the OutPOSt compatibility version");
assert(releaseResult.versions.accounting === "0.402.3", "release checker must read the Accounting version independently");
assert(releaseResult.delivered === 0, "same releases must not be redelivered");
assert(!calls.some((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "555"), "same releases must not send Telegram message");

// A newer OutPOSt release is delivered once and must not masquerade as Accounting.
currentVersion = "0.24.3";
calls.length = 0;
releaseResult = await telegram.maybeNotifyTelegramRelease({ ...env, TELEGRAM_PUBLIC_ENABLED: "1" });
assert(releaseResult.version === "0.24.3" && releaseResult.delivered === 1, "new OutPOSt release must be delivered once");
const outpostReleaseCall = calls.find((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "555");
assert(/Вийшла нова версія OutPOSt v0\.24\.3/.test(outpostReleaseCall?.payload?.text || ""), "OutPOSt notification must name OutPOSt and target version");
assert(!/OutPOSt Бухгалтерія/.test(outpostReleaseCall?.payload?.text || ""), "OutPOSt notification must not be labeled as Accounting");
releaseCursor = JSON.parse(analyticsDb.subscribers.get("555").last_notified_version);
assert(releaseCursor.outpost === "0.24.3" && releaseCursor.accounting === "0.402.3", "OutPOSt delivery must advance only OutPOSt cursor");

// A newer Accounting release gets its own product name, version and buttons.
currentAccountingVersion = "0.402.4";
calls.length = 0;
releaseResult = await telegram.maybeNotifyTelegramRelease({ ...env, TELEGRAM_PUBLIC_ENABLED: "1" });
assert(releaseResult.delivered === 1 && releaseResult.delivered_by_product.accounting === 1, "new Accounting release must be delivered once");
const accountingReleaseCall = calls.find((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "555");
assert(/Вийшла нова версія OutPOSt Бухгалтерія v0\.402\.4/.test(accountingReleaseCall?.payload?.text || ""), "Accounting notification must name Accounting and its own version");
assert(JSON.stringify(accountingReleaseCall?.payload?.reply_markup || {}).includes("Завантажити Бухгалтерію"), "Accounting notification must use Accounting-specific download button");
releaseCursor = JSON.parse(analyticsDb.subscribers.get("555").last_notified_version);
assert(releaseCursor.outpost === "0.24.3" && releaseCursor.accounting === "0.402.4", "Accounting delivery must advance only Accounting cursor");

// Concurrent release checks must use compare-and-swap so one release produces one message.
currentVersion = "0.24.4";
calls.length = 0;
const concurrentResults = await Promise.all([
  telegram.maybeNotifyTelegramRelease({ ...env, TELEGRAM_PUBLIC_ENABLED: "1" }),
  telegram.maybeNotifyTelegramRelease({ ...env, TELEGRAM_PUBLIC_ENABLED: "1" })
]);
const concurrentDelivered = concurrentResults.reduce((sum, item) => sum + Number(item.delivered || 0), 0);
const concurrentMessages = calls.filter((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "555" && /v0\.24\.4/.test(call.payload.text || ""));
assert(concurrentDelivered === 1, "parallel checks must claim a release only once");
assert(concurrentMessages.length === 1, "parallel checks must not duplicate the same Telegram release message");

// A production rollback must never be announced as a newer release.
currentVersion = "0.24.3";
calls.length = 0;
releaseResult = await telegram.maybeNotifyTelegramRelease({ ...env, TELEGRAM_PUBLIC_ENABLED: "1" });
assert(releaseResult.delivered === 0, "rollback to an older OutPOSt release must not be announced");
assert(!calls.some((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "555"), "rollback must not send Telegram release message");
currentVersion = "0.24.4";

// Legacy one-product state is upgraded silently and must not retroactively announce Accounting.
analyticsDb.subscribers.set("777", {
  chat_id: "777",
  subscribed_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  last_notified_version: "0.24.4"
});
calls.length = 0;
releaseResult = await telegram.maybeNotifyTelegramRelease({ ...env, TELEGRAM_PUBLIC_ENABLED: "1" });
assert(!calls.some((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "777"), "legacy subscriber must not receive a retroactive Accounting notification");
const migratedLegacyCursor = JSON.parse(analyticsDb.subscribers.get("777").last_notified_version);
assert(migratedLegacyCursor.outpost === "0.24.4" && migratedLegacyCursor.accounting === "0.402.4", "legacy state must migrate to independent product cursors");

// Unsubscribe must remove the chat ID from storage.
calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest(callbackUpdate(23, 555, "updates:unsubscribe")), env);
assert(response.status === 200, "unsubscribe callback must succeed");
assert(!analyticsDb.subscribers.has("555"), "unsubscribe must delete chat ID");

// Customer text still creates an admin routing card and acknowledgement.
calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest({
  update_id: 30,
  message: {
    message_id: 30,
    from: { id: 321, first_name: "Client", username: "client", is_bot: false },
    chat: { id: 321, type: "private" },
    text: "Потрібна допомога з ПРРО",
    reply_to_message: { text: "Категорія: ПРРО\nНапишіть ваше питання одним повідомленням." }
  }
}), env);
assert(response.status === 200, "customer webhook must succeed");
const adminCard = calls.find((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "9001");
assert(adminCard, "customer message must be routed to admin");
assert(adminCard.payload.text.includes("ПРРО"), "admin card must include category");
assert(adminCard.payload.text.includes("#outpost_user_321"), "admin card must include reply marker");

// Admin Reply routes back to the customer.
calls.length = 0;
response = await telegram.handleTelegramWebhook(webhookRequest({
  update_id: 31,
  message: {
    message_id: 31,
    from: { id: 9001, first_name: "Admin", is_bot: false },
    chat: { id: 9001, type: "private" },
    text: "Перевірте налаштування каси.",
    reply_to_message: { text: "🔔 Нове звернення\n#outpost_user_321" }
  }
}), env);
assert(response.status === 200, "admin reply webhook must succeed");
assert(calls.some((call) => call.method === "sendMessage" && String(call.payload.chat_id) === "321" && /Перевірте/.test(call.payload.text)), "admin reply must be delivered to customer");

// Public contact stays disabled until the explicit final switch is enabled.
calls.length = 0;
let healthResponse = telegram.handleTelegramHealth(new Request("https://outpost.com.ua/api/telegram/health"), env);
let healthBody = await responseJson(healthResponse);
assert(healthResponse.status === 200 && healthBody.enabled === false, "health must stay disabled before final switch");
const readyEnv = { ...env, TELEGRAM_PUBLIC_ENABLED: "1" };
healthResponse = telegram.handleTelegramHealth(new Request("https://outpost.com.ua/api/telegram/health"), readyEnv);
healthBody = await responseJson(healthResponse);
assert(healthBody.enabled === true, "health must enable only with configuration plus explicit switch");

// Setup endpoint requires its own secret header and configures commands for the richer bot.
calls.length = 0;
response = await telegram.handleTelegramSetup(new Request("https://outpost.com.ua/api/telegram/setup", {
  method: "POST",
  headers: { "x-outpost-telegram-setup-key": env.TELEGRAM_SETUP_KEY }
}), env);
const setupBody = await responseJson(response);
assert(response.status === 200 && setupBody.ok === true, "authorized setup must succeed");
const setWebhook = calls.find((call) => call.method === "setWebhook");
assert(setWebhook, "setup must call setWebhook");
assert(setWebhook.payload.url === "https://outpost.com.ua/api/telegram/webhook", "setup must use canonical webhook URL");
assert(setWebhook.payload.secret_token === env.TELEGRAM_WEBHOOK_SECRET, "setup must configure webhook secret token");
const commandCall = calls.find((call) => call.method === "setMyCommands");
assert(commandCall, "setup must configure commands");
const commands = JSON.stringify(commandCall.payload.commands || []);
for (const command of ["faq", "updates", "download", "support"]) {
  assert(commands.includes(`\"command\":\"${command}\"`), `setup must expose /${command}`);
}
const downloadCommand = (commandCall.payload.commands || []).find((item) => item.command === "download");
assert(downloadCommand?.description === "Поточні версії програм", "/download command must describe both products, not only OutPOSt");

console.log("Telegram support tests: PASS");
