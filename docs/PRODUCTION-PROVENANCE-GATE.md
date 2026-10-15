# Protected production provenance

Operational checkpoint: 2026-10-15. This read-only gate is used by the active
protected publisher/live verification. It cannot enable a writer, change settings
or send a message. Future-only notification acceptance remains a separate fact.

The Pages publication path must preserve the exact currently reviewed `wrangler.jsonc`.
Publishing without that file can clear its configuration marker even when D1
bindings and runtime settings survive. Never substitute an isolated-preview file,
reconstruct encrypted values or accept unexplained configuration drift.

The reviewed production-only nonsecret mode flag is declared in `vars`, not just
project metadata. Preview explicitly overrides `vars` with an empty object; its
remote configuration marker stays independently pinned to the previous baseline.
This is a narrow deliberate source/config change, not acceptance of arbitrary vars
or automatic preview updates. Existing runtime, D1, secrets, domains and protections
remain unchanged. Actual runtime health remains mandatory: a controlled plain-text
project-only attempt failed this gate and was restored rather than marked successful.

## Before any canonical live GET

`scripts/production_deployment_gate.py --check` is read-only and requires:

- this repository, trusted `refs/heads/main` workflow source and exact event SHA;
- owner-only manual dispatch or a main push, with the production activation switch;
- the current remote main SHA and exactly one actual merged PR for that commit;
- the latest human owner's APPROVED review on the exact PR head (a commit-message
  `#PR` marker or historical review does not substitute for this);
- a production environment with an owner reviewer and only the `main` branch policy;
- a clean exact checkout, reviewed config blob and existing runtime/D1 contracts;
- the canonical Pages deployment with that same SHA, production/main, success and
  dirty=false, matching deployment/project secret names/types;
- a fresh read-only Telegram health response confirming that the visitor-triggered
  sender is OFF and the deliberate confirmed-release mode is ON.

The existing live workflow waits at most five minutes for that exact deployment.
It does not certify the old site against a newer commit merely because installer
versions happen to match. Configuration drift, missing credentials, unknown old
health schema, pending/failed/preview deployment or an advanced main blocks checks.
Health is rechecked after waiting. This is a bounded read-only wait, not publication.

The confirmation workflow performs this gate after Windows-receipt validation and
before canonical download verification or use of the confirmation key. Preview
health reports both release engines as disabled and exposes no bot credentials.

## Credential boundary and accepted operation

No token/environment protection/activation variable is created by these scripts.
The default command without `--check` is OFFLINE validation only, never remote PASS.
The required protected environment secrets are `CLOUDFLARE_ACCOUNT_ID` and a dedicated
`OUTPOST_PAGES_DEPLOY_TOKEN`; never reuse an owner's broad interactive OAuth session
in public CI. Keep the bot/webhook/setup secrets only in Cloudflare.

Cloudflare's documented minimum upload permission is account-level Pages Edit.
It is not claimed to be a provider-enforced per-project token. This helper can only
read the allowlisted Pages project, but local allowlisting cannot narrow the token's
inherent rights. Scope to the selected account with no D1/DNS/Workers mutation
permissions, protected main/production and expiry; obtaining and storing that
credential needs a separate explicit owner decision. A narrower broker would be a
separate reviewed architecture, not an implied new service.

The active writer is described in [PRODUCTION-PUBLISHER.md](PRODUCTION-PUBLISHER.md).
Separately accepted stages applied the compatible configuration, scoped keys and
five-minute pump. These scripts do not themselves create keys, activate a schedule,
resolve unknown delivery, change quota or announce current baseline versions.
Protected publication/live acceptance has real evidence; a genuine next-release
delivery for each desktop product remains separately pending. The source-declared
mode suppresses the legacy sender only when actual runtime health confirms it.
Merging code or adding health fields alone cannot establish any of these facts.

An encrypted secret's value cannot be compared through Pages metadata. The proof
checks names/types and safe mode, not cryptographic equality of hidden values.
Production provenance is trusted provider metadata plus controlled reviewed source,
not an independent signed attestation of the compiled Worker bytes. No new Windows
acceptance or mathematical exactly-once Telegram delivery is claimed.

Sources: [Cloudflare CI upload permissions](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/),
[Pages configuration source of truth](https://developers.cloudflare.com/pages/functions/wrangler-configuration/),
[GitHub environment protections](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments),
[public environment read API](https://docs.github.com/en/rest/deployments/environments).
