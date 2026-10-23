# Import a verified OutPOSt installer from Dropbox

This is a **staging-only** workflow. It never deploys, merges, sends Telegram alerts, changes Cloudflare/D1/PRRO or bypasses the protected release workflow.

## One-time configuration (repo owner only)

1. In the [Dropbox App Console](https://www.dropbox.com/developers/apps), create a **Scoped Access / Full Dropbox** app. Grant **only** `files.content.read` (and optionally `files.metadata.read` for diagnostics). The existing build is stored in a shared folder, so App Folder access would be insufficient.
2. Use Dropbox OAuth authorization-code flow with `token_access_type=offline` to obtain a **refresh token**. Never paste the token into ChatGPT, a public issue, source code or a workflow input. The refresh token must belong to the Dropbox account with access to the original release file.
3. In **GitHub > repository Settings > Secrets and variables > Actions > Secrets**, create the following repository secrets: `OUTPOST_DROPBOX_APP_KEY`, `OUTPOST_DROPBOX_APP_SECRET`, `OUTPOST_DROPBOX_REFRESH_TOKEN`. Use fresh app credentials and restrict access to repository administrators.
4. In **Variables** on the same page set `OUTPOST_DROPBOX_IMPORT_ENABLED=1` only after reviewing the workflow and authorizing its scopes. This separate activation flag is **disabled by default**.
5. Preserve the existing `OUTPOST_RELEASE_PREPARATION_ENABLED` gate for the downstream `Prepare public release PR` workflow.

## Per-release sequence

1. Build the release on Windows and place `OutPOSt-Setup-vX.Y.Z.exe` into Dropbox path `/OutPOSt/git-work/outpost-02410-redesign/dist/` (the importer expects this exact directory and filename). Complete the **actual** Windows installation, upgrade and runtime acceptance on the exact bytes.
2. Commit to `staging` **only** the new exact `site/downloads/OutPOSt-Setup-vX.Y.Z.sha256.txt`, updated `site/changelog.html`, and `release/evidence/outpost-vX.Y.Z.json` with a genuine owner-approved `windows_acceptance=PASS` and the digest of the actual Windows acceptance report. Do not invent a receipt from a build log.
3. From **Actions > Import verified OutPOSt installer from Dropbox > Run workflow**, select `main`, set `version=X.Y.Z`, and run. The job reads Dropbox only using secrets, checks binary length, SHA-256 and the existing strict release receipt verifier, then commits the EXE **only to `staging`**, rejecting staging divergence or surprise files.
4. Once its run succeeds, dispatch **Prepare public release PR** (on `main`, `version=X.Y.Z`). The existing separate release workflow validates the exact four-input staging scope, prepares the reviewable release PR and executes tests. Complete protected PR/CI/deployment/live verification before announcing the version.

## Safety and failure cases

- Any absent credentials, absent Windows owner approval, unknown changed files, mismatched SHA/size, changed `main`/`staging`, PE header failure, missing Dropbox source or API error **fails closed**. No production writes or receipt forgery.
- Never set `ACTIONS_STEP_DEBUG` for a credential troubleshooting run or print OAuth responses/HTTP request headers. Rotate/revoke the Dropbox app token immediately if accidentally exposed.
- The installer is a regular Git file (~15.5 MB), not a GitHub Actions artifact or Git LFS pointer. GitHub's normal per-file 100 MB cap and the local **25 MiB** limit apply.
- The workflow is manual and owner-only. It does not automatically claim new builds are tested or ready to ship. If the Dropbox release folder changes, update the hardcoded directory in the trusted Python importer through a reviewed PR before importing.
- A skipped job typically means the owner-only / opt-in gate is not enabled. The normal release workflow remains independent and immutable.
