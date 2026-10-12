# Public repository boundary

Only the allowlisted website, reviewed runtime, public-safe documentation, immutable
downloads and exact four reviewed schema migrations belong here. Desktop source and
dependencies, runtime data, SQL exports/seeds, database files, private reports/archives,
credentials and editorial history stay private. The original private repositories and
Git history are not made public by this migration.

The security job uses a read-only token with no persisted checkout credentials, exact
official Action pins, full-redaction Gitleaks scans of working source **and the new
public Git history**, reviewed screenshot hashes, decoding/EXIF/blank/tiny-image checks,
installer integrity and append-only artifact validation against the exact PR base.
No `pull_request_target` checkout or production secret access is allowed.

Automated scanning does not certify absence of all PII, license problems, malicious
payloads or misleading screenshots. Human source/screenshot/installer review remains
required; review manifests bind the exact bytes so a replacement needs renewed review.

Workflow/release/runtime changes need protected review. Owner-reviewed Windows receipt
digests are public attestations, not signing credentials or executable test reports.
See RELEASE-RUNBOOK.md for their trust boundary. A web CI PASS is not Windows acceptance.

Production activation variables remain unset, new-repository secrets are absent, and
the existing production deployment is unchanged until separate owner go/no-go.
