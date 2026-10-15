# Release preparation — two independent products

Operational checkpoint: 2026-10-15. The new public repository is the production
source; the protected publisher, post-live future-only confirmation and scheduled
pump are active. Current products at this checkpoint are OutPOSt 0.24.40 and
Accounting 1.0.2. Preparation, merged source, accepted live publication and an
acknowledged Telegram delivery are four different facts. Do not conflate them.

The release-preparation Actions remain OFF, as does repository Actions permission
to create PRs. Use the local topic-branch path below without changing either
setting. The manual Telegram pilot is also OFF and must not be replayed.

## Trust and evidence

Use a genuinely new, approved private Windows release package. Never use a synthetic
test binary, the highest filename version, or green website tests as Windows evidence.
Compare its installer, payload manifest, build release report and Windows acceptance
report. Keep original reports, paths, databases and credentials outside this repository.
Compute their SHA-256 locally; record only the reviewed public fields below.

`release/evidence/outpost-vX.Y.Z.json` or `accounting-vX.Y.Z.json` has **exactly**:

- `schema_version`: integer 1; `kind`: `owner-reviewed-windows-release`.
- `product`: `outpost` or `accounting`; `version`: X.Y.Z; exact `installer` basename.
- `size_bytes`: exact integer length; `sha256`: exact uppercase installer SHA-256.
- `payload_manifest_sha256`, `release_report_sha256`, `windows_report_sha256`:
  exact uppercase digests of the corresponding private evidence files.
- `windows_acceptance`: `PASS`; `runtime`: `net48`; `architecture`: `x86`.
- `app_authenticode`, `setup_authenticode`: the actual `Valid` or `NotSigned` state.
- `published_date`: explicitly approved YYYY-MM-DD, not inferred from the host clock.
- `approved_for_publication`: boolean true **only after** approval of that package.

A JSON receipt is a **reviewed attestation, not a digital signature**. The scripts
verify its schema, exact product/version/PE bytes/hash and declared states, but cannot
establish that a Windows test really ran from a PASS string. The independent owner
review must compare these report digests and assertions with the original trusted
reports before accepting a release PR. Report hashes alone do not authorize publication.

Unsigned builds stay unsigned in public copy. An invalid/unverified signature is
not silently relabeled unsigned. RC NOT_VERIFIED cannot advance either product.
Test fixtures use invented attestations in temporary directories only; no test
attestation is a real release or committed to `release/evidence`.

## Immutable downloads

`release/artifact-registry.json` contains the audited artifact pairs (23 at this checkpoint).
It is append-only, with exact installer and checksum-file digests. All historical
URLs and bytes must remain. The CI compares it with the **exact PR base**. Initial
registry bootstrapping is limited to the recorded independent public root commit
and compares its actual 22 Git artifact blobs; later commits require the registry.

Never replace an EXE/checksum under an existing version, even to “repair” it. Publish
a new version instead. Artifact removal/storage migration needs a separate reviewed
plan. A normal release cannot delete old downloads. Pages' 25 MiB per-file limit is
checked before acceptance; larger artifacts require an approved storage design.

## OutPOSt

Stage exactly four inputs relative to current main: new OutPOSt EXE, matching checksum,
authored changelog update (retain every previous release), and reviewed Windows receipt.
No scripts, workflows, Worker, other product binaries or runtime configuration may
ride along as release inputs.

```text
python scripts/prepare_public_release.py X.Y.Z
python scripts/prepare_public_release.py X.Y.Z --apply
python scripts/prepare_public_release.py --check-current
```

Dry-run does not write anything. Apply updates current public metadata and appends
the registry, retaining historical binaries. It does not deploy or notify Telegram.

## Accounting

Stage exactly three inputs: new Accounting EXE, reviewed receipt, authored changelog.
The target changelog section must have `id="accounting-XYZ"` (dots removed) and a
visible `Бухгалтерія X.Y.Z` heading. The tool generates the new checksum/manifest and
updates /buhgalteriya, the Accounting download panel, /features and their sitemap dates.
The receipt date must not predate any changed page's lastmod. The old Accounting EXE
and checksum remain **by default**, even without the compatibility `--keep-previous`.

```text
python scripts/prepare_accounting_release.py X.Y.Z
python scripts/prepare_accounting_release.py X.Y.Z --apply
python scripts/prepare_accounting_release.py --check-current
```

Optional `--rc-acceptance` / `--authenticode` are assertions checked against the receipt,
never substitutes for it. Neither has a default that can fabricate successful acceptance.
Accounting keeps the truthful Pre-release status; the other product's binary, version
and checksum remain unchanged. Changelog notes must be authored, not invented by tooling.

## GitHub preparation and approval

`prepare-public-release.yml` and `prepare-accounting-release.yml` are manual only,
trusted-main/owner/repository restricted and inactive until
`OUTPOST_RELEASE_PREPARATION_ENABLED=1` is deliberately configured under a separate reviewed plan.
Do not enable it as a shortcut around a failed test, review, or incomplete migration.
Default workflow permissions stay read-only; only these gated preparation jobs request
contents/PR write permissions. They check out trusted main and prove staging contains
only the exact input allowlist **before** executing any staging script. Their full
static gates run before pushing an isolated `codex/...` release branch.

The rollback point is the exact main SHA, not a new backup branch for each invocation.
No force-push, automatic merge, main/staging mutation, deployment, D1 write or broadcast
is part of preparation. GitHub Actions permission to create bot-authored PRs is presently
disabled; enabling it needs a reviewed, narrow automation plan. Never let a bot approve
its own release. A human PR author cannot supply their own required approving review.

All six actual required checks must pass on the exact final commit: source security,
public smoke, combined browser suites, resources, asset budget, sitemap freshness.
Required workflows run on every main PR. A workflow that did not run remains pending,
**not PASS**: repair its PR trigger and verify the actual pull_request run on the exact
head. A workflow_dispatch diagnostic run does not substitute for required PR checks.
No fabricated check statuses, renamed required contexts, or reduced review rules.

## Current local preparation path

1. Verify a clean checkout and fresh remote main; record that exact SHA as the
   rollback/source base. Create a `codex/...` topic from it. Do not overwrite a
   dirty checkout, force-push main/staging or merge unrelated staging changes.
2. Add only the product's inputs above. Review the trusted Windows evidence and
   authored notes, run its dry-run, inspect the plan, then run `--apply`.
3. Review every changed file, immutable registry append and the unchanged other
   product. Run `python scripts/run_production_quality.py`, the browser suites and
   redacted source/history scans. A local PASS is not actual GitHub CI or Windows acceptance.
4. Push only the topic and open a reviewable PR through the existing authorized
   path. Obtain exact-head owner review and all six real required PR checks. When
   Codex acts under explicit owner delegation, identify that as delegated approval,
   not an independent human review. Do not let the PR-authoring bot self-approve.
5. After normal merge, require both publisher quality jobs, the protected production
   approval, one identified upload and all 20 live contracts. Preserve the two
   immutable publisher journals and their source/run/deployment linkage. See
   PRODUCTION-PUBLISHER.md; never rerun an ambiguous or already-used source.
6. Inspect the separate confirmation result for the genuinely new product and the
   pump's persisted acknowledgement. A green deploy or `release_announced:false`
   in the code writer's journal does not establish either delivery success or failure.
   See CONFIRMED-TELEGRAM-RELEASES.md for pending/unknown outcomes.

Do not synchronize staging as a side effect of publication. The optional gated
preparation workflows require a separately prepared staging descendant of fresh
main with exactly the input allowlist; current staging need not already meet it.

## Publication and remaining acceptance

The existing production domain, D1 bindings, subscriber rows/cursors and private
services are preserved. Legacy visitor-triggered announcements are disabled;
only confirmed future releases enter the delivery journal. Never reset cursors,
announce baseline versions, create a fake release or repeat the completed pilot
to make an acceptance checklist green.

Both-product offline independence/negative tests and current live artifacts are
verified. The next genuinely new approved release of **each** product must still
record installer/download/changelog/metadata live PASS and its own positive
Telegram acknowledgement without a duplicate. An empty Cron or the earlier
private OutPOSt pilot is not that end-to-end proof. Track this pending acceptance
in the private migration report; no new Windows build is authorized by these docs.

Preparation is not idempotent publication: repeat apply to an already-current version
fails closed rather than making another release. An interrupted/partially applied
local preparation must be inspected and recovered in a clean topic checkout; do not
silently overwrite artifact URLs or report a partial write as a published release.
