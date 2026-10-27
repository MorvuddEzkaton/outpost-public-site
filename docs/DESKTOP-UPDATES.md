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
