# Security policy

Report security concerns privately through the official support contact at https://outpost.com.ua/support. Do not open a public issue containing keys, databases, license details, subscriber IDs or customer information.

## Publication boundary

- Only public website source, reviewed demonstration images, public release facts, public schema definitions and verified public installers belong here.
- Never add working databases, D1 exports, CMS drafts/seed exports, recovery manifests, environment files, KEP/fiscal keys, tokens or private audit evidence.
- D1 identifiers in configuration are resource routing metadata, not authorization credentials. Their bindings must still be protected from unintended changes.
- Runtime secrets stay in encrypted Cloudflare storage or restricted deployment environments; do not make secret-bearing PR previews.
- Public PRs run with read-only permissions and without deployment credentials. Do not execute untrusted PR code via `pull_request_target` or privileged `workflow_run` jobs.
- Production deployment, credential rotation and real Telegram broadcasts require separately approved operational actions during migration.

## Scanning

Use Gitleaks with full redaction and the additional repository boundary/image/installer checks. The only scanner allowlist entry is the exact IndexNow ownership verification value in its existing script, matched by both path and value. This value is already deliberately served in the corresponding public verification file; the exception does not allow private API keys, Telegram tokens or other generic credentials.

Review new screenshots for real customer/store data and record the SHA-256 of approved bytes in `release/public-screenshot-review.json`. Changed screenshots require a fresh review. Automatic checks cannot prove that photographed names or figures are fictional.
