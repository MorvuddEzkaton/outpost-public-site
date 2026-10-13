# Protected Pages publisher — prepared, not activated

This is source publication to the existing `outpost-web` Pages project. It does not
publish a new desktop release, announce versions, create resources, or change
DNS, secrets, D1 or Git integration. It uploads only the exact reviewed Wrangler
configuration; it does not patch provider settings.

## Declared runtime mode (source preparation only)

The nonsecret `TELEGRAM_CONFIRMED_RELEASES_ENABLED="1"` is declared in production
`vars`, with `env.preview.vars={}` explicitly preventing inheritance. A plain-text
project setting alone is not sufficient when the vars-free Wrangler file owns
runtime Worker bindings: a controlled attempt produced new health schema 1 but
confirmed=false/legacy=true despite matching project/deployment metadata. It was
restored, not accepted. Do not substitute a synthetic environment or metadata for
actual canonical health, resubmit that source, or silently convert the flag to a
secret/change other bindings.

The current exact file pin is `1250f89a51fd987f0829d2e9772afd658943d956666259661ceaecfe212bfcf6`.
Runtime date and both D1 environments are unchanged. Remote **preview** retains
its independent legacy configuration marker
`a3d4877bd8247b79f20c1e90cfce6577d28a62cd276870acd6942df782ecc49d`:
production publication must not force a preview upload or mutate its settings.
Unexpected variables/values/fields or either environment's marker drift block.
The full stable project fingerprint and baseline environment equality remain strict.

Historical evidence understands only these two explicitly reviewed pins; current
operational intents/packages accept only the current pin. Legacy resolved evidence
is not discarded, but legacy intents cannot authorize a new upload. Unknown or
unresolved old attempts still quarantine all source SHAs. No checkpoint rewrite,
retention reset, history pruning or automatic-recovery override is added.

This source/config change does **not** publish, activate a writer, create keys,
initialize release SQL, enable a scheduler or announce a desktop release. A new
explicitly approved bootstrap and compatible successful baseline are still needed
before protected writer acceptance. Old preview or legacy-mode deployment metadata
alone cannot qualify as a compatible code-only rollback target.
[Cloudflare Pages configuration source of truth](https://developers.cloudflare.com/pages/functions/wrangler-configuration/).

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
   head; current main; protected environment; exact approved config/runtime/bindings;
   no production deployment in flight; successful current baseline; safe confirmed
   notification mode. Old/unknown health or visitor-triggered mode blocks.
2. Record the baseline ID/source, normalized configuration digest, exact package
   digest, reviewed source and run ID. Persist this credential-free intent as a
   GitHub artifact **before** upload. No project configuration dump, raw tool/API
   logs, secret values, recipient identities, or database content are uploaded.
3. Export only reviewed tracked regular files under `site/` and the exact approved
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
complete sequential run numbers starting at one detect unaccounted missing runs. Duplicate
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

No recovery override or acknowledgment file is added. A reviewed source checkpoint
can preserve **already verified resolved** evidence before retention expiry. Missing
evidence without that checkpoint still blocks, including an unknown attempt whose
provider history has expired. These read-only guards do not create a transaction
store or guarantee protection against a privileged owner replacing reviewed code,
or an independent Cloudflare writer.

[GitHub run-number identity contract](https://docs.github.com/en/actions/reference/workflows-and-actions/variables),
[artifact identity, digest and archive download](https://docs.github.com/en/rest/actions/artifacts).

### Bounded production deployment inventory

Read the provider's **production-only** deployment inventory with
`env=production&per_page=20`, not `per_page=100` (rejected by the actual Pages API).
Preview deployments cannot be successful production baselines or competing
production uploads; preview configuration/bindings remain protected by the
unchanged complete project fingerprint and configuration guard.

Require exact page/size/count/total-pages metadata, a stable total count, complete
pages, unique deployment IDs and production scope on every row. Never accept a
truncated prefix, ignored filter, shifted page, duplicate or failed read. Retain
the 1,000-record bound (at most 50 read-only requests). Larger production history
requires a separate reviewed policy, not automatic pruning or relaxed checks.
The initial journal IDs refer to this complete production inventory. This change
does not limit the unfiltered **GitHub publisher run** history/quarantine above.
All upload, rollback, current main, journal and notification-mode guards remain.
[Cloudflare deployment-list contract](https://developers.cloudflare.com/api/resources/pages/subresources/projects/subresources/deployments/methods/list/).

### Owner-reviewed append-only checkpoint

`release/production-history-checkpoint.json` was introduced with an **empty genesis**
in PR7. Real evidence is appended only through a separate verified, owner-reviewed
PR. The initial capture preserves runs 1–3: each actual `publish` job was skipped,
had no steps or runner, and produced no journal artifacts. These records prove
**no publisher operation**, not a successful site rollout or live acceptance.
The publisher has no repository-write permission and does not append checkpoints.

An explicit read-only preparation tool can produce a candidate outside Git:
`python scripts/verify_production_checkpoints.py --capture --output <new-external-file>`.
Only when separately authorized, provide an existing Actions-read credential on
stdin through a private helper, never an argument, terminal history or a tracked
file. The tool reads only the pinned workflow/run/job/artifact endpoints. It has
no Cloudflare client and cannot publish, change a setting, repair a run or send
Telegram. Unknown, running, incomplete or expired evidence produces no candidate.
No token creation, automatic capture, schedule, push or approval is included.

The readable candidate contains only fixed-schema run identities, a minimal
skipped-publisher proof or the two validated journals and artifact identities.
ZIPs are decoded after checking the provider digest; their raw bytes, comments,
signed URLs, logs, actors and free text are never copied to the public ledger.
Each record includes a canonical-content hash linked to its predecessor. These
hashes detect corruption, **not** an independent provider signature.

Copy the safe candidate into a topic branch and obtain the existing required
owner review. The security PR job receives only `contents: read` and
`actions: read`; it compares against the **exact PR base** and downloads live
provider evidence for every newly appended record before it expires. The initial
empty-ledger PR and subsequent changes without new records make no evidence API
requests. It has no operational secret or write permission.

Runtime requires the exact tracked ledger bytes and complete Git ancestry, from
empty genesis through **every** append-only ledger revision. Existing records may
not be edited, removed, reordered, reset or replaced; new records form a contiguous
resolved prefix from the pinned first run. The limits are 8 MiB, fewer than 1,000
archived runs and at most 256 ledger-changing commits; exceeding them blocks for
a separate reviewed maintenance/recovery decision, not automatic pruning.

Previously reviewed records do not need their expired artifacts downloaded again.
Live run metadata, when still present, must match the archived identity, final
status and attempt exactly. A rerun or competing change blocks. A retained prefix
may cover provider-deleted historical runs; any gap after that prefix blocks.
Archived SHAs still participate in the original same-source no-replay rule. A
new SHA, a successful CI check or a manually written "acknowledged" record cannot
clear an unknown attempt.

Keep capture/review ahead of the shortest evidence retention. GitHub's current
retention rules affect workflow runs/checks/statuses as well as artifacts/logs;
loss of a never-checkpointed run cannot be guessed away.
[GitHub retention policy](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository).
Default offline validation is `python scripts/verify_production_checkpoints.py`;
it does not consume credentials or contact any service.

## Operator recovery and limitations

- `upload_unknown`, `rollback_unknown`, missing final artifacts, or an interrupted
  runner require inspection. Never press rerun/re-upload to "see if it works".
  Compare the saved intent, current deployment, complete inventory, config and main.
  Recovery authorization and any necessary reconciliation are separate actions.
- Intent/result artifacts have seven-day retention. Capture and separately review
  resolved evidence before expiry. Preserve unresolved evidence privately for
  investigation, never append it as resolved; do not delete unresolved history. The journal is not
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
- Checkpoints address retention only, **not** first-rollout compatibility. New
  encrypted binding names can make the existing five-binding legacy deployment
  incompatible with the guarded rollback target. Do not activate the writer,
  add bindings or promise rollback to the old code until a separately approved
  bootstrap has established and checked a compatible successful baseline.
  A legacy metadata snapshot is not proof that the new runtime binding applies.
  Recovery must not overwrite hidden secret values or restore SQL over new data.

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
receipt provenance, real checkpoint capture/review and actual notification acceptance
remain separate work. No new Windows build/evidence is implied.

Keep the exact reviewed configuration as the source of truth, not a generated preview
configuration or a config-free upload.
[Cloudflare configuration contract](https://developers.cloudflare.com/pages/functions/wrangler-configuration/).
