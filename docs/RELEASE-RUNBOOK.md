# Release preparation — two independent products

Migration checkpoint: 2026-10-12. This is preparation, **not** production publication.
Production cutover, live verification and confirmed Telegram dispatch are still
separate migration gates. Current products remain OutPOSt 0.24.39 / Accounting 1.0.2.

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

`release/artifact-registry.json` contains the 22 audited existing artifact pairs.
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
`OUTPOST_RELEASE_PREPARATION_ENABLED=1` is deliberately configured after migration review.
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
Path-filtered workflows that did not run remain pending, **not PASS**: dispatch those
workflows for the exact topic branch and verify head SHA, job execution and conclusion.
No fabricated check statuses, renamed required contexts, or reduced review rules.

## Publication remains gated

Next gates: isolated Cloudflare preview, private D1 backups/restore drill, approved
deployment provenance, explicit owner cutover, actual installer/page re-download and
live PASS. Only then may a confirmed `release_published` event trigger the future
delivery journal. Existing visitor-triggered production Telegram logic is unchanged
during preparation; never test it against real subscribers or reset their cursors.

Preparation is not idempotent publication: repeat apply to an already-current version
fails closed rather than making another release. An interrupted/partially applied
local preparation must be inspected and recovered in a clean topic checkout; do not
silently overwrite artifact URLs or report a partial write as a published release.
