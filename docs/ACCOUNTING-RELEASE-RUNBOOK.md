# OutPOSt Accounting pre-release runbook

Цей процес призначений **лише для OutPOSt Бухгалтерії**. Він не є релізом основного OutPOSt і не має права змінювати стабільний `OutPOSt-Setup-v*.exe`, його checksum або `site/changelog.html`.

## Що підготувати

1. Переконайтесь, що `main` і `staging` синхронізовані та зелений production уже має rollback backup.
2. Додайте в `staging` **рівно один новий файл**:
   `site/downloads/OutPOSt-Accounting-Setup-v<VERSION>.exe`
3. Не додавайте checksum вручну. Не змінюйте разом із цим HTML, manifest, stable OutPOSt installer або changelog.

Наприклад:
`site/downloads/OutPOSt-Accounting-Setup-v0.403.exe`

## Запуск

У GitHub Actions вручну запустіть **Prepare Accounting pre-release PR** і задайте:

- `version` — версія, що точно відповідає імені EXE;
- `rc_acceptance` — `PASS` тільки якщо Windows RC acceptance реально пройдено, інакше `NOT_VERIFIED`;
- `authenticode` — `signed` тільки якщо цей конкретний installer справді підписаний, інакше `unsigned`.

## Що workflow робить автоматично

- перевіряє, що `staging` базується на актуальному `main`;
- відмовляється працювати, якщо в `staging` є щось крім одного нового Accounting EXE;
- робить dry-run;
- створює backup поточного `main`;
- створює ізольовану `accounting-release/...` гілку;
- обчислює byte size та SHA-256 з самого EXE;
- генерує `.sha256.txt`;
- оновлює `release/accounting-release.json`;
- синхронізує поточну версію/розмір/SHA/RC/AuthentiCode на `/buhgalteriya` та в правій Accounting-половині `/download`;
- оновлює тільки `lastmod` `/buhgalteriya` у sitemap;
- прибирає попередню публічну Accounting EXE/checksum пару;
- запускає повний static release gate: SEO/contextual/FAQ/demo guards, workflow-quality regressions, release-gate parity, sitemap freshness/parity, product maturity, host/privacy та Open Graph image-dimension offline regressions, Accounting synthetic regression і stable OutPOSt release guards;
- відкриває PR у `main`.

## Що workflow не робить

- не merge'ить PR;
- не push'ить у `main` або `staging`;
- не запускає Cloudflare deploy напряму;
- не змінює stable OutPOSt installer/checksum/changelog;
- не викликає Cabinet, Director, Sync, D1, ПРРО або інші protected endpoints.

## Перед merge

PR має пройти повний `Public site smoke checks`. Окремо перевіряйте, що diff містить лише Accounting release artifacts/manifest/pages/sitemap та не містить protected runtime або stable OutPOSt release змін.

Перед merge створіть точний backup актуального `main`.

## Після merge

1. Синхронізуйте `staging` на exact merge SHA.
2. Дочекайтесь `Verify live production`.
3. Обов'язково має пройти `Verify live Accounting pre-release`: він перевіряє `/buhgalteriya`, `/download`, checksum, 1-byte HTTP Range нового EXE, top-level навігацію та deployed shared JS.
4. Загальний `Verify live production` також має підтвердити sitemap parity, canonical/alternate-host normalization, відсутність Cloudflare RUM, security headers, structured/social metadata, фактичні dimensions Open Graph PNG та product-maturity contract.
5. Переконайтесь, що фінальний `Verify live customer Cabinet entry` також зелений.
6. Створіть post-merge green backup.

## Канонічне джерело release-фактів

`release/accounting-release.json` — єдине джерело поточної Accounting версії, filename, byte size, SHA-256, RC/AuthentiCode статусу та дати публікації для release tooling і guards.
