# Initial publication review

Date: 2026-10-12.

This is a reviewed snapshot with a new independent Git history, not a mirror/fork of the historical private repository. Production migration is a separate owner-approved operation.

Checks completed before the initial push:

- Explicit source-file allowlist; private recovery inventories, CMS seed export/editorial history, runtime state and databases excluded.
- Manual review of public Pages Worker, CMS renderer and Telegram authentication boundaries. Existing backend/proxy contracts retained; no credentials in source. Telegram release reliability changes are still a separate pending workstream.
- Gitleaks 8.30.1 and additional credential/path checks. One exact, documented exception for the intentionally hosted IndexNow ownership verification value, not a private authorization token.
- Ninety demonstration screenshots visually reviewed, with SHA-256 review records. Owner confirmed fictional test data for the historical debt-sale scenario. No EXIF data found in the decoded images.
- Unused malformed artwork excluded from this snapshot and retained privately for audit; live source not changed.
- All 22 historical installer/checksum pairs preserved and verified. Current installers also independently re-downloaded from production with byte/SHA parity. Source scanning is not a claim of comprehensive reverse-engineering or malware certification of every historical executable.
- Official GitHub Actions pinned to full reviewed commit SHAs. PR jobs have no production credentials.

Private evidence, resource inventory, authenticated diagnostics and backups stay outside this repository. Required ongoing gates include secret scanning, source boundary checks, reviewed-image integrity, installer verification and the existing site/browser checks.

This review cannot mathematically prove that all sensitive data are absent. New files, screenshots and dependencies need renewed review. The original repositories stay private. This public source must not be interpreted as authorization for domain changes, key rotation, D1 mutations or real Telegram broadcasts.
