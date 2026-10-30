# Signed desktop update feed — bootstrap

The public JSON at `/updates/desktop/stable.json` describes an already approved,
immutable OutPOSt installer. This bootstrap describes the existing 0.24.46 bytes.
It does not release a new installer, enable an installed application's automatic
updates, change a store or initiate a Telegram message.

The first future OutPOSt installer containing the Update Center still needs normal
Windows acceptance and one manual installation. Real updater/UAC/restart acceptance
in an isolated Windows environment remains required before activating that feature.
Website checks or a signed feed do not replace native acceptance.

## Acceptance status — 2026-10-27

OutPOSt 0.24.48 enables the native application and embedded runner installation
gates after Windows acceptance. Automatic updates default on, can be disabled
in the Update Center, and install only during the next safe normal exit. That
automatic exit leaves the program closed; confirmed manual installation restarts
it as the original Windows user. An explicit opt-out survives the next launch.

The acceptance exercised the production runner with isolated registry, cache,
mutex, test key and probe-application boundaries. Real Inno replacement passed
both normal and administrative/UAC runs: cancellation, complete parent exit,
version replacement, original-user child/restart, normal-exit behavior and
unchanged database/license sentinels. The owner confirmed the Windows prompts.
Actual native WPF, backup/shutdown, signed-package checks and the production
installer's connector/Inno gates were also verified on the exact release payload.
The working store installation was not replaced for this test. The reviewed
receipt is `release/evidence/outpost-v0.24.48.json`.

The installed 0.24.47 client still has its old installation gate disabled. Its
first upgrade to 0.24.48 needs the normal installer; publishing a newer signed
JSON cannot change code already installed on a customer's computer. The initial
0.24.46 bootstrap description above is historical, not the current feed version.

## Native login — 0.24.50

The current signed feed describes the separately accepted immutable0.24.50 installer,
whose receipt is `release/evidence/outpost-v0.24.50.json`. Its native Settings → License
supports email-delivered codes and existing account passwords, without browser approval.
Only the scoped DPAPI device proof persists, across restarts/upgrades without calendar
expiry until explicit logout. Offline logout is durable, pauses first-party exchange and
queues scoped server revocation while preserving offline licensing and business data.
Existing0.24.48 browser approval remains supported by the server for compatibility.

Actual native account/WPF97, server authentication34, isolated core132, integration13,
updateWPF34, XPS39, currency49, shutdown15 and the required production installer gates
passed. The production updater sources and actual embedded runner are unchanged from
the accepted48 lifecycle above (SHA-256
`7A9D09DAF40DBF1C39C0FA4D7A6EB56BC1AB914A2DFC5C7F8D3F658B58B45903`).
Reuse of protocol85 and the normal/admin-UAC acceptance is explicit; the actual50 app
gate and independent runner argument guard were also verified. This does not claim
another50 administrative replacement or an upgrade of the working shop installation.

The real pinned-key service and actual Update Center window from immutable47 and48
verified the signed50 envelope, full reviewed installer bytes and SHA-256 in isolated
HTTP fixtures.47 exposes Download/Open folder and retains its disabled installation
gate; the user closes OutPOSt and runs the downloaded normal installer once.48 exposes
Install and the normal-exit automatic policy.50 recognizes its own version as current.
The installed47 executable hash was read-only matched to that immutable probe binary.
Live full download/readback with both older clients is required after this publisher
completes; fixture acceptance must not be described as a public live download.

Publishing metadata cannot alter the gate compiled into an already installed47.
Native probes use temporary profiles and never invoke an installer or touch working
licensing/data. The signed envelope contains no private key or customer information.

## Normal update close — 0.24.51

At the owner's explicit request,0.24.51 removes the mandatory full pre-update
archive and its30-second wait/busy-backup prerequisite. Its application invokes
the same normal graceful-close path before committing the installer handoff.
Fiscal/document guards, clean-session handling and durable committed DB/WAL data
remain. Independent scheduled/manual backups are unchanged. The confirmation text
describes this behavior. Receipt: `release/evidence/outpost-v0.24.51.json`.

The regression first fails on immutable50 with the exact busy-copy error, then
passes on51. Actual WPF40 checks cover a held backup lock, no added archive,
fiscal/cancel safeguards and a real32MiB database with a pinned WAL reader. Close
took25ms in the final acceptance run; a separate restarted process read the
committed stamp and payload size from preserved WAL. This is a test measurement,
not a universal timing promise. Native account97, isolated core132, integration13,
XPS39, currency49, shutdown15 and the mandatory production installer gates pass.

The signed independent updater, protocol/handoff sources and embedded runner are
unchanged (SHA-256
`7A9D09DAF40DBF1C39C0FA4D7A6EB56BC1AB914A2DFC5C7F8D3F658B58B45903`).
Reuse of protocol85 and the real48 normal/admin-UAC lifecycle acceptance is explicit;
new51 application close behavior has its own actual WPF/WAL/shutdown evidence.
No new51 administrative replacement or working-shop upgrade is claimed.

An already installed48/50 still executes its compiled full-copy prerequisite.
If it blocks this first transition, close normally and run the normal51 installer
once; future updates initiated from51 do not require a full archive. Metadata
cannot alter code already installed. Old50 and current51 real pinned-key fixtures
verify the signed51 envelope/full package (no installer execution). Live full
readback is required after protected publication. Older47 retains its existing
Download/Open-folder/manual first-upgrade rule.

## OutPOSt 0.25 (package 0.25.0)

The signed stable feed and installer are published together with the current
website release metadata. Canonical package version 0.25.0 preserves the existing
X.Y.Z update contract; the product release family is 0.25. The pinned public key,
minimum updater version and independent runner are unchanged. Receipt:
`release/evidence/outpost-v0.25.0.json`.

Actual isolated copies of the accepted 0.24.51 and 0.24.52 Update Centers verified
the new signed envelope and complete installer bytes and exposed Install. The
0.25.0 Update Center identifies itself as Current. No installer was executed by
these download probes. Live download readback is required after publication.
The embedded runner SHA-256 remains
`7A9D09DAF40DBF1C39C0FA4D7A6EB56BC1AB914A2DFC5C7F8D3F658B58B45903`;
its previously accepted normal/admin-UAC lifecycle is inherited explicitly.
The current installer also passed its own trial/pairing/connector, real Inno
replacement and protected-temp gates. This is not a claim of another full
administrative installation on a real shop PC.

Older 0.24.47 keeps its existing Download/Open-folder first-upgrade path. An
already installed 0.24.48/50 retains its compiled backup prerequisite; if that
blocks its first upgrade, close normally and run the regular 0.25.0 installer
once. Metadata cannot modify code already installed. From 0.24.51 onward,
installation uses normal safe shutdown without an additional mandatory full
archive. Existing document/fiscal guards remain.

Services, currencies and recovery checks run on synthetic isolated databases.
The 118-table large-database equivalence from the accepted 0.24.52 candidate is
inherited because business database source is unchanged. The new database
recovery action never rewrites old store IDs or merges histories: explicit
administrator consent connects a separate database, with server ownership,
fingerprint, expiry and race checks. Web Services/Accounting compatibility is
separate from this desktop publication; Goods sync retains its legacy fallback.

## Verification

The envelope signs raw UTF-8 payload bytes with RSA-3072/PKCS#1 v1.5/SHA-256. Its
public key is `release/desktop-update-public-key.xml`; the native UI and independent
runner pin the same key. No private key is stored here or provided to Actions.
The existing owner's protected local release process creates the signed envelope
only after receipt, actual installer bytes and authored notes have been reviewed.
It neither changes approvals nor creates a Windows receipt.

The source guard verifies the signature, key/product/channel/architecture, bounded
validity, exact first-party versioned URL, size and SHA-256. It compares actual
installer bytes, the reviewed Windows receipt and immutable registry entry. A
future/unpublished version is rejected. The small fixture uses a DIFFERENT public
test key and a deliberately fictional payload, never the production signing key.

Run `python scripts/desktop_update_feed.py` and
`python scripts/test_desktop_update_feed.py`. Both are in the normal smoke inventory,
so the existing protected publisher runs them with the other source gates. Public
readback must additionally match the exact reviewed JSON bytes after deployment.

## Advancing the feed

Keep the existing four-input Windows release contract intact. The signed feed is
a separate, reviewed infrastructure follow-up to a genuinely new accepted Windows
release. After that release's receipt, exact immutable EXE and authored notes exist:

1. Verify the private Windows reports and publication approval using RELEASE-RUNBOOK.
2. Sign metadata locally with the existing protected key; publish neither the private
   key nor its backup. Preserve the actual release date. Metadata issuance/expiry
   can be refreshed without falsely changing the product's publication date.
3. Stage only the signed JSON in an owned `codex/...` topic from fresh main and run
   the full source/browser/security gates. The guard requires that the described
   artifact already belongs to the current or an earlier public release.
4. Obtain exact-head owner review and all six real PR checks, merge normally and
   use the existing protected publisher. Confirm exact live JSON hash, headers and
   a native client check before calling the update feed advanced.

If practical, prepare the reviewed follow-up alongside release work and publish the
combined current main only after both changes merge. Never skip a publisher gate,
fake an acceptance receipt, merge arbitrary workflow changes into a four-input
release, or mark a new desktop update operational while the feed still describes
the previous version. The four-input release and feed advancement are separate
facts until live readback confirms the target signed metadata.

This bootstrap intentionally does not add unattended CI signing or broaden bot
permissions. An expired or invalid description makes the client show an unavailable
check; it cannot cause execution of an unsigned/unverified installer. Refresh a
description through the same reviewed path before its expiry (normally 90 days).

## Accounting connector process guard — 0.25.1

A real old-client update exposed a missing combined acceptance case: the runner
classified the headless Accounting supervisor/server (hosted by OutPOSt.exe) as a
second POS and aborted before Setup's existing graceful connector bridge ran.
Earlier isolated runner and installer tests had exercised those stages separately.

0.25.1 permits only exact supervise/autostart/serve commands with the same installed
image, Windows owner and session to reach Setup. A second POS, unknown arguments
or unverifiable process metadata still blocks installation. Setup retains its
source/config validation, saved recovery intent, graceful stop and original-user
resume. Signature/hash, parent exit, single-instance and normal-exit rules remain.

Combined tests reproduce the old failure and exercise the new production runner
and bridge together with real Inno replacement: cancellation, manual restart and
automatic normal-exit install, both connector roles, configuration and synthetic
data/license sentinels. Existing elevation-launch acceptance is inherited explicitly;
the new guard does not change that launch code.

An already installed old runner cannot gain this fix from signed feed metadata.
Its first transition requires one graceful connector pause, with its configuration
and restart intent preserved, then the normal Update Center installation.
Future transitions from 0.25.1 delegate connector pause/resume to Setup.
