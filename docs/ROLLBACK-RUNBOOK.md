# Rollback and recovery

Operational checkpoint: 2026-10-15. Production is published from the new public
repository to the existing Pages project/domain. Original private repositories,
CMS/analytics bindings and historical installer URLs remain; the old Git
integration's automatic production builds are OFF. Do not re-enable it as a shortcut.

## Before publication

Retain the exact pre-release main SHA, compatible successful canonical deployment,
reviewed configuration/package identities and current private recovery evidence.
The publisher's two immutable journals bind those facts to its run/source. There is
no automatic backup branch per release. See [PRODUCTION-PUBLISHER.md](PRODUCTION-PUBLISHER.md).

CMS and analytics/subscription backups and independent local restore checks were
completed during migration; analytics was refreshed for subscriber activation.
These encrypted backups remain outside GitHub and Dropbox. Windows CurrentUser
encryption requires the same Windows profile: local restore PASS does **not** prove
offsite or cross-machine recovery. Record and separately test any portable recovery
plan before claiming it. Do not publish backup paths or database rows.

## Failure during an identified rollout

1. Stop rollout/notification progression. Record actual source, run, deployment,
   failed contracts and whether an operation may still be in flight. A failed or
   uncertain upload is NOT PUBLISHED, even if a command printed success.
2. Inspect immutable intent/final journals and current canonical state read-only.
   Never press rerun, issue another upload, clear history or invent a receipt to
   resolve an ambiguous outcome. A new source does not clear an unresolved attempt.
3. The separately enabled publisher rollback may restore **only** its recorded
   compatible successful baseline, while its own deployment remains canonical,
   with unchanged configuration and no intervening deployment. It restores code,
   not D1/settings/secrets. A successful rollback keeps the failed publication red.
4. Other recovery requires a separately reviewed exact-scope decision. A corrective
   or rollback PR uses the normal review/check/environment gates; no force-push,
   weakening protection, silent source downgrade or automatic history cleanup.
5. Verify actual canonical deployment and all applicable live contracts after
   recovery. Preserve failed source/evidence for diagnosis and the resolved history
   checkpoint before artifact retention expires.

Old deployments with a different binding/environment contract are not compatible
rollback targets merely because their metadata says success. The intentional
subscriber configuration bootstrap established the current compatible baseline;
do not replay it or manufacture protected CI context for a manual operation.

## Delivery and data are separate

Do not roll back accepted website code solely because confirmation or Telegram
delivery is pending/unknown. A lost Telegram acknowledgement is not permission to
resend. Follow [CONFIRMED-TELEGRAM-RELEASES.md](CONFIRMED-TELEGRAM-RELEASES.md),
retain uncertainty and obtain explicit reconciliation authority when needed.

Before any data recovery, check for newer CMS edits, subscriptions and analytics
writes. **Never restore an old D1 snapshot over newer production data** as part of
code rollback. Website rollback must not modify customer desktop databases,
private Cabinet/Director/Sync services, licensing, fiscal or payment records.

Keep historical EXE/checksum URLs immutable; correct bad binaries with a genuinely
new version, not changed bytes at an existing URL. A source rollback cannot make
already-published Git history private. Suspected credential exposure requires a
separate controlled incident/rotation procedure, not just deleting a line.

Retain the original private repositories and recovery material until an accepted
stability/recovery decision. Branch/PR cleanup is separate and needs verified
ancestry, active-work/rollback checks and exact-list approval; see
[BRANCH-RETENTION.md](BRANCH-RETENTION.md). Age alone does not authorize deletion.
