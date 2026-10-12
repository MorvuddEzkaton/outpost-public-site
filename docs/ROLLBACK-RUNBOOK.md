# Rollback checkpoints during migration

Current production remains on its private source/project. Public repository source
preparation is not permission to change a domain, D1, active token or Telegram webhook.

For a prepared release, retain the exact pre-release main SHA and immutable downloads.
Use a reviewed corrective/rollback PR; never force-push protected main or remove the
new public Git history. A failed preparation is NOT PUBLISHED, even if local files
were written. Restore/reconstruct only owned topic work after inspecting the diff.

Before the future cutover, complete the **private** resource/settings inventory, CMS
and analytics/subscription backups, isolated D1 restore drill, health baseline and
precise deployment rollback plan. These prerequisites are not yet claimed complete.

If live verification fails after an approved deployment: stop rollout and release
notification, record the actual head SHA/deployment ID/impacted endpoints, then use
the pre-approved deployment recovery path. Preserve historical installer URLs. Check
whether CMS, subscribers or analytics received new writes before any data recovery;
do not overwrite newer production records with an older D1 snapshot.

Keep all private source/resource backups outside this repository. Never publish an
incident report containing database rows, chat IDs, tokens, cookies or private paths.
Retain the original private repository/project until a verified stability period and
recovery are accepted. Old branch deletion requires its own exact approved candidate list.
