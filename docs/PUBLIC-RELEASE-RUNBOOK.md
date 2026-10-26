# OutPOSt release — operator steps

Operational checkpoint: 2026-10-26. The protected public-repository publisher is
active. The optional **Prepare public release PR** Action remains OFF; do not enable
it or Actions PR-creation permissions as a workaround. The supported local path
uses the same reviewed preparation tool. The authoritative receipt schema,
immutability and review rules are in [RELEASE-RUNBOOK.md](RELEASE-RUNBOOK.md).

## Prepare four inputs

Use a clean `codex/...` topic based on fresh main and record the exact base SHA.
Do not start release work by editing protected main or overwriting staging.
For a genuinely new, approved Windows `net48/x86` version `X.Y.Z`, add:

```text
A  site/downloads/OutPOSt-Setup-vX.Y.Z.exe
A  site/downloads/OutPOSt-Setup-vX.Y.Z.sha256.txt
A  release/evidence/outpost-vX.Y.Z.json
M  site/changelog.html
```

The checksum line is `<SHA256> *OutPOSt-Setup-vX.Y.Z.exe`. Independently compare
the exact bytes, size, product/version, signatures and receipt against the private
trusted Windows reports. A receipt's PASS string is not proof that Windows ran.
Keep the reports and their private paths out of Git and PR output.

Author the changelog entry; preserve the complete old history. Its current marker
must contain `<strong>X.Y.Z</strong>` inside `changelog-version`, and the hero CTA
must say `Завантажити vX.Y.Z`. Do not invent notes from the version number.

Do not replace an installer under an existing URL, delete its predecessor, or
mix Accounting, Worker, Telegram, headers or Cloudflare changes into a release.
If `.release-hold` exists, resolve its recorded cause with reviewed correct inputs;
do not remove the hold merely to obtain green CI.

## Dry-run, review, apply

```text
python scripts/prepare_public_release.py X.Y.Z
python scripts/prepare_public_release.py X.Y.Z --apply
python scripts/prepare_public_release.py --check-current
python scripts/run_production_quality.py
```

The first command writes nothing. Inspect its plan **before** the second command.
Apply updates the allowed public current-version references/sitemap and appends the
immutable registry. It does not deploy, send Telegram, change runtime/D1 or touch
the Accounting binary/version/checksum. Also run the browser suites and redacted
source/history scans; inspect `git diff --check` and every changed file.

Repeat preparation for an already-current version fails closed. Inspect partial
local preparation in its owned topic; do not blindly retry or relabel old bytes.

## Review and accepted publication

1. Push only the reviewed topic and open a PR to main. Record exact head/base SHA;
   stale checks on a closed/reused PR do not certify its advanced source branch.
2. Require owner review and all six actual exact-head required checks, not just
   public smoke. No direct main push, forged status, bot self-approval or weakened gate.
   **Squash merge caution:** always keep GitHub's generated `(#PR_NUMBER)` suffix
   in the merge commit subject, including when specifying `commit_title` via API
   (example: `docs(site): update content (#82)`). The separate
   `verify_main_push_provenance.py` post-check requires a recognized PR marker.
   PR #81 was published successfully, but its custom squash title omitted `(#81)`;
   the independent live verification therefore reported an avoidable failure.
   Do not rewrite published history or disable the provenance guard to conceal it.
3. After merge, the protected publisher runs static and browser quality again.
   Its production environment still requires approval. The exact main SHA is the
   rollback reference; no new backup branch is automatically created per release.
4. Accept publication only from the identified deployment and linked immutable
   journals recording all 20 live contracts PASS. These include actual installer
   range/re-download bytes, SHA/size, pages, checksum, sitemap, canonical/privacy,
   metadata and integration-boundary contracts. Merge/printed upload success is insufficient.
5. Separately inspect future-only confirmation and the scheduled pump's positive
   delivery acknowledgement. Do not manually confirm/pump again because the message
   has not arrived yet. Pending and unknown require different handling.

The optional Action, if separately enabled later, first proves trusted main/staging
ancestry and the **four-input** allowlist, then prepares an isolated `codex/...`
release PR with full gates. It does not merge, synchronize staging, deploy or notify.

See [PRODUCTION-PUBLISHER.md](PRODUCTION-PUBLISHER.md),
[CONFIRMED-TELEGRAM-RELEASES.md](CONFIRMED-TELEGRAM-RELEASES.md) and
[ROLLBACK-RUNBOOK.md](ROLLBACK-RUNBOOK.md). Current published baseline OutPOSt 0.24.46 must
not be re-announced; next-release live delivery acceptance remains pending until
a genuinely new approved package exists.
