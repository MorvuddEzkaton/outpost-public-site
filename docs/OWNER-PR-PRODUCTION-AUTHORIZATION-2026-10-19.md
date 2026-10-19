# Власник репозиторію: без самосхвалення PR — 2026-10-19

## Причина
PR #31 в `main` (64e56cd7c32bd9cad9f525564dd70d2cdfa1b621) пройшов static/browser quality, але publisher зупинився **до завантаження** на `human_codeowner_review_missing`.
GitHub забороняє схвалювати власний PR; попередній валідатор вимагав саме таке схвалення незалежно від автора.
Додатково `verify_main_push_provenance.py` не розпізнавав справжній заголовок `Merge PR #31: ...`.

## Нові дві моделі авторизації
1. **Owner self-merge:** асоційований із точним `main` SHA злитий PR повинен мати автора `MorvuddEzkaton`, а окремий read-only запит GET `/pulls/{number}` мусить довести `merged=true`, `merged_by.login=MorvuddEzkaton`, той самий PR number, head SHA, base repo/main, merge SHA та merge timestamp. **Немає фіктивного review ID**.
2. **Інший автор (у т.ч. bot):** чинний доказ останнього `APPROVED` review власника на точний head SHA залишається обов'язковим. Owner-author без owner-merge не допускається.

Усі сценарії також вимагають реального merge PR (не commit-subject), поточного main SHA, CODEOWNER-scoped production environment approval, правильних прив'язок Cloudflare/D1 та коректного notification mode. Прямі push без PR не отримують доказу.

## Журнал і історія
- Для owner-self-merge запис: `{pr, head_sha, owner_review_id:null, authorization:"owner_self_merge"}`.
- Для bot/іншого автора з реальним CODEOWNER approval запис **не змінено**: `{pr, head_sha, owner_review_id:<positive integer>}`.
- Історичні журнали залишаються валідними; журнал із підробленим authorization, ключами чи review ID відхиляється.
- `Merge PR #31: ...` тепер розпізнається лише як допустима **форма коміту**; доказом авторизації все одно слугують метадані GitHub API.

## Межі приймання
- Новий PR включає невикладений PR #31 (у main) і вміст PR #32/#33 із спільної перевіреної гілки.
- GitHub Actions 6/6 і повні production static/browser тести мають бути зеленими.
- Власник окремо схвалює **production environment**; заборонено вимикати цей захист.
- Після публікації перевірити точну SHA-версію в Cloudflare і всі live contracts, зокрема Кабінет.
- Не змінювалися Worker, D1, ліцензії, фіскальні модулі, Telegram, секрети, права доступу або інсталятори.
- Відкатна контрольна гілка `backup/accepted-production-before-seo-20261019` = `ae9d9a60a184e7620a78d26c7db90541a51cd623`.

## Відновлення після failed-before-plan-intent PR #31
Publisher run 39217275288 провалився на кроці 7 (read-only plan), а кроки 8–13 були `skipped`: жодного upload не було. Історичний interlock без journal artifacts правильно блокував нове джерело, але не мав окремого способу довести збій до intent. Тепер provider Actions job steps 1–13 перевіряються за точним набором наслідків: PASS static/browser, FAIL лише на плані й SKIPPED для всіх потенційно небезпечних кроків. Лише такий випадок приймається як `preflight_failed`; усі невідомі, скасовані й after-upload стани залишаються заблокованими. Дозволено append-only checkpoint для доведеного випадку.
