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

The reusable safe-rollback PR workflow remains available for same-release public-site source changes after the new repository becomes the production source. Its presence does not authorize migration cutover or D1 restoration.
