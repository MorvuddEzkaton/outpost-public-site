# OutPOSt public deployment workflow

Protected provenance preparation: see [PRODUCTION-PROVENANCE-GATE.md](PRODUCTION-PROVENANCE-GATE.md).
Once deliberately activated, live verification waits for an actual reviewed exact-SHA
successful Pages deployment and safe confirmed notification mode before canonical GETs.
This read-only gate does not itself publish. A separate dormant protected writer is
prepared in [PRODUCTION-PUBLISHER.md](PRODUCTION-PUBLISHER.md); it is not activated.

Migration preparation date: 2026-10-12. The owner-approved source-only cutover has
published reviewed public source to the existing Pages project. The old private Git
integration identity remains for recovery, with its automatic production deployment
disabled. That completed source-only step did not activate new automatic publication,
new credentials, notification modes or a scheduled sender.

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

Preview integrations fail closed: noncanonical/HTTP/nonstandard-port hosts cannot forward public questions, handle Telegram setup/webhook or start release notifications/download analytics writes, even if production-style bindings are accidentally present. Preview Telegram health explicitly returns enabled=false; blocked writes return 403 and never pretend successful delivery. Set OUTPOST_PREVIEW_ONLY=1 on an isolated test deployment as an additional safeguard, including against an incorrectly attached canonical hostname. Preserve the canonical HTTPS production proxy/header contract; test it with an in-memory upstream, never with real test messages to production. Local D1 simulations are not production backups or a remote restore drill.

## Release and rollback

OutPOSt and Accounting releases are independent immutable artifacts with checksums, acceptance evidence, truthful status and retained history. Complete static/browser/staging checks before deployment and exact live installer/page checks afterward. Telegram requires a confirmed release event, not merely a version change or website visit.

Before cutover: private settings/D1 backups, isolated restore drill, health baseline, precise rollback and explicit owner go/no-go. Keep the original repository/project until verified stability. Do not overwrite newer D1 records with older snapshots during rollback.
