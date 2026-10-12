# OutPOSt Public Release Runbook

**Purpose:** publish a new Windows installer on `outpost.com.ua` without one-off search/replace work and without touching Cabinet, Director, Sync API or Cloudflare/D1 data.

## Safety rules

1. Never start a public release from `main`. Prepare release inputs in `staging`.
2. Create a backup branch/reference before release work. The automated PR workflow also creates an additional pre-release backup of the current `main`.
3. Never replace or delete the previous installer during the same release. Historical installers remain available for rollback/audit unless there is a separate explicit cleanup decision.
4. Do not change `site/_worker.js`, `site/_telegram-support.js`, `site/_telegram-faq.js`, `site/_headers`, `wrangler.jsonc`, Cabinet, Director, Sync API or D1 bindings as a side effect of a desktop release.
5. Merge only after `Public site smoke checks` is green.
6. Create/retain a fresh backup of `main` immediately before merge.
7. After merge, require `Verify live production` to pass before treating the release as fully published.

## Explicit release hold

If the repository root contains `.release-hold`, production publication is intentionally blocked. The public-site smoke workflow fails before the normal release checks and prints the hold reason.

Use this only for a concrete safety condition such as a newer verified installer replacing an already-staged binary under the same version number. Do not remove the hold merely to obtain a green PR.

Before removing `.release-hold`:

1. stage the exact replacement installer;
2. update its checksum and all generated public release metadata from that exact binary;
3. run the normal release/static verification;
4. remove the hold only in the same candidate that contains the verified replacement.

A PR to `main` must not be merged while `.release-hold` exists.

## Inputs required for a new release

For version `X.Y.Z`, prepare these two new files in `staging`:

```text
site/downloads/OutPOSt-Setup-vX.Y.Z.exe
site/downloads/OutPOSt-Setup-vX.Y.Z.sha256.txt
```

Checksum format:

```text
<SHA256> *OutPOSt-Setup-vX.Y.Z.exe
```

The reusable release tool calculates the installer SHA-256 itself and refuses to proceed if the checksum file does not match the actual bytes.

### Verify the binary before release metadata work

When the installer is copied or uploaded manually, treat the exact `dist` artifact as the source of truth. Before changing public version metadata:

1. verify the exact filename `OutPOSt-Setup-vX.Y.Z.exe`;
2. verify the byte size against the release report/source artifact;
3. recompute SHA-256 independently and compare it with the `.sha256.txt` file;
4. after a manual GitHub upload, verify the uploaded repository object again before proceeding;
5. if either size or digest differs, remove the uploaded file immediately and do **not** continue with changelog/current-version publication.

Do not reuse an older installer under a newer filename and do not accept “same version number” as proof that two binaries are identical.

## Changelog first

In the same prepared `staging`, update `site/changelog.html` with the new translated/public release block and mark it as the current release.

Required marker:

```html
<div class="changelog-version"><span>Поточний реліз</span><strong>X.Y.Z</strong></div>
```

The hero CTA must also contain:

```text
Завантажити vX.Y.Z
```

The updater deliberately does **not** invent release notes. This keeps technical claims under review instead of generating them from a version number.

At this point the net `main..staging` diff must contain exactly three release inputs:

```text
A  site/downloads/OutPOSt-Setup-vX.Y.Z.exe
A  site/downloads/OutPOSt-Setup-vX.Y.Z.sha256.txt
M  site/changelog.html
```

Any additional, deleted, renamed or copied file must be handled separately before release preparation.

## Recommended path: Prepare public release PR

After the three release inputs are committed to `staging`, run the GitHub Actions workflow **Prepare public release PR** manually and enter `X.Y.Z`.

The workflow is intentionally PR-only. It:

1. checks that `staging` is based on current `main` without divergence;
2. refuses to continue unless the `main..staging` diff is exactly the target installer, target checksum and `site/changelog.html`;
3. runs `prepare_public_release.py X.Y.Z` as a read-only dry-run;
4. creates an automatic `backup/pre-vX.Y.Z-...` reference from the current `main`;
5. creates an isolated `release/vX.Y.Z-...` branch from the validated `staging`;
6. runs `prepare_public_release.py X.Y.Z --apply`;
7. permits the resulting release diff only inside public root HTML, `site/sitemap.xml`, the target installer and target checksum;
8. verifies that Worker, Telegram Worker/FAQ, security headers and Cloudflare configuration remain unchanged;
9. runs the complete static release gate, including SEO uniqueness/contextual links, FAQ/demo regressions, workflow-quality guards, installer SHA, release metadata, sitemap freshness/parity regressions, product maturity, commercial terms, host/privacy regressions, Open Graph image dimension checks, Cabinet-entry and Telegram checks;
10. commits the generated release metadata, pushes only the isolated release branch and opens a PR to `main`.

It does **not** merge the PR, push to `main`, mutate `staging`, deploy Cloudflare, or call Cabinet/Director/Sync/D1. Human review + normal PR smoke remain mandatory.

## Manual fallback: dry-run

If the automated PR workflow cannot be used, run the reusable updater manually from the repository root:

```powershell
python scripts/prepare_public_release.py X.Y.Z
```

The command is read-only by default. It checks:

- target version syntax and ordering;
- target installer presence;
- target checksum presence and format;
- actual installer SHA-256 against the checksum file;
- changelog current-release marker;
- every existing current-release reference that would need migration;
- transformed `/download` markers before anything is written;
- structured `softwareVersion` / `downloadUrl` / `fileSize` consistency for the current release, including minified JSON-LD;
- preview-safe relative homepage installer links so staging validation does not silently jump to the production artifact.

Review the listed files.

## Manual fallback: apply

Only after reviewing the dry-run:

```powershell
python scripts/prepare_public_release.py X.Y.Z --apply
```

The tool updates only public HTML current-release metadata/CTAs and the release sitemap. It does not touch the Worker, Cloudflare configuration, D1, Cabinet, Director or Sync API.

## Mandatory local/static checks

For a manual release preparation, run:

```powershell
python scripts/verify_public_site.py
python scripts/verify_automation_landing_intents.py
python scripts/verify_public_seo_uniqueness.py
python scripts/verify_public_contextual_links.py
python scripts/test_demo_dialog_contract.py
python scripts/test_public_faq_schema.py
python scripts/verify_site_identity.py
python scripts/verify_site_identity_workflows.py
python scripts/verify_quality_gate_workflows.py
python scripts/test_quality_gate_workflows.py
python scripts/test_main_push_provenance.py
python scripts/verify_removed_public_pages.py
python scripts/verify_404_page.py
python scripts/verify_public_ctas.py
python scripts/verify_support_discovery.py
python scripts/verify_safe_rollback_workflow.py
python scripts/verify_prepare_release_workflow.py
python scripts/verify_prepare_accounting_release_workflow.py
python scripts/verify_release_gate_parity.py
python scripts/test_release_gate_parity.py
python scripts/verify_internal_anchors.py
python scripts/verify_license_activation_path.py
python scripts/verify_public_license_terms.py
python scripts/verify_public_product_maturity.py
python scripts/test_product_maturity_guard.py
python scripts/verify_cabinet_entry.py
python scripts/verify_accessibility.py
python scripts/verify_color_contrast.py
python scripts/verify_public_contacts.py
python scripts/verify_phone_ctas.py
python scripts/verify_cloudflare_config.py
python scripts/verify_security_headers.py
python scripts/verify_installers.py
python scripts/verify_accounting_release.py
python scripts/prepare_accounting_release.py --check-current
python scripts/test_prepare_accounting_release.py
python scripts/verify_release_metadata.py
python scripts/verify_release_sitemap.py
python scripts/prepare_public_release.py --check-current
python scripts/test_prepare_public_release.py
python scripts/test_sitemap_freshness.py
python scripts/verify_sitemap_freshness.py
python scripts/test_live_host_normalization.py
python scripts/test_live_cloudflare_privacy.py
python scripts/test_live_sitemap.py
python scripts/test_live_static_assets.py
python scripts/test_social_image_dimensions.py
python scripts/verify_telegram_support.py
node scripts/test_telegram_support.mjs
node scripts/test_cms_preview_privacy.mjs
node scripts/test_static_preview_privacy.mjs
node scripts/generate_support_center.mjs --check
node --check site/script.js
node --check site/_cms-runtime.js
```

Then inspect:

```powershell
git status
git diff --check
git diff
```

## Pull request and production merge

For the recommended automated path:

1. review the `release/vX.Y.Z-... -> main` PR created by the workflow;
2. verify the PR head SHA is exactly the expected current release/staging branch SHA before accepting any CI result. A previously closed PR can retain a stale head snapshot while its source branch advances;
3. if the PR head SHA does not match the expected branch SHA, do **not** merge or rely on old checks: keep that PR closed and create a fresh PR from the current validated branch to `main`;
4. require `Public site smoke checks` = PASS on that exact head SHA;
5. review changed filenames. A normal desktop release must not contain protected web-service files;
6. verify the automatic pre-release backup exists and keep the explicit pre-merge backup discipline;
7. merge to `main` only after review.

For the manual fallback, create an isolated release PR to `main` after the same checks. Do not bypass the PR with a direct push to `main`. If a paused/closed staging PR is reused after additional commits, the same exact-head rule applies before CI or merge.

## Post-deploy verification

`Verify live production` runs automatically for relevant `main` changes and can also be run manually.

It derives the expected release from the repository and waits for Cloudflare Pages propagation. It verifies:

- live `/` and `/download` expose the expected release and installer;
- live checksum file matches the repository;
- live installer byte size matches the repository;
- live installer SHA-256 matches the repository;
- live sitemap matches repository `loc`, `lastmod`, `changefreq` and `priority` values;
- live `robots.txt` matches the repository safety rules;
- canonical HTTP/trailing-slash/`.html` variants normalize permanently;
- `www.outpost.com.ua` and both known `pages.dev` hosts still redirect directly to the apex canonical host with query/path preservation;
- Cloudflare RUM/Web Analytics injection remains absent from delivered HTML;
- live social/OpenGraph and structured commercial metadata remain equal to protected source;
- live Open Graph PNG dimensions match the declared `og:image:width` / `og:image:height` values;
- public product-maturity wording remains valid;
- all public sitemap pages retain Support Center discovery;
- all public sitemap pages retain the canonical customer Cabinet link without following that link or calling protected Cabinet services.

The installer validation uses an HTTP Range request and requires `206 Partial Content`. The public Worker excludes range/resume requests from installer download analytics, so CI verification does not inflate the public download counter.

A release is considered fully published only after this workflow is green.

## Current-release health check

At any time:

```powershell
python scripts/prepare_public_release.py --check-current
```

This verifies that the current installer/checksum pair is internally valid and that the changelog points to the same current release.

## Rollback

If a public release causes a website/deployment problem:

1. do not edit Cabinet/Director/Sync as a workaround;
2. identify the most recent pre-release `main` backup branch;
3. restore/revert only the public-site release commit(s);
4. let Cloudflare deploy the restored `main`;
5. require `Verify live production` to pass against the restored release;
6. preserve the failed release branch/commit for diagnosis.

The desktop user's working database is not stored in the website repository; public-site rollback must not alter customer business data.
