# OutPOSt public deployment workflow

Migration preparation date: 2026-10-12. This new public repository is not the production source until an explicit owner-approved cutover. The existing private Git integration and Pages deployment remain active during preparation.

## Branches and checks

Keep main, staging, active PR branches and bounded rollback checkpoints. Protect main with PR-only changes, required real checks, no force push or branch deletion. Sensitive workflows, runtime and release metadata need owner review.

Normal flow: scoped topic branch -> local checks -> staging/isolated preview -> exact-SHA CI -> reviewed PR -> approved deployment -> real production verification.

All six required quality/security workflows run automatically for every PR into main, including docs-, scripts-, release- and installer-only changes. Restrictive paths, negative paths and activity/ignore filters must not leave a required check pending. The four browser suites share one Chromium installation; the four legacy browser workflows remain manual diagnostics, not duplicate automatic runs. A skipped/not-started check is not PASS. Release jobs must satisfy all applicable gates. Official Actions use full commit pins and tests use read-only tokens. Never run unreviewed PR code with production credentials.

Evaluate the actual PR required-check panel, not only a commit-wide list of historical successful jobs. Manual workflow_dispatch runs are useful diagnostics but do not satisfy PR required checks; GitHub documents this distinction at https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks. Do not rename contexts, synthesize success, broaden App permissions or waive protection to unblock a PR. Re-run the actual pull_request workflows after fixing a coverage gap, then verify the exact current PR head and owner review.

## Deployment authority

Creating this repository, merging the initial snapshot or seeing green static CI does not authorize production deployment. OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED stays unset until the explicit cutover plan is approved. The live-production workflow is inactive until then; a skipped live job does not certify the live site.

Preferred future path: validate controlled Wrangler deployment to the existing Pages project so domains, private bindings and encrypted secrets can remain intact. Confirm this against the actual project before use. Disable conflicting old automatic deployments only during approved cutover, not during repository preparation.

Infrastructure maintenance has a separate opt-in variable and protected environment. Do not provision an account-wide maintenance token merely to publish website content.

## Protected boundaries

Preserve cabinet/public-question destinations, license services, Director, Sync, D1 data, secrets, installer paths and customer contracts. Preview requires separate databases and no production Telegram credentials. Public and CMS preview HTML/sitemap stay noindex/nofollow.

## Release and rollback

OutPOSt and Accounting releases are independent immutable artifacts with checksums, acceptance evidence, truthful status and retained history. Complete static/browser/staging checks before deployment and exact live installer/page checks afterward. Telegram requires a confirmed release event, not merely a version change or website visit.

Before cutover: private settings/D1 backups, isolated restore drill, health baseline, precise rollback and explicit owner go/no-go. Keep the original repository/project until verified stability. Do not overwrite newer D1 records with older snapshots during rollback.
