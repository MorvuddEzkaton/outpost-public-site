// Public verification digests of two independently random 256-bit capabilities.
// No secret, recipient ID, bot credential or subscriber permission is stored here.
// This short-lived authority can reach only the fixed administrator pilot route.
export const PILOT_CREDENTIAL_VERIFIERS = Object.freeze({
  "schema": 1,
  "expires_at": "2026-10-16T16:03:12.420708+00:00",
  "confirm_sha256": "cca5ed007d4fddf7e52a3234d2a2ae90278a1e97c8208b302d99130d65d6d850",
  "pump_sha256": "1b9d2951fdd7c1dfac49b901879e501cfceb62007ff28499e39c4681ad096c7d"
});

export async function pilotCredentialRole(supplied, verifiers = PILOT_CREDENTIAL_VERIFIERS, now = Date.now()) {
  if (typeof supplied !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(supplied) ||
      verifiers?.schema !== 1 || !Number.isFinite(now) || !Number.isFinite(Date.parse(verifiers.expires_at)) ||
      Date.parse(verifiers.expires_at) <= now ||
      !/^[a-f0-9]{64}$/.test(verifiers.confirm_sha256) || !/^[a-f0-9]{64}$/.test(verifiers.pump_sha256) ||
      verifiers.confirm_sha256 === verifiers.pump_sha256) return null;
  const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(supplied)))]
    .map(byte => byte.toString(16).padStart(2,"0")).join("");
  const equal = expected => { let diff = 0; for (let i=0;i<64;i++) diff |= digest.charCodeAt(i)^expected.charCodeAt(i); return diff === 0; };
  if (equal(verifiers.confirm_sha256)) return "confirm";
  if (equal(verifiers.pump_sha256)) return "pump";
  return null;
}
