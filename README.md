# OutPOSt public website

Public-safe source for the marketing website, public download artifacts, changelog and isolated Pages runtime.

This repository starts a new independent Git history. It is not a fork or mirror of the private historical website repository. Desktop source, customer portal, Director, Sync, CMS editorial history, databases and credentials are not included.

## Migration status

Prepared from the verified public-site snapshot of 2026-10-10. Production remains on the existing private deployment until an explicit owner-approved cutover. Creating this repository or merging a PR is not permission to change production, rotate credentials or broadcast Telegram messages.

Current public products: OutPOSt 0.24.39 and OutPOSt Бухгалтерія 1.0.2. Accounting remains an unsigned verified Windows pre-release. Installer versions, checksums and public URLs are independent for the two products.

## Checks

Run the existing public-site and release checks plus:

```text
python scripts/test_public_repository_security.py
python scripts/verify_public_repository_security.py
gitleaks dir . --config .gitleaks.toml --redact=100 --ignore-gitleaks-allow
```

Pillow 12.3.0 is required for image review checks. A security scan does not replace manual screenshot/payload review.

## Boundaries and operations

- Changes go through PRs and checks. Deployment secrets never belong in PR jobs.
- Production and preview databases and Telegram credentials remain separate.
- Keep the original deployment and private backups until rollback has been verified.
- Preserve historical installer bytes and changelog entries; never silently replace an installer under an existing version URL.

See `SECURITY.md` and `docs/BRANCH-RETENTION.md`. Migration inventory and backups remain private outside this repository.
