import { TELEGRAM_FAQ_SECTIONS, TELEGRAM_FAQ_BY_ID } from "./_telegram-faq.js";

const TELEGRAM_API_ORIGIN = "https://api.telegram.org";
const BOT_USERNAME = "OutPOStUA_bot";
const WEBHOOK_PATH = "/api/telegram/webhook";
const SETUP_PATH = "/api/telegram/setup";
const HEALTH_PATH = "/api/telegram/health";
const USER_MARKER = /#outpost_user_(-?\d+)/;
const OUTPOST_RELEASE_VERSION_RE = /OutPOSt-Setup-v(\d+\.\d+\.\d+)\.exe/g;
const ACCOUNTING_RELEASE_VERSION_RE = /OutPOSt-Accounting-Setup-v(\d+\.\d+\.\d+)\.exe/g;

const RELEASE_PRODUCTS = Object.freeze({
  outpost: {
    label: "OutPOSt",
    emoji: "🚀",
    downloadText: "⬇️ Завантажити OutPOSt",
    detailsText: "📝 Що нового",
    detailsUrl: "https://outpost.com.ua/changelog"
  },
  accounting: {
    label: "OutPOSt Бухгалтерія",
    emoji: "📊",
    downloadText: "⬇️ Завантажити Бухгалтерію",
    detailsText: "📘 Про Бухгалтерію",
    detailsUrl: "https://outpost.com.ua/buhgalteriya"
  }
});

const CATEGORIES = {
  support: { label: "Техпідтримка", prompt: "Категорія: Техпідтримка\nНапишіть ваше питання одним повідомленням." },
  purchase: { label: "Покупка / ліцензія", prompt: "Категорія: Покупка / ліцензія\nНапишіть ваше питання одним повідомленням." },
  prro: { label: "ПРРО", prompt: "Категорія: ПРРО\nНапишіть ваше питання одним повідомленням." },
  eakcyz: { label: "еАкциз", prompt: "Категорія: еАкциз\nНапишіть ваше питання одним повідомленням." },
  accounting: { label: "Бухгалтерія", prompt: "Категорія: Бухгалтерія\nНапишіть ваше питання одним повідомленням." }
};

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}

function safeEqual(a, b) {
  const left = String(a || "");
  const right = String(b || "");
  if (!left || left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i += 1) diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return diff === 0;
}

function requireSecret(env, name) {
  const value = env?.[name];
  if (!value) throw new Error(`missing ${name}`);
  return String(value);
}

async function telegramApi(env, method, payload = {}) {
  const token = requireSecret(env, "TELEGRAM_BOT_TOKEN");
  const response = await fetch(`${TELEGRAM_API_ORIGIN}/bot${token}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data?.ok) throw new Error(`Telegram ${method} failed`);
  return data.result;
}

function mainKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: "📚 FAQ", callback_data: "nav:faq" },
        { text: "🔔 Оновлення програм", callback_data: "updates:menu" }
      ],
      [
        { text: "⬇️ Поточні версії", callback_data: "download:current" },
        { text: "🐞 Повідомити про помилку", callback_data: "error:start" }
      ],
      [{ text: "👨‍💻 Написати в підтримку", callback_data: "nav:support" }]
    ]
  };
}

function supportKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: "🛠 Техпідтримка", callback_data: "cat:support" },
        { text: "💳 Покупка", callback_data: "cat:purchase" }
      ],
      [
        { text: "🧾 ПРРО", callback_data: "cat:prro" },
        { text: "🏷 еАкциз", callback_data: "cat:eakcyz" }
      ],
      [{ text: "📊 Бухгалтерія", callback_data: "cat:accounting" }],
      [{ text: "⬅️ Головне меню", callback_data: "nav:main" }]
    ]
  };
}

function faqSectionsKeyboard() {
  const sectionButtons = Object.entries(TELEGRAM_FAQ_SECTIONS).map(([key, section]) => [
    { text: section.label, callback_data: `faqsec:${key}` }
  ]);
  sectionButtons.push([{ text: "⬅️ Головне меню", callback_data: "nav:main" }]);
  return { inline_keyboard: sectionButtons };
}

function faqItemsKeyboard(sectionKey) {
  const section = TELEGRAM_FAQ_SECTIONS[sectionKey];
  if (!section) return faqSectionsKeyboard();
  return {
    inline_keyboard: [
      ...section.items.map((item) => [{ text: item.question, callback_data: `faq:${item.id}` }]),
      [{ text: "⬅️ До розділів FAQ", callback_data: "nav:faq" }],
      [{ text: "🏠 Головне меню", callback_data: "nav:main" }]
    ]
  };
}

function faqAnswerKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: "✅ Допомогло", callback_data: "faq:yes" },
        { text: "❓ Не допомогло", callback_data: "faq:no" }
      ],
      [{ text: "📚 До FAQ", callback_data: "nav:faq" }]
    ]
  };
}

function updatesKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: "🔔 Підписатися", callback_data: "updates:subscribe" },
        { text: "🔕 Відписатися", callback_data: "updates:unsubscribe" }
      ],
      [{ text: "⬇️ Поточні версії", callback_data: "download:current" }],
      [{ text: "⬅️ Головне меню", callback_data: "nav:main" }]
    ]
  };
}

function releaseLinksKeyboard(productKey = "outpost", includeUnsubscribe = false) {
  const product = RELEASE_PRODUCTS[productKey] || RELEASE_PRODUCTS.outpost;
  const rows = [
    [
      { text: product.downloadText, url: "https://outpost.com.ua/download" },
      { text: product.detailsText, url: product.detailsUrl }
    ]
  ];
  if (includeUnsubscribe) rows.push([{ text: "🔕 Відписатися", callback_data: "updates:unsubscribe" }]);
  rows.push([{ text: "🏠 Головне меню", callback_data: "nav:main" }]);
  return { inline_keyboard: rows };
}

function currentVersionsKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: "⬇️ Завантажити OutPOSt", url: "https://outpost.com.ua/download" },
        { text: "📝 Що нового OutPOSt", url: "https://outpost.com.ua/changelog" }
      ],
      [
        { text: "⬇️ Завантажити Бухгалтерію", url: "https://outpost.com.ua/download" },
        { text: "📘 Про Бухгалтерію", url: "https://outpost.com.ua/buhgalteriya" }
      ],
      [{ text: "🏠 Головне меню", callback_data: "nav:main" }]
    ]
  };
}

async function sendStart(env, chatId) {
  return telegramApi(env, "sendMessage", {
    chat_id: chatId,
    text: "Вітаємо у підтримці OutPOSt. Тут можна знайти відповідь у FAQ, перевірити актуальну версію, підписатися на релізи або написати оператору.",
    reply_markup: mainKeyboard()
  });
}

async function sendSupportMenu(env, chatId) {
  return telegramApi(env, "sendMessage", {
    chat_id: chatId,
    text: "Оберіть тему звернення. Після цього одним повідомленням опишіть питання — воно буде передане оператору OutPOSt.",
    reply_markup: supportKeyboard()
  });
}

async function sendFaqMenu(env, chatId) {
  return telegramApi(env, "sendMessage", {
    chat_id: chatId,
    text: "📚 FAQ OutPOSt\n\nОберіть розділ із найпоширенішими запитаннями.",
    reply_markup: faqSectionsKeyboard()
  });
}

async function sendFaqSection(env, chatId, sectionKey) {
  const section = TELEGRAM_FAQ_SECTIONS[sectionKey];
  if (!section) return sendFaqMenu(env, chatId);
  return telegramApi(env, "sendMessage", {
    chat_id: chatId,
    text: `${section.label}\n\nОберіть запитання:`,
    reply_markup: faqItemsKeyboard(sectionKey)
  });
}

async function sendFaqAnswer(env, chatId, itemId) {
  const item = TELEGRAM_FAQ_BY_ID[itemId];
  if (!item) return sendFaqMenu(env, chatId);
  return telegramApi(env, "sendMessage", {
    chat_id: chatId,
    text: `❓ ${item.question}\n\n${item.answer}`,
    reply_markup: faqAnswerKeyboard()
  });
}

function releaseVersionFromHtml(html, pattern, label, required = true) {
  const versions = new Set(Array.from(html.matchAll(pattern), (match) => match[1]));
  if (!required && versions.size === 0) return null;
  if (versions.size !== 1) throw new Error(`${label}_release_ambiguous`);
  return [...versions][0];
}

async function currentReleaseVersions(env) {
  if (!env?.ASSETS?.fetch) throw new Error("assets_binding_unavailable");
  const response = await env.ASSETS.fetch(new Request("https://outpost.com.ua/download.html"));
  if (!response.ok) throw new Error("download_page_unavailable");
  const html = await response.text();
  return {
    outpost: releaseVersionFromHtml(html, OUTPOST_RELEASE_VERSION_RE, "outpost"),
    accounting: releaseVersionFromHtml(html, ACCOUNTING_RELEASE_VERSION_RE, "accounting", false)
  };
}

async function currentReleaseVersion(env) {
  return (await currentReleaseVersions(env)).outpost;
}

function versionTuple(value) {
  const parts = String(value || "").split(".");
  if (parts.length !== 3 || parts.some((part) => !/^\d+$/.test(part))) return null;
  return parts.map(Number);
}

function isNewerRelease(current, previous) {
  const next = versionTuple(current);
  const prior = versionTuple(previous);
  if (!next) return false;
  if (!prior) return true;
  for (let i = 0; i < 3; i += 1) {
    if (next[i] > prior[i]) return true;
    if (next[i] < prior[i]) return false;
  }
  return false;
}

function releaseCursorFromStorage(raw, current) {
  const text = String(raw || "").trim();
  if (versionTuple(text)) {
    return { outpost: text, accounting: current.accounting || null };
  }
  try {
    const parsed = JSON.parse(text);
    return {
      outpost: versionTuple(parsed?.outpost) ? parsed.outpost : current.outpost,
      accounting: versionTuple(parsed?.accounting) ? parsed.accounting : (current.accounting || null)
    };
  } catch {
    return { outpost: current.outpost, accounting: current.accounting || null };
  }
}

function serializeReleaseCursor(cursor) {
  return JSON.stringify({
    outpost: versionTuple(cursor?.outpost) ? cursor.outpost : null,
    accounting: versionTuple(cursor?.accounting) ? cursor.accounting : null
  });
}

function pendingReleaseProducts(current, previous) {
  return Object.keys(RELEASE_PRODUCTS).filter((key) => {
    const nextVersion = current?.[key];
    return Boolean(nextVersion && isNewerRelease(nextVersion, previous?.[key]));
  });
}

function releaseNotificationText(productKey, version) {
  if (productKey === "accounting") {
    return `📊 Вийшла нова версія OutPOSt Бухгалтерія v${version}.\n\nОновлення Бухгалтерії вже опубліковане на офіційному сайті. Бухгалтерія має власну версію та поки встановлюється окремо від основного OutPOSt. Перед важливим оновленням рекомендуємо мати актуальну резервну копію даних.`;
  }
  return `🚀 Вийшла нова версія OutPOSt v${version}.\n\nОновлення OutPOSt вже опубліковане на офіційному сайті. Перед важливим оновленням рекомендуємо мати актуальну резервну копію даних.`;
}

async function claimSubscriberCursor(env, chatId, expectedCursor, nextCursor) {
  if (expectedCursor === nextCursor) return false;
  const result = await env.ANALYTICS_DB.prepare(`
    UPDATE telegram_update_subscribers
    SET last_notified_version = ?, updated_at = ?
    WHERE chat_id = ? AND last_notified_version = ?
  `).bind(nextCursor, new Date().toISOString(), chatId, expectedCursor).run();
  return Number(result?.meta?.changes || 0) === 1;
}

async function sendDownloadInfo(env, chatId) {
  let versions = null;
  try { versions = await currentReleaseVersions(env); } catch {}
  const versionLines = versions
    ? [
        `OutPOSt: v${versions.outpost}`,
        ...(versions.accounting ? [`Бухгалтерія: v${versions.accounting}`] : [])
      ]
    : [];
  const headline = versionLines.length
    ? `⬇️ Поточні версії\n${versionLines.join("\n")}`
    : "⬇️ Поточні версії OutPOSt";
  return telegramApi(env, "sendMessage", {
    chat_id: chatId,
    text: `${headline}\n\nЗавантажуйте програми тільки з офіційного сайту OutPOSt. На сторінці завантаження також публікуються SHA-256 інсталяторів.`,
    reply_markup: currentVersionsKeyboard()
  });
}

async function ensureUpdateSubscriptionTable(env) {
  if (!env?.ANALYTICS_DB) throw new Error("analytics_db_unavailable");
  await env.ANALYTICS_DB.prepare(`
    CREATE TABLE IF NOT EXISTS telegram_update_subscribers (
      chat_id TEXT PRIMARY KEY,
      subscribed_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      last_notified_version TEXT NOT NULL
    )
  `).run();
}

async function isUpdateSubscriber(env, chatId) {
  await ensureUpdateSubscriptionTable(env);
  const row = await env.ANALYTICS_DB.prepare(`
    SELECT chat_id
    FROM telegram_update_subscribers
    WHERE chat_id = ?
    LIMIT 1
  `).bind(String(chatId)).first();
  return Boolean(row?.chat_id);
}

async function subscribeToUpdates(env, chatId) {
  await ensureUpdateSubscriptionTable(env);
  const versions = await currentReleaseVersions(env);
  const cursor = serializeReleaseCursor(versions);
  const now = new Date().toISOString();
  await env.ANALYTICS_DB.prepare(`
    INSERT INTO telegram_update_subscribers
      (chat_id, subscribed_at, updated_at, last_notified_version)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(chat_id) DO UPDATE SET
      updated_at = excluded.updated_at,
      last_notified_version = excluded.last_notified_version
  `).bind(String(chatId), now, now, cursor).run();
  return versions;
}

async function unsubscribeFromUpdates(env, chatId) {
  await ensureUpdateSubscriptionTable(env);
  await env.ANALYTICS_DB.prepare(`
    DELETE FROM telegram_update_subscribers
    WHERE chat_id = ?
  `).bind(String(chatId)).run();
}

async function sendUpdatesMenu(env, chatId) {
  let versions = null;
  let subscribed = false;
  try {
    versions = await currentReleaseVersions(env);
    subscribed = await isUpdateSubscriber(env, chatId);
  } catch {}
  const versionLines = versions
    ? [
        `OutPOSt: v${versions.outpost}`,
        ...(versions.accounting ? [`Бухгалтерія: v${versions.accounting}`] : [])
      ].join("\n") + "\n"
    : "";
  const statusLine = subscribed ? "Статус: ✅ ви підписані." : "Статус: підписка не активна.";
  return telegramApi(env, "sendMessage", {
    chat_id: chatId,
    text: `🔔 Оновлення програм OutPOSt\n\n${versionLines}${statusLine}\n\nБот відстежує OutPOSt і Бухгалтерію окремо та надсилає повідомлення лише про той продукт, у якого з’явилася новіша версія. Зберігається лише ваш Telegram chat ID і технічний стан підписки.`,
    reply_markup: updatesKeyboard()
  });
}

async function sendErrorPrompt(env, chatId) {
  return telegramApi(env, "sendMessage", {
    chat_id: chatId,
    text: "Діагностика помилки OutPOSt\n\nНапишіть одним повідомленням:\n1) версію OutPOSt, якщо знаєте;\n2) що саме робили перед помилкою;\n3) точний текст помилки.\n\nМожна прикріпити скріншот або файл. Не надсилайте паролі, КЕП чи секретні ключі.",
    reply_markup: {
      force_reply: true,
      selective: true,
      input_field_placeholder: "Версія, дія, текст помилки…"
    }
  });
}

function categoryFromReply(message) {
  const prompt = message?.reply_to_message?.text || "";
  if (prompt.startsWith("Діагностика помилки OutPOSt")) return "Помилка / діагностика";
  for (const category of Object.values(CATEGORIES)) {
    if (prompt.startsWith(`Категорія: ${category.label}`)) return category.label;
  }
  return "Загальне питання";
}

function displayName(from) {
  if (!from) return "Користувач Telegram";
  const name = [from.first_name, from.last_name].filter(Boolean).join(" ").trim() || "Користувач Telegram";
  return from.username ? `${name} (@${from.username})` : name;
}

function customerSummary(message, category) {
  const chatId = String(message.chat.id);
  const body = message.text || message.caption || "[Вкладення без тексту]";
  const clipped = body.length > 2500 ? `${body.slice(0, 2500)}…` : body;
  return [
    `🔔 Нове звернення OutPOSt · ${category}`,
    `Від: ${displayName(message.from)}`,
    `Chat ID: ${chatId}`,
    "",
    clipped,
    "",
    "↩️ Відповідай Reply саме на це повідомлення — бот надішле відповідь клієнту.",
    `#outpost_user_${chatId}`
  ].join("\n");
}

async function notifyAdmin(env, message, category) {
  const adminChatId = env?.TELEGRAM_ADMIN_CHAT_ID;
  if (!adminChatId) {
    await telegramApi(env, "sendMessage", {
      chat_id: message.chat.id,
      text: "Підтримка OutPOSt ще завершує налаштування. Спробуйте написати трохи пізніше."
    });
    return;
  }

  await telegramApi(env, "sendMessage", {
    chat_id: String(adminChatId),
    text: customerSummary(message, category)
  });

  if (!message.text && message.message_id) {
    await telegramApi(env, "copyMessage", {
      chat_id: String(adminChatId),
      from_chat_id: message.chat.id,
      message_id: message.message_id
    });
  }

  await telegramApi(env, "sendMessage", {
    chat_id: message.chat.id,
    text: "✅ Звернення передано. Відповідь прийде сюди в Telegram."
  });
}

async function relayAdminReply(env, message) {
  const repliedText = message?.reply_to_message?.text || message?.reply_to_message?.caption || "";
  const match = repliedText.match(USER_MARKER);
  if (!match) {
    await telegramApi(env, "sendMessage", {
      chat_id: message.chat.id,
      text: "Щоб відповісти клієнту, використай Reply на повідомленні бота з позначкою #outpost_user_."
    });
    return;
  }

  const targetChatId = match[1];
  if (message.text) {
    await telegramApi(env, "sendMessage", {
      chat_id: targetChatId,
      text: `Відповідь OutPOSt:\n\n${message.text}`
    });
  } else {
    await telegramApi(env, "copyMessage", {
      chat_id: targetChatId,
      from_chat_id: message.chat.id,
      message_id: message.message_id
    });
  }

  await telegramApi(env, "sendMessage", {
    chat_id: message.chat.id,
    text: "✅ Відповідь надіслано клієнту."
  });
}

async function handleMessage(env, message) {
  if (!message?.chat?.id || message.from?.is_bot) return;
  const chatId = String(message.chat.id);
  const text = (message.text || "").trim();
  const adminChatId = env?.TELEGRAM_ADMIN_CHAT_ID ? String(env.TELEGRAM_ADMIN_CHAT_ID) : null;

  if (/^\/whoami(?:@\w+)?$/i.test(text)) {
    await telegramApi(env, "sendMessage", { chat_id: chatId, text: `Ваш Telegram chat ID: ${chatId}` });
    return;
  }

  if (/^\/(?:start|help)(?:@\w+)?(?:\s+.*)?$/i.test(text)) {
    await sendStart(env, chatId);
    return;
  }
  if (/^\/faq(?:@\w+)?$/i.test(text)) {
    await sendFaqMenu(env, chatId);
    return;
  }
  if (/^\/updates(?:@\w+)?$/i.test(text)) {
    await sendUpdatesMenu(env, chatId);
    return;
  }
  if (/^\/download(?:@\w+)?$/i.test(text)) {
    await sendDownloadInfo(env, chatId);
    return;
  }
  if (/^\/support(?:@\w+)?$/i.test(text)) {
    await sendSupportMenu(env, chatId);
    return;
  }

  if (adminChatId && chatId === adminChatId) {
    await relayAdminReply(env, message);
    return;
  }

  if (message.chat.type && message.chat.type !== "private") return;
  await notifyAdmin(env, message, categoryFromReply(message));
}

async function handleCallback(env, callback) {
  if (!callback?.id || !callback.message?.chat?.id) return;
  const chatId = String(callback.message.chat.id);
  const data = String(callback.data || "");
  await telegramApi(env, "answerCallbackQuery", { callback_query_id: callback.id });

  if (data === "nav:main") return sendStart(env, chatId);
  if (data === "nav:support") return sendSupportMenu(env, chatId);
  if (data === "nav:faq") return sendFaqMenu(env, chatId);
  if (data === "download:current") return sendDownloadInfo(env, chatId);
  if (data === "error:start") return sendErrorPrompt(env, chatId);
  if (data === "updates:menu") return sendUpdatesMenu(env, chatId);

  if (data === "updates:subscribe") {
    try {
      const versions = await subscribeToUpdates(env, chatId);
      const versionLines = [
        `OutPOSt: v${versions.outpost}`,
        ...(versions.accounting ? [`Бухгалтерія: v${versions.accounting}`] : [])
      ].join("\n");
      return telegramApi(env, "sendMessage", {
        chat_id: chatId,
        text: `✅ Підписку активовано.\n\n${versionLines}\n\nБот відстежує версії окремо й повідомить тільки про той продукт, який оновився.`,
        reply_markup: updatesKeyboard()
      });
    } catch {
      return telegramApi(env, "sendMessage", {
        chat_id: chatId,
        text: "Не вдалося активувати підписку. Спробуйте трохи пізніше або напишіть у підтримку.",
        reply_markup: supportKeyboard()
      });
    }
  }

  if (data === "updates:unsubscribe") {
    try { await unsubscribeFromUpdates(env, chatId); } catch {}
    return telegramApi(env, "sendMessage", {
      chat_id: chatId,
      text: "🔕 Підписку на повідомлення про нові версії вимкнено. Telegram chat ID видалено зі списку підписників.",
      reply_markup: mainKeyboard()
    });
  }

  if (data === "faq:yes") {
    return telegramApi(env, "sendMessage", {
      chat_id: chatId,
      text: "✅ Добре. Якщо з’явиться інше питання — FAQ і підтримка завжди доступні з головного меню.",
      reply_markup: mainKeyboard()
    });
  }
  if (data === "faq:no") {
    return telegramApi(env, "sendMessage", {
      chat_id: chatId,
      text: "Тоді передамо питання людині. Оберіть тему звернення:",
      reply_markup: supportKeyboard()
    });
  }

  if (data.startsWith("faqsec:")) return sendFaqSection(env, chatId, data.slice("faqsec:".length));
  if (data.startsWith("faq:")) return sendFaqAnswer(env, chatId, data.slice("faq:".length));

  if (data.startsWith("cat:")) {
    const key = data.slice("cat:".length);
    const category = CATEGORIES[key];
    if (!category) return;
    return telegramApi(env, "sendMessage", {
      chat_id: chatId,
      text: category.prompt,
      reply_markup: {
        force_reply: true,
        selective: true,
        input_field_placeholder: "Опишіть питання…"
      }
    });
  }
}

export async function maybeNotifyTelegramRelease(env) {
  if (!env?.ANALYTICS_DB || !env?.ASSETS?.fetch || !env?.TELEGRAM_BOT_TOKEN) return { ok: true, skipped: true };
  if (String(env?.TELEGRAM_PUBLIC_ENABLED || "") !== "1") return { ok: true, skipped: true };

  await ensureUpdateSubscriptionTable(env);
  const versions = await currentReleaseVersions(env);
  const targetCursor = serializeReleaseCursor(versions);
  const pending = await env.ANALYTICS_DB.prepare(`
    SELECT chat_id, last_notified_version
    FROM telegram_update_subscribers
    WHERE last_notified_version <> ?
    ORDER BY subscribed_at
    LIMIT 100
  `).bind(targetCursor).all();
  const rows = (Array.isArray(pending?.results) ? pending.results : []).slice(0, 40);
  let delivered = 0;
  let claimed = 0;
  const deliveredByProduct = { outpost: 0, accounting: 0 };

  for (const row of rows) {
    const chatId = String(row?.chat_id || "");
    const storedCursor = String(row?.last_notified_version || "");
    if (!chatId || !storedCursor) continue;

    const previous = releaseCursorFromStorage(storedCursor, versions);
    const productKeys = pendingReleaseProducts(versions, previous);

    if (productKeys.length === 0) {
      const normalizedCursor = serializeReleaseCursor(previous);
      if (normalizedCursor !== storedCursor) {
        try { await claimSubscriberCursor(env, chatId, storedCursor, normalizedCursor); } catch {}
      }
      continue;
    }

    const next = { ...previous };
    for (const productKey of productKeys) next[productKey] = versions[productKey];
    const nextCursor = serializeReleaseCursor(next);

    let ownsClaim = false;
    try { ownsClaim = await claimSubscriberCursor(env, chatId, storedCursor, nextCursor); } catch {}
    if (!ownsClaim) continue;
    claimed += 1;

    const failedProducts = [];
    for (const productKey of productKeys) {
      try {
        await telegramApi(env, "sendMessage", {
          chat_id: chatId,
          text: releaseNotificationText(productKey, versions[productKey]),
          reply_markup: releaseLinksKeyboard(productKey, true)
        });
        delivered += 1;
        deliveredByProduct[productKey] += 1;
      } catch (error) {
        failedProducts.push(productKey);
        console.error(JSON.stringify({ event: "telegram_release_notify_failed", product: productKey, chat: chatId, name: error?.name || "Error" }));
      }
    }

    if (failedProducts.length) {
      const recovery = { ...next };
      for (const productKey of failedProducts) recovery[productKey] = previous[productKey];
      const recoveryCursor = serializeReleaseCursor(recovery);
      try { await claimSubscriberCursor(env, chatId, nextCursor, recoveryCursor); } catch {}
    }
  }

  return {
    ok: true,
    version: versions.outpost,
    versions,
    pending: rows.length,
    claimed,
    delivered,
    delivered_by_product: deliveredByProduct
  };
}

export async function handleTelegramWebhook(request, env) {
  if (request.method !== "POST") return jsonResponse({ ok: false, error: "method_not_allowed" }, 405);
  let webhookSecret;
  try {
    requireSecret(env, "TELEGRAM_BOT_TOKEN");
    webhookSecret = requireSecret(env, "TELEGRAM_WEBHOOK_SECRET");
  } catch {
    return jsonResponse({ ok: false, error: "telegram_not_configured" }, 503);
  }

  if (!safeEqual(request.headers.get("x-telegram-bot-api-secret-token"), webhookSecret)) {
    return jsonResponse({ ok: false, error: "unauthorized" }, 401);
  }

  const contentLength = Number(request.headers.get("content-length") || 0);
  if (contentLength > 1024 * 1024) return jsonResponse({ ok: false, error: "payload_too_large" }, 413);

  let update;
  try {
    update = await request.json();
  } catch {
    return jsonResponse({ ok: false, error: "invalid_json" }, 400);
  }

  try {
    if (update.callback_query) await handleCallback(env, update.callback_query);
    else if (update.message) await handleMessage(env, update.message);
    return jsonResponse({ ok: true });
  } catch (error) {
    console.error(JSON.stringify({ event: "telegram_support_error", name: error?.name || "Error" }));
    return jsonResponse({ ok: false, error: "telegram_processing_failed" }, 502);
  }
}

export function handleTelegramHealth(request, env) {
  if (request.method !== "GET") return jsonResponse({ ok: false, error: "method_not_allowed" }, 405);
  const configured = Boolean(env?.TELEGRAM_BOT_TOKEN && env?.TELEGRAM_WEBHOOK_SECRET && env?.TELEGRAM_ADMIN_CHAT_ID);
  const enabled = configured && String(env?.TELEGRAM_PUBLIC_ENABLED || "") === "1";
  return jsonResponse({ ok: true, enabled, bot: `@${BOT_USERNAME}` });
}

export async function handleTelegramSetup(request, env) {
  if (request.method !== "POST") return jsonResponse({ ok: false, error: "method_not_allowed" }, 405);

  let setupKey;
  let webhookSecret;
  try {
    requireSecret(env, "TELEGRAM_BOT_TOKEN");
    webhookSecret = requireSecret(env, "TELEGRAM_WEBHOOK_SECRET");
    setupKey = requireSecret(env, "TELEGRAM_SETUP_KEY");
  } catch {
    return jsonResponse({ ok: false, error: "telegram_not_configured" }, 503);
  }

  if (!safeEqual(request.headers.get("x-outpost-telegram-setup-key"), setupKey)) {
    return jsonResponse({ ok: false, error: "unauthorized" }, 401);
  }

  const webhookUrl = new URL(WEBHOOK_PATH, request.url).toString();
  try {
    await telegramApi(env, "setWebhook", {
      url: webhookUrl,
      secret_token: webhookSecret,
      allowed_updates: ["message", "callback_query"]
    });
    await telegramApi(env, "setMyCommands", {
      commands: [
        { command: "start", description: "Відкрити головне меню" },
        { command: "faq", description: "Популярні запитання" },
        { command: "updates", description: "Підписка на нові версії" },
        { command: "download", description: "Поточні версії програм" },
        { command: "support", description: "Написати в підтримку" },
        { command: "whoami", description: "Показати ваш Telegram chat ID" }
      ]
    });
    await telegramApi(env, "setMyDescription", {
      description: "Офіційний бот OutPOSt: FAQ, підтримка, ПРРО, еАкциз, Бухгалтерія та сповіщення про нові версії."
    });
    await telegramApi(env, "setMyShortDescription", {
      short_description: "OutPOSt — FAQ, підтримка та оновлення програми"
    });
    const info = await telegramApi(env, "getWebhookInfo");
    return jsonResponse({
      ok: true,
      bot: `@${BOT_USERNAME}`,
      webhook: info?.url || webhookUrl,
      pending_updates: info?.pending_update_count || 0
    });
  } catch (error) {
    console.error(JSON.stringify({ event: "telegram_setup_error", name: error?.name || "Error" }));
    return jsonResponse({ ok: false, error: "telegram_setup_failed" }, 502);
  }
}

export function isTelegramPath(pathname) {
  return pathname === WEBHOOK_PATH || pathname === SETUP_PATH || pathname === HEALTH_PATH;
}

export async function telegramPathResponse(request, env) {
  const pathname = new URL(request.url).pathname;
  if (pathname === WEBHOOK_PATH) return handleTelegramWebhook(request, env);
  if (pathname === SETUP_PATH) return handleTelegramSetup(request, env);
  if (pathname === HEALTH_PATH) return handleTelegramHealth(request, env);
  return null;
}
