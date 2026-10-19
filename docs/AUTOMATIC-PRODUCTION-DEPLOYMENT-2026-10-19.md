# OutPOSt — автоматичне production-розгортання після merge PR

Дата підготовки: 2026-10-19. **Це контрольований перехід, а не вже активований автоматичний режим.**

## Поточна архітектура та ціль

`.github/workflows/deploy-public-production.yml` уже запускається за `push` до `main` та виконує:
1. `static-quality` — повний контроль репозиторію, перевірки релізу, історії, security-скан;
2. `browser-quality` — WCAG, keyboard, runtime, UI;
3. `publish` у GitHub environment **production**, тільки після успішного завершення обох джобів;
4. read-only provenance через GitHub API: фактично **merged** PR у `main`, підтверджений точний commit/head SHA; для owner-authored PR — server-verified author **та** merger = власник, для інших — останній власницький CODEOWNER APPROVED на точному SHA;
5. main-only deployment-branch policy GitHub environment `production` — **тільки одна Branch = main**, без тегів/wildcards;
6. source-hash, Cloudflare project/D1/preview-конфіг, release health, наявність попереднього прийнятого результату, запис intent перед upload;
7. **одну** спробу завантаження, підтвердження canonical deployment exact SHA, повні live-контракти, rollback тільки нашого коду в разі критичного live failure, запис final journal;
8. окрему незалежну workflow `live-production-verify.yml` на `push main` з тими ж обмеженнями походження, що чекає exact source deployment та перевіряє live UI/Cabinet entry.

Cloudflare Pages **Git-integrated auto-deploy залишається вимкненим**. Увімкнення власного GitHub Actions publisher не означає його ввімкнення.

## Що саме змінено в коді

У `production_deployment_gate.py` додано явний перемикач **репозиторного** GitHub Actions Variable:

`OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED`

- Відсутнє / `0`: **старий manual mode**. Вимагає `production` required reviewer = `MorvuddEzkaton`. Без рецензента — fail-closed.
- Рівно `1`: **auto mode**. Вимагає, щоб `production` не мало `required_reviewers` rule. Якщо reviewer досі є — fail-closed.
- Будь-яке інше значення: **fail-closed**.
- У **обох режимах**: environment саме `production`, `deployment_branch_policy = {protected_branches:false,custom_branch_policies:true}`, рівно одна branch policy **Branch main**, точний merged PR, всі тести, SHA, секрети в environment, без прямого push/форсування прав чи змін у Workers, D1, Cloudflare.
- Явний mode passed у **publisher**, **independent live verifier** і `confirm-telegram-release`. Захисти релізної розсилки не послаблено.

### Важлива різниця в ризиках

У разі вимкнення `Required reviewers` **секрети environment production стануть доступні для jobs, що посилаються на production, без ручного approval**. Це свідоме послаблення одного рівня захисту, компенсоване scope `main` + mandatory PR/status checks + fail-closed provenance, але це **не тотожна безпека**. Власник має підтримувати захист `main` від прямого push, force-push і випадкового злиття неперевіреного workflow. Не дозволяти стороннім змінювати `.github/workflows/**` без review.

## Одноразова активація (тільки власник, у GitHub UI)

1. Спочатку злийте і **прийміть цей PR у старому manual режимі**: 6/6 required checks, protected publisher та independent live success на точному merge SHA. Це останнє ручне схвалення для завантаження режиму в `main`. **Не змінюйте required reviewers до завершення першого приймання.**
2. Відкрийте `https://github.com/MorvuddEzkaton/outpost-public-site/settings/variables/actions` → `New repository variable`. Ім'я `OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED`, значення рівно `1`. Не використовуйте Secret замість Variable і не додавайте в `wrangler.jsonc`.
3. Відкрийте `https://github.com/MorvuddEzkaton/outpost-public-site/settings/environments` → `production`. **Зніміть тільки `Required reviewers`** та збережіть правила. Нічого більше не видаляйте.
4. **Обов'язково перевірте**: `Deployment branches and tags` = `Selected branches and tags`, рівно одна branch policy `main`, немає `*`/тегів; environment `production` залишився з тими самими Secrets; `Wait timer` можна залишити, якщо потрібна пауза без участі людини.
5. Після цього кожне наступне **злиття перевіреного PR в main** автоматично запускає quality → protected environment (без reviewer) → plan → intent → upload → canonical exact-SHA proof → live → conditional rollback. GitHub Actions показує логи, не вимагаючи `Approve and deploy`.
6. **Контрольна перевірка:** невеликий PR без змін бізнес-логіки й з усіма перевірками. Він має пройти весь pipeline автоматично. Після SUCCESS переконатися, що незалежний live verifier також SUCCESS; перевірити `/support`, `/download`, `/cabinet` entry (точний route тестів), SHA, Cloudflare і journal. Автопублікація **не вважається підтвердженою**, доки не пройде цей реальний test deployment.

## Відкат режиму

- Якщо автопублікація не проходить: **не повторювати upload вручну всупереч journal** і не знімати інші guards.
- Спершу **повернути Required reviewers** власника у `production` (зберегти).
- Тоді змінити `OUTPOST_AUTOMATIC_PRODUCTION_APPROVAL_ENABLED` на `0`. Обидві операції потрібні для старого режиму; тимчасовий mismatch безпечніше fail-closed, ніж неперевірене розгортання.
- Rollback коду — тільки через наявні code-only rollback / backup / контрольовані PR; **не відновлювати D1** за замовчуванням.
- Резервна точка до цього PR: `backup/pre-auto-production-20261019` → `5657cce954677bf2beb4100ef38dcfc57b7cd891`.

## Що не змінювалося

Жодних змін D1, Workers, DNS, Cloudflare Pages config/секретів, вебкабінету, інтеграцій POS, фіскалізації, інсталяторів або Telegram-сповіщень. Вхід у вебкабінет перевіряється public smoke, але end-to-end синхронізацію статистики ця зміна **не тестує**. Автоматична відправка релізів у Telegram залишається окремо захищеною своїми змінними та журналами.
