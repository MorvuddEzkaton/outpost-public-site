# Protected production provenance — preparation, not activation

The Pages publication path must preserve the reviewed original `wrangler.jsonc`.
Publishing without that file can clear its configuration marker even when D1
bindings and runtime settings survive. Never substitute an isolated-preview file,
reconstruct encrypted values or accept unexplained configuration drift.

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

## Credentials and remaining work

No token/environment protection/activation variable is created by these scripts.
The default command without `--check` is OFFLINE validation only, never remote PASS.
The required future environment secrets are `CLOUDFLARE_ACCOUNT_ID` and a dedicated
`OUTPOST_PAGES_DEPLOY_TOKEN`; never reuse an owner's broad interactive OAuth session
in public CI. Keep the bot/webhook/setup secrets only in Cloudflare.

Cloudflare's documented minimum upload permission is account-level Pages Edit.
It is not claimed to be a provider-enforced per-project token. This helper can only
read the allowlisted Pages project, but local allowlisting cannot narrow the token's
inherent rights. Scope to the selected account with no D1/DNS/Workers mutation
permissions, protected main/production and expiry; obtaining and storing that
credential needs a separate explicit owner decision. A narrower broker would be a
separate reviewed architecture, not an implied new service.

The dormant writer is now prepared separately in [PRODUCTION-PUBLISHER.md](PRODUCTION-PUBLISHER.md).
Neither package activates it, creates confirmed-release keys, enables the scheduled
pump, resolves unknown delivery states, changes quota or announces current versions.
The existing live/confirmation diagnostics fail closed until prerequisites are ready.
Actual protected deployment->live->release end-to-end acceptance remains separate.
Ordinary legacy behavior remains unchanged
until deliberate activation; adding health fields does not switch either engine.

An encrypted secret's value cannot be compared through Pages metadata. The proof
checks names/types and safe mode, not cryptographic equality of hidden values.
Production provenance is trusted provider metadata plus controlled reviewed source,
not an independent signed attestation of the compiled Worker bytes. No new Windows
acceptance or mathematical exactly-once Telegram delivery is claimed.

Sources: [Cloudflare CI upload permissions](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/),
[Pages configuration source of truth](https://developers.cloudflare.com/pages/functions/wrangler-configuration/),
[GitHub environment protections](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments),
[public environment read API](https://docs.github.com/en/rest/deployments/environments).
