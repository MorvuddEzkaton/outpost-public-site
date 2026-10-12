#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
MODULE = SITE / "_telegram-support.js"
FAQ = SITE / "_telegram-faq.js"
WORKER = SITE / "_worker.js"
SCRIPT = SITE / "script.js"
STYLES = SITE / "styles.css"
WORKFLOW = ROOT / ".github" / "workflows" / "public-site-smoke.yml"
DOCS = ROOT / "docs" / "TELEGRAM-SUPPORT.md"
JOURNAL = SITE / "_telegram-release-journal.js"
SCHEDULER = ROOT / "scripts" / "telegram_release_scheduler.mjs"

errors = []

for path in (MODULE, FAQ, WORKER, SCRIPT, STYLES, WORKFLOW, DOCS, JOURNAL, SCHEDULER):
    if not path.exists():
        errors.append(f"missing required file: {path.relative_to(ROOT)}")

if errors:
    print("Telegram support guard: FAIL")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

module = MODULE.read_text(encoding="utf-8")
faq = FAQ.read_text(encoding="utf-8")
worker = WORKER.read_text(encoding="utf-8")
script = SCRIPT.read_text(encoding="utf-8")
styles = STYLES.read_text(encoding="utf-8")
workflow = WORKFLOW.read_text(encoding="utf-8")
docs = DOCS.read_text(encoding="utf-8")
journal = JOURNAL.read_text(encoding="utf-8")
scheduler = SCHEDULER.read_text(encoding="utf-8")

# Never allow a real-looking Bot API token in source-controlled integration files.
token_pattern = re.compile(r"\b\d{7,12}:[A-Za-z0-9_-]{30,}\b")
for path, text in ((MODULE, module), (FAQ, faq), (WORKER, worker), (SCRIPT, script), (WORKFLOW, workflow), (DOCS, docs), (JOURNAL, journal), (SCHEDULER, scheduler)):
    if token_pattern.search(text):
        errors.append(f"possible Telegram bot token committed in {path.relative_to(ROOT)}")

required_module_markers = [
    'TELEGRAM_BOT_TOKEN',
    'TELEGRAM_WEBHOOK_SECRET',
    'TELEGRAM_SETUP_KEY',
    'TELEGRAM_ADMIN_CHAT_ID',
    'TELEGRAM_PUBLIC_ENABLED',
    '/api/telegram/health',
    'x-telegram-bot-api-secret-token',
    'x-outpost-telegram-setup-key',
    'setWebhook',
    'setMyCommands',
    'copyMessage',
    '#outpost_user_',
    'OutPOStUA_bot',
    'TELEGRAM_FAQ_SECTIONS',
    'TELEGRAM_FAQ_BY_ID',
    'updates:subscribe',
    'updates:unsubscribe',
    'telegram_update_subscribers',
    'last_notified_version',
    'maybeNotifyTelegramRelease',
    'ANALYTICS_DB',
    'Повідомити про помилку',
    'ACCOUNTING_RELEASE_VERSION_RE',
    'RELEASE_PRODUCTS',
    'currentVersionsKeyboard',
    'Завантажити OutPOSt',
    'Що нового OutPOSt',
    'Завантажити Бухгалтерію',
    'Про Бухгалтерію',
    'Поточні версії програм',
    'serializeReleaseCursor',
    'pendingReleaseProducts',
    'delivered_by_product',
]
for marker in required_module_markers:
    if marker not in module:
        errors.append(f"Telegram module missing contract marker: {marker}")


required_docs_markers = [
    'OutPOSt-Setup-vX.Y.Z.exe',
    'OutPOSt-Accounting-Setup-vX.Y.Z.exe',
    'Поточні версії програм',
    'Завантажити OutPOSt',
    'Що нового OutPOSt',
    'Завантажити Бухгалтерію',
    'Про Бухгалтерію',
    'two-product cursor',
    'product-specific Telegram release notice',
    'Compare-and-swap cursor updates',
]
for marker in required_docs_markers:
    if marker not in docs:
        errors.append(f"Telegram support docs missing product-separation marker: {marker}")

if 'extracts the single current `OutPOSt-Setup-vX.Y.Z.exe` reference' in docs:
    errors.append("Telegram support docs still describe the obsolete single-product release model")

required_worker_markers = [
    'from "./_telegram-support.js"',
    'telegramPathResponse(request, env)',
    'maybeNotifyTelegramRelease',
    'TELEGRAM_RELEASE_CHECK_PATHS',
    'PUBLIC_QUESTION_PATH',
    'https://cabinet.outpost.com.ua',
]
for marker in required_worker_markers:
    if marker not in worker:
        errors.append(f"Worker missing protected integration marker: {marker}")

required_faq_markers = [
    '2000 грн',
    '2 роки',
    'безстрокова',
    '6 і більше ПК',
    'УБД',
    'безкоштовно',
    'ПРРО',
    'еАкциз',
    'Бухгалтерія',
    'MINI-T400',
    'Data Matrix',
]
for marker in required_faq_markers:
    if marker not in faq:
        errors.append(f"Telegram FAQ missing current product marker: {marker}")

if '1000 грн' in faq or '1000 грн' in module:
    errors.append("Telegram FAQ/support must not expose the obsolete 1000 UAH license price")

# Current release must be discovered from the official download page, not hard-coded in FAQ/runtime.
for stale_version in re.findall(r'\b0\.\d+\.\d+\b', faq + "\n" + module):
    errors.append(f"Telegram FAQ/runtime must not hard-code a release version: {stale_version}")

if 'https://t.me/OutPOStUA_bot?start=site' not in script:
    errors.append("shared script missing canonical Telegram bot deep link")
if 'fetch("/api/telegram/health"' not in script:
    errors.append("Telegram contact button must be gated by runtime readiness")
if 'rel = "noopener"' not in script and 'rel="noopener"' not in script:
    errors.append("Telegram external link must use noopener")
if '.telegram-contact' not in styles:
    errors.append("Telegram contact UI styles missing")

workflow_markers = [
    'python scripts/verify_telegram_support.py',
    'node scripts/test_telegram_support.mjs',
    'node --check site/_telegram-support.js',
    'node --check site/_telegram-faq.js',
    'node scripts/test_telegram_release_journal.mjs',
    'python scripts/verify_confirmed_release_workflow.py',
    'python scripts/test_confirmed_release_security.py',
    'node --check site/_telegram-release-journal.js',
    'node --check scripts/telegram_release_scheduler.mjs',
]
for marker in workflow_markers:
    if marker not in workflow:
        errors.append(f"CI missing Telegram guard/test step: {marker}")

# Telegram may use only the privacy-minimal ANALYTICS_DB table for release subscriptions.
# It must remain isolated from CMS, Customer Portal, Director/Sync and customer/store data.
for forbidden in ('CMS_DB', 'CUSTOMER_PORTAL_ORIGIN', 'cabinet.outpost.com.ua', 'SyncOutbox', 'customer_store', 'sales_total'):
    if forbidden in module or forbidden in faq or forbidden in journal or forbidden in scheduler:
        errors.append(f"Telegram integration must not depend on protected backend/data: {forbidden}")

if 'CREATE TABLE IF NOT EXISTS telegram_update_subscribers' not in module:
    errors.append("Telegram subscription storage must self-initialize its isolated table")
if 'chat_id TEXT PRIMARY KEY' not in module:
    errors.append("Telegram subscription storage must key only by chat ID")
for forbidden_column in ('username TEXT', 'first_name TEXT', 'last_name TEXT', 'email TEXT', 'phone TEXT'):
    if forbidden_column in module:
        errors.append(f"Telegram subscription table must not store profile data: {forbidden_column}")

if errors:
    print("Telegram support guard: FAIL")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print("Telegram support guard: PASS")
