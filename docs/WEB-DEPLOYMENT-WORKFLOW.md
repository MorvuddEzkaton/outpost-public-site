# OutPOSt public deployment workflow

Protected provenance: see [PRODUCTION-PROVENANCE-GATE.md](PRODUCTION-PROVENANCE-GATE.md).
Live verification waits for an actual reviewed exact-SHA
successful Pages deployment and safe confirmed notification mode before canonical GETs.
This read-only gate does not itself publish. The active protected writer is
described in [PRODUCTION-PUBLISHER.md](PRODUCTION-PUBLISHER.md).

Operational checkpoint: 2026-10-15. Reviewed public source is published to the
existing Pages project/domain through the protected publisher. The old private Git
integration is retained for recovery with its production autodeploy disabled.
Subsequent separately approved stages activated future-only post-live confirmation
and one five-minute pump; the manual pilot and desktop-preparation Actions remain OFF.
The initial 12 October source-only cutover alone did not establish these later facts.

## Branches and checks

Keep main, staging, active PR branches and bounded rollback checkpoints. Protect main with PR-only changes, required real checks, no force push or branch deletion. Sensitive workflows, runtime and release metadata need owner review.

Normal flow: scoped topic branch -> local checks -> staging/isolated preview -> exact-SHA CI -> reviewed PR -> approved deployment -> real production verification.

All six required quality/security workflows run automatically for every PR into main, including docs-, scripts-, release- and installer-only changes. Restrictive paths, negative paths and activity/ignore filters must not leave a required check pending. The four browser suites share one Chromium installation; the four legacy browser workflows remain manual diagnostics, not duplicate automatic runs. A skipped/not-started check is not PASS. Release jobs must satisfy all applicable gates. Official Actions use full commit pins and tests use read-only tokens. Never run unreviewed PR code with production credentials.

Evaluate the actual PR required-check panel, not only a commit-wide list of historical successful jobs. Manual workflow_dispatch runs are useful diagnostics but do not satisfy PR required checks; GitHub documents this distinction at https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks. Do not rename contexts, synthesize success, broaden App permissions or waive protection to unblock a PR. Re-run the actual pull_request workflows after fixing a coverage gap, then verify the exact current PR head and owner review.

## Deployment authority

Creating a repository, merging source or seeing green static CI is not live acceptance.
OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED and OUTPOST_PRODUCTION_WRITER_ENABLED are
currently enabled under owner authorization, not set by documentation or PR jobs.
Both publisher quality jobs, exact-source review and protected production approval
remain required. A skipped live/publish job is not PASS.

The accepted path uses controlled pinned Wrangler publication to the existing
project, retaining domains/private bindings/encrypted secrets and strict compatible
baseline equality. Do not reconnect Git, re-enable the conflicting old autodeploy,
repeat a completed bootstrap or silently change provider settings.

Infrastructure maintenance has a separate opt-in variable and protected environment. Do not provision an account-wide maintenance token merely to publish website content.

## Protected boundaries

Preserve cabinet/public-question destinations, license services, Director, Sync, D1 data, secrets, installer paths and customer contracts. Preview requires separate databases and no production Telegram credentials. Public and CMS preview HTML/sitemap stay noindex/nofollow.

Preview integrations fail closed: noncanonical/HTTP/nonstandard-port hosts cannot forward public questions, handle Telegram setup/webhook or start release notifications/download analytics writes, even if production-style bindings are accidentally present. Preview Telegram health explicitly returns enabled=false; blocked writes return 403 and never pretend successful delivery. Set OUTPOST_PREVIEW_ONLY=1 on an isolated test deployment as an additional safeguard, including against an incorrectly attached canonical hostname. Preserve the canonical HTTPS production proxy/header contract; test it with an in-memory upstream, never with real test messages to production. Local D1 simulations are not production backups or a remote restore drill.

## Release and rollback

OutPOSt and Accounting releases are independent immutable artifacts with checksums, acceptance evidence, truthful status and retained history. Complete static/browser/staging checks before deployment and exact live installer/page checks afterward. Telegram requires a confirmed release event, not merely a version change or website visit.

Private settings/D1 backups, independent local restore, compatible baseline and
explicit go/no-go were accepted during cutover/activation. They are dated evidence,
not permission to overwrite newer D1 data. Keep the original repository and recovery
points; portable/offsite recovery remains unclaimed. For the next publication follow
RELEASE-RUNBOOK.md and ROLLBACK-RUNBOOK.md, not a replay of migration executors.
