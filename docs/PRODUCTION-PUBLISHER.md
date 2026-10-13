# Protected Pages publisher — prepared, not activated

This is source publication to the existing `outpost-web` Pages project. It does not
publish a new desktop release, announce versions, create resources, or change
DNS, secrets, D1, Git integration, or the original Wrangler configuration.

## Dormant by default

`deploy-public-production.yml` is gated by both
`OUTPOST_PRODUCTION_DEPLOYMENT_ENABLED=1` and
`OUTPOST_PRODUCTION_WRITER_ENABLED=1`. No script sets either variable. It only
accepts reviewed current main, push-main or an owner dispatch from the main
workflow source. Production credentials are available only after the existing
protected `production` environment approval, not to PRs or quality jobs.

The complete smoke command inventory plus security, artifact integrity,
first-party resources, asset budget, sitemap freshness, navigation contracts,
redacted source/history scanning and four browser suites must pass before the
protected job. Checkout uses the exact event SHA, no persisted credentials and
no shorter deploy-only substitute for the smoke gates. All six existing PR
required checks and both desktop release preparation paths are unchanged or
strengthened.

## One attempt; explicit states

1. Read-only preflight: actual merged PR with latest owner review on its exact
   head; current main; protected environment; original config/runtime/bindings;
   no production deployment in flight; successful current baseline; safe confirmed
   notification mode. Old/unknown health or visitor-triggered mode blocks.
2. Record the baseline ID/source, normalized configuration digest, exact package
   digest, reviewed source and run ID. Persist this credential-free intent as a
   GitHub artifact **before** upload. No project configuration dump, raw tool/API
   logs, secret values, recipient identities, or database content are uploaded.
3. Export only reviewed tracked regular files under `site/` and the exact original
   `wrangler.jsonc` to a separate upload directory. Check every byte, hash and
   filename; reject symlinks, extra files and ancestor development configs.
   Wrangler 4.142.0 and its dependency integrity lock are reviewed; install with
   `npm ci --ignore-scripts`, outside the checkout and without credentials.
4. Fresh state comparison, then fsync an upload intent and issue one upload.
   No upload retries. Ignore printed success as proof: inspect actual canonical
   deployment/source/status, wait read-only at most four minutes for our own
   deployment, and reject another rollout or configuration drift.
5. Recheck actual exact deployment, current main and safe notification mode
   before **each** live verifier. Run the existing 20 live contracts. Record
   `live_pass` only after all pass. Any failure/uncertainty remains a failure.
6. If separately approved via `OUTPOST_PRODUCTION_ROLLBACK_ENABLED=1`, a critical
   live failure can restore only the recorded successful baseline, only while
   our identified deployment is still canonical and no intervening deployment
   or config change exists. Never restore databases or patch settings. A broken
   new health handler does not prevent metadata-only code rollback.
7. Persist the final small journal even when a command fails. A successful
   rollback does **not** turn a failed publication workflow green.

An existing journal, an upload intent, another run for the same source, a rerun
attempt, incomplete run history, multiple matching deployments, timeout or unknown
response blocks automatic replay. The read-only Actions token is used only to
check run identity/history, not to write status or claim quality PASS.

### Cross-source quarantine

Before preparing a plan and again immediately before an upload or rollback,
inspect the **unfiltered** history of the existing publisher workflow, not only
runs for the new commit. Its provider workflow identity and first run are pinned;
complete sequential run numbers starting at one detect deleted runs. Duplicate
identities, a recreated workflow, pagination drift, missing history, reruns, or
more than 1,000 runs block for a separate reviewed recovery decision. A new SHA
never clears an earlier unresolved attempt.

Each earlier completed run must have both its original `prepared` intent and a
linked final journal. Only `prepared` (no upload started), `live_pass` (all live
contracts accepted) or `rolled_back` (failed publication restored) is resolved.
All intermediate, failed-live, timeout and unknown states remain quarantined.
A workflow's green conclusion alone is never enough; rollback remains a failed
publication, not a green rollout. Journals bind the run/source, baseline, package,
configuration, review, event order and deployment identity to each other.

When **no** journal artifacts exist, require proof that the actual `publish` job
was skipped without steps or a runner. This permits dormant runs and failures in
unprivileged quality jobs; a missing result from an executed publisher blocks.
Missing, expired, duplicate, mismatched or unreadable artifacts are not silently
ignored. Validate the provider's SHA-256 archive digest and accept only one bounded
journal JSON entry; never extract paths or accept duplicate JSON keys. The signed
artifact-storage redirect receives no GitHub Authorization header and is never
logged or saved.

No recovery override or acknowledgment file is added. Retention expiry after an
executed run intentionally blocks future automatic publication, even for resolved
runs, until a separately reviewed durable evidence/reconciliation policy exists.
Keep the history and preserve unresolved evidence before expiry. These read-only
guards do not create a new transaction store or guarantee protection against a
privileged owner replacing the reviewed code, or an independent Cloudflare writer.

[GitHub run-number identity contract](https://docs.github.com/en/actions/reference/workflows-and-actions/variables),
[artifact identity, digest and archive download](https://docs.github.com/en/rest/actions/artifacts).

## Operator recovery and limitations

- `upload_unknown`, `rollback_unknown`, missing final artifacts, or an interrupted
  runner require inspection. Never press rerun/re-upload to "see if it works".
  Compare the saved intent, current deployment, complete inventory, config and main.
  Recovery authorization and any necessary reconciliation are separate actions.
- Intent/result artifacts have seven-day retention. Preserve unresolved evidence
  privately before expiry; do not delete unresolved run history. The journal is not
  a permanent external transaction store or an independent disaster-recovery backup.
- Provider metadata/reads do not give an atomic compare-and-swap with independent
  administrators. Shared workflow concurrency prevents this writer from interrupting
  itself; it cannot lock Cloudflare dashboard users or other systems. Exclude
  independent writers during rollout; any observed competing change stops recovery.
- A Pages rollback target must be a successful production deployment, not preview.
  The provider operation restores deployed code, not a SQL snapshot.
  [Cloudflare rollback contract](https://developers.cloudflare.com/pages/configuration/rollbacks/).
- Hidden encrypted secret values cannot be independently compared; only names/types
  and observable mode/config contracts are checked. No compiled-worker cryptographic
  attestation or mathematical exactly-once publication is claimed.

## Separate activation decision

The CI credential must be dedicated to the selected account with Pages Edit,
expiry and no D1/DNS/Workers mutation permissions. It is **account-level**, not a
provider-enforced per-project token; a code allowlist does not narrow the token's
inherent rights. Never copy an owner's broad interactive OAuth profile into CI.
[Official CI credential permissions](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/).

Before activation: human code review; explicit deployment/credential/mode/rollback
approval; controlled bootstrap of the new health schema; deliberate confirmed-mode
transition without an unsolicited broadcast; and a real protected pipeline acceptance
against the existing project. This preparation has only synthetic/offline tests,
not production end-to-end acceptance. The scheduler, release-confirmation linkage,
receipt provenance, retention/reconciliation and actual notification acceptance
remain separate work. No new Windows build/evidence is implied.

Keep the original configuration as the source of truth, not a generated preview
configuration or a config-free upload.
[Cloudflare configuration contract](https://developers.cloudflare.com/pages/functions/wrangler-configuration/).
