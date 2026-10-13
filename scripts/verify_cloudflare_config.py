#!/usr/bin/env python3
"""Read-only guard for the public OutPOSt Cloudflare Pages configuration."""

from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "wrangler.jsonc"
LEGACY_CONFIG_HASH = "a3d4877bd8247b79f20c1e90cfce6577d28a62cd276870acd6942df782ecc49d"
APPROVED_CONFIG_HASH = "1250f89a51fd987f0829d2e9772afd658943d956666259661ceaecfe212bfcf6"
# A production-only upload must not require or silently change preview settings.
EXPECTED_PREVIEW_CONFIG_HASH = LEGACY_CONFIG_HASH
EXPECTED_PRODUCTION_VARS = {"TELEGRAM_CONFIRMED_RELEASES_ENABLED": "1"}

EXPECTED = {
    "name": "outpost-web",
    "pages_build_output_dir": "./site",
    "compatibility_date": "2026-08-22",
}

EXPECTED_PRODUCTION_D1 = {
    "ANALYTICS_DB": ("outpost-download-analytics", "0ebb8c01-8411-464c-9ab9-bd6945c9148b"),
    "CMS_DB": ("outpost-cms-production", "59db204d-7252-4b84-ba29-3bb8c8438129"),
}

EXPECTED_PREVIEW_D1 = {
    "ANALYTICS_DB": ("outpost-download-analytics-staging", "1db69075-97d9-43fd-92df-12f7a330ed21"),
    "CMS_DB": ("outpost-cms-staging", "48e1bd8c-16f9-4631-a4e2-7ed62fca00d0"),
}


def as_binding_map(items: list[dict]) -> dict[str, tuple[str, str]]:
    return {
        item.get("binding", ""): (item.get("database_name", ""), item.get("database_id", ""))
        for item in items
    }


def configuration_errors(data) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["configuration must be an object"]
    if set(data) != {"$schema", "name", "pages_build_output_dir", "compatibility_date", "vars", "d1_databases", "env"}:
        errors.append("unexpected configuration fields")
    environments = data.get("env", {})
    preview_candidate = environments.get("preview", {}) if isinstance(environments, dict) else {}
    preview_config = preview_candidate if isinstance(preview_candidate, dict) else {}
    if not isinstance(environments, dict) or set(environments) != {"preview"} or not isinstance(preview_candidate, dict) or set(preview_config) != {"vars", "d1_databases"}:
        errors.append("only the explicit preview configuration is allowed")
    if data.get("vars") != EXPECTED_PRODUCTION_VARS:
        errors.append("production must declare exactly the nonsecret confirmed-mode flag as string 1")
    if preview_config.get("vars") != {}:
        errors.append("preview must explicitly override vars with an empty object")
    for key, expected in EXPECTED.items():
        if data.get(key) != expected:
            errors.append(f"{key} does not match the reviewed contract")
    try:
        if as_binding_map(data.get("d1_databases", [])) != EXPECTED_PRODUCTION_D1:
            errors.append("production D1 bindings changed")
        if as_binding_map(preview_config.get("d1_databases", [])) != EXPECTED_PREVIEW_D1:
            errors.append("preview D1 bindings changed")
    except (TypeError, AttributeError):
        errors.append("invalid D1 binding structure")
    return errors


def main() -> int:

    if not CONFIG.is_file():
        print("Cloudflare config guard: FAIL\n  - wrangler.jsonc is missing")
        return 1

    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Cloudflare config guard: FAIL\n  - wrangler.jsonc is not parseable JSON: {exc}")
        return 1

    errors = configuration_errors(data)
    import hashlib
    if hashlib.sha256(CONFIG.read_bytes()).hexdigest() != APPROVED_CONFIG_HASH:
        errors.append("configuration bytes do not match the reviewed exact pin")

    if errors:
        print(f"Cloudflare config guard: FAIL ({len(errors)} issue(s))")
        for error in errors:
            print(f"  - {error}")
        print("If a binding change is intentional, review it as a dedicated Cloudflare task and update this guard in the same PR.")
        return 1

    print("Cloudflare config guard: PASS")
    print("  Exact reviewed configuration: production mode flag, isolated preview vars, unchanged runtime and D1 bindings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
