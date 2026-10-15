# Change safety and rollback

This public repository starts an independent history. Historical rollback references from the private repository are not imported and must not be assumed to exist here.

- Require reviewed PRs and real checks for source changes.
- Before a production deployment retain the last known-good SHA/deployment ID privately.
- Preserve protected private services, D1 data, authentication and installer artifacts.
- Never force-push main or silently cross an application release boundary as a website rollback.
- Routine website rollback preserves the current installer/checksum/version set and backend contracts.
- Application downgrade is a separately coordinated release operation.
- Record D1 writes after deployment before rollback; do not erase fresh subscriptions/CMS/analytics by restoring an old database blindly.
- Keep the original private repository and production deployment until approved migration and rollback verification succeed.

The new repository is the production source (checkpoint 2026-10-15). The reusable
safe-rollback PR workflow is for reviewed same-release source recovery, not automatic
cutover, application downgrade or D1 restoration. Use the current
[ROLLBACK-RUNBOOK.md](ROLLBACK-RUNBOOK.md) and compatible protected-publisher baseline;
do not confuse a prepared recovery PR with an accepted live rollback.
