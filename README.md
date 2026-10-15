# OutPOSt public website

Public-safe source for the marketing website, public download artifacts, changelog and isolated Pages runtime.

This repository starts a new independent Git history. It is not a fork or mirror of the private historical website repository. Desktop source, customer portal, Director, Sync, CMS editorial history, databases and credentials are not included.

## Migration status

Operational checkpoint: 2026-10-15. Production source is now this public repository, published through the protected Pages publisher to the existing project/domain. The old Git integration is retained with automatic production builds disabled; no repository reconnect, DNS move or private-service migration is implied. Creating a PR or merging it is not live acceptance.

Current public products at this checkpoint: OutPOSt 0.24.40 and OutPOSt Бухгалтерія 1.0.2. Accounting remains an unsigned verified Windows pre-release. Installer versions, checksums and public URLs are independent for the two products. Use the release manifests and current-release checks, not this dated paragraph, for the next release.

Future-only Telegram confirmation and the five-minute scheduled pump are active. Historical versions are excluded; an idle scheduled invocation is not proof of a new-release delivery. Genuine new-release acceptance for both products remains an explicit follow-up, without inventing a desktop version or replaying old announcements.

## Checks

Run the existing public-site and release checks plus:

```text
python scripts/test_public_repository_security.py
python scripts/verify_public_repository_security.py
python scripts/release_integrity.py
python scripts/test_release_integrity.py
python scripts/test_release_workflow_security.py
python scripts/run_production_quality.py
gitleaks dir . --config .gitleaks.toml --redact=100 --ignore-gitleaks-allow
```

Pillow 12.3.0 is required for image review checks. A security scan does not replace manual screenshot/payload review.

## Boundaries and operations

- Changes go through PRs and checks. Deployment secrets never belong in PR jobs.
- Production and preview databases and Telegram credentials remain separate.
- Keep the original deployment and private backups until rollback has been verified.
- Preserve historical installer bytes and changelog entries; never silently replace an installer under an existing version URL.

See `SECURITY.md`, `docs/PUBLIC-REPO-SECURITY.md`, `docs/RELEASE-RUNBOOK.md`,
`docs/ROLLBACK-RUNBOOK.md`, `docs/PRODUCTION-PUBLISHER.md`,
`docs/CONFIRMED-TELEGRAM-RELEASES.md` and `docs/BRANCH-RETENTION.md`.
Migration inventory and backups remain private outside this repository. Desktop
release-preparation Actions are still gated OFF; use the reviewed local preparation
path. This is separate from the active protected publisher and notifier.
