import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { TELEGRAM_FAQ_SECTIONS } from "../site/_telegram-faq.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUTPUT = path.join(ROOT, "site", "support.html");
const CHECK = process.argv.includes("--check");
const PUBLIC_EMAIL_HREF = "mailto:roman@outpost.com.ua";
const PUBLIC_PHONE_HREF = "tel:+380993210872";

const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

// Three public Support-only questions appear below the shared Telegram FAQ.
// Include them in FAQPage schema so every visible <details> has a truthful Q/A pair.
const SUPPORT_ONLY_FAQ = Object.freeze([
  {
    question: "Які дані корисно додати до звернення?",
    answer: "Вкажіть версію OutPOSt, точний текст помилки, що саме робили безпосередньо перед нею, і за можливості додайте скріншот. Для MINI‑T400ME також корисні COM-порт і результат перевірки зв’язку."
  },
  {
    question: "Чи потрібно надсилати робочу базу магазину?",
    answer: "Зазвичай ні. Діагностичний пакет і текстове звернення мають спочатку дати достатньо технічної інформації без передачі товарів, клієнтів, PIN, секретів або повної SQLite-бази."
  },
  {
    question: "Що робити при невизначеному фіскальному результаті?",
    answer: "Не повторюйте чек або повернення навмання. Спочатку перевірте стан черги/recovery та зафіксуйте текст помилки. Для фіскальних інтеграцій важливо встановити, чи документ уже був створений зовнішнім сервісом або РРО."
  }
]);

// Outage and backup FAQ is public-site only; it is not part of Telegram bot content.
const RESERVE_FAQ = Object.freeze([
  {
    id: "reserve_power",
    question: "Що робити, якщо вимкнули світло й основний касовий ПК недоступний?",
    answer: "Якщо резервна каса OutPOSt була підготовлена заздалегідь, на телефоні можна знайти товари за локальним каталогом, перевірити останню синхронізовану ціну, сформувати кошик і зберегти резервний запис. Коли Windows-каса знову працюватиме, записи потрібно звірити й опрацювати в основній програмі."
  },
  {
    id: "reserve_offline",
    question: "Чи працює резервна каса без мобільного Інтернету?",
    answer: "Після попереднього завантаження каталог зберігається на телефоні й може бути доступний при тимчасовій втраті зв’язку. Резервні записи зберігаються локально до синхронізації. Без попередньої підготовки гарантувати наявність каталогу не можна; після відновлення зв’язку перевірте час останнього оновлення."
  },
  {
    id: "reserve_fiscal",
    question: "Чи є резервний запис фіскальним чеком?",
    answer: "Ні. Резервний запис із телефона не є фіскальним чеком і не замінює РРО або ПРРО. Перш ніж переносити чи проводити операцію після відновлення основної каси, звірте її стан та фіскальний статус, щоб уникнути дублювання продажу або повторної фіскалізації."
  }
]);
const faqEntities = () => [
  ...Object.values(TELEGRAM_FAQ_SECTIONS).flatMap((section) => section.items),
  ...SUPPORT_ONLY_FAQ,
  ...RESERVE_FAQ,
].map((item) => ({
  "@type": "Question",
  name: item.question,
  acceptedAnswer: { "@type": "Answer", text: item.answer }
}));

function faqSchema() {
  return JSON.stringify({
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebPage",
        "@id": "https://outpost.com.ua/support#webpage",
        url: "https://outpost.com.ua/support",
        name: "Підтримка OutPOSt — FAQ, оновлення та допомога",
        description: "Центр підтримки OutPOSt: FAQ про ліцензію, ПРРО, Кабінет директора, зарплатню, Бухгалтерію, MINI-T400, оновлення, резервні копії та типові помилки.",
        inLanguage: "uk",
        isPartOf: { "@id": "https://outpost.com.ua/#website" },
        about: { "@id": "https://outpost.com.ua/#software" },
        breadcrumb: { "@id": "https://outpost.com.ua/support#breadcrumb" }
      },
      {
        "@type": "BreadcrumbList",
        "@id": "https://outpost.com.ua/support#breadcrumb",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Головна", item: "https://outpost.com.ua/" },
          { "@type": "ListItem", position: 2, name: "Підтримка", item: "https://outpost.com.ua/support" }
        ]
      },
      {
        "@type": "FAQPage",
        "@id": "https://outpost.com.ua/support#faq",
        mainEntity: faqEntities()
      }
    ]
  });
}

const navItems = [
  ["license-faq", "Ліцензія"],
  ["fiscal-faq", "ПРРО / CheckBox"],
  ["mini-faq", "MINI‑T400ME"],
  ["accounting-faq", "Бухгалтерія"],
  ["management-faq", "Директор і зарплатня"],
  ["excise-faq", "еАкциз"],
  ["updates-faq", "Оновлення й база"],
  ["reserve-faq", "Резервна каса"],
  ["errors-faq", "Помилки"]
];

function supportNavHtml() {
  return `<nav class="support-nav">${navItems.map(([id, label]) =>
    `<a href="#${id}">${escapeHtml(label)}</a>`
  ).join("")}</nav>`;
}

function detailsHtml(items) {
  return items.map((item) =>
    `<details data-faq-id="${escapeHtml(item.id)}"><summary>${escapeHtml(item.question)}</summary><p>${escapeHtml(item.answer)}</p></details>`
  ).join("");
}

function groupHtml(id, title, items) {
  const reserveGuide = id === "reserve-faq"
    ? '<p><a href="/offline-programa-dlya-magazynu#reserve-cash">Детальний порядок роботи з резервною касою →</a></p>'
    : "";
  return `<section class="support-group" id="${id}"><h2>${escapeHtml(title)}</h2><div class="faq-compact">${detailsHtml(items)}</div>${reserveGuide}</section>`;
}

function supportGroupsHtml() {
  const programItems = TELEGRAM_FAQ_SECTIONS.program.items;
  const updateItems = programItems.filter((item) => item.id !== "program_bug");
  const errorItems = programItems.filter((item) => item.id === "program_bug");
  if (!errorItems.length) throw new Error("Telegram FAQ program_bug item is missing");

  return [
    groupHtml("license-faq", "Ліцензія та оплата", TELEGRAM_FAQ_SECTIONS.license.items),
    groupHtml("fiscal-faq", "ПРРО та CheckBox", TELEGRAM_FAQ_SECTIONS.prro.items),
    groupHtml("mini-faq", "MINI‑T400ME", TELEGRAM_FAQ_SECTIONS.mini.items),
    groupHtml("accounting-faq", "Бухгалтерія", TELEGRAM_FAQ_SECTIONS.accounting.items),
    groupHtml("management-faq", "Кабінет директора та зарплатня", TELEGRAM_FAQ_SECTIONS.management.items),
    groupHtml("excise-faq", "еАкциз / XTrace", TELEGRAM_FAQ_SECTIONS.eakcyz.items),
    groupHtml("updates-faq", "Оновлення, база та резервні копії", updateItems),
    groupHtml("reserve-faq", "Резервна каса та відключення світла", RESERVE_FAQ),
    groupHtml("errors-faq", "Помилки та звернення в підтримку", errorItems)
  ].join("\n");
}

function replaceExactlyOnce(source, pattern, replacement, label) {
  const matches = source.match(pattern);
  if (!matches || matches.length !== 1) {
    throw new Error(`${label}: expected exactly one match, got ${matches?.length ?? 0}`);
  }
  return source.replace(pattern, replacement);
}

function synchronize(source) {
  let next = source;

  next = replaceExactlyOnce(
    next,
    /<script type="application\/ld\+json">[\s\S]*?<\/script>/g,
    `<script type="application/ld+json">${faqSchema()}</script>`,
    "support JSON-LD"
  );

  next = replaceExactlyOnce(
    next,
    /<nav class="support-nav">[\s\S]*?<\/nav>/g,
    supportNavHtml(),
    "support FAQ navigation"
  );

  const startToken = '<div class="support-groups">';
  const endToken = '</div></div></section><section class="dense-section soft seo-depth-section">';
  const start = next.indexOf(startToken);
  const end = next.indexOf(endToken, start + startToken.length);
  if (start < 0 || end < 0 || next.indexOf(startToken, start + 1) >= 0) {
    throw new Error("support FAQ groups boundary is missing or ambiguous");
  }

  next = next.slice(0, start)
    + startToken + "\n" + supportGroupsHtml() + "\n"
    + next.slice(end);

  return next;
}

const current = await readFile(OUTPUT, "utf8").catch(() => "");
if (!current) {
  console.error("site/support.html is missing");
  process.exit(1);
}

if (!current.includes(PUBLIC_EMAIL_HREF)) throw new Error("Support Center shell lacks current public email");
if (!current.includes(PUBLIC_PHONE_HREF)) throw new Error("Support Center shell lacks current public phone");

const expected = synchronize(current);

if (CHECK) {
  if (current !== expected) {
    console.error("support.html FAQ content is not synchronized with _telegram-faq.js. Run: node scripts/generate_support_center.mjs");
    process.exit(1);
  }
  console.log(`Support Center: synchronized (${faqEntities().length} FAQ items, v20 shell preserved)`);
} else {
  await writeFile(OUTPUT, expected, "utf8");
  console.log(`Support Center: generated (${faqEntities().length} FAQ items, v20 shell preserved)`);
}
