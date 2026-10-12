#!/usr/bin/env python3
"""Read-only guard for the public OutPOSt Cloudflare Pages configuration."""

from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "wrangler.jsonc"

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


def main() -> int:
    errors: list[str] = []

    if not CONFIG.is_file():
        print("Cloudflare config guard: FAIL\n  - wrangler.jsonc is missing")
        return 1

    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Cloudflare config guard: FAIL\n  - wrangler.jsonc is not parseable JSON: {exc}")
        return 1

    for key, expected in EXPECTED.items():
        actual = data.get(key)
        if actual != expected:
            errors.append(f"{key}: expected {expected!r}, got {actual!r}")

    production = as_binding_map(data.get("d1_databases", []))
    if production != EXPECTED_PRODUCTION_D1:
        errors.append(f"production D1 bindings changed: {production!r}")

    preview = as_binding_map(data.get("env", {}).get("preview", {}).get("d1_databases", []))
    if preview != EXPECTED_PREVIEW_D1:
        errors.append(f"preview D1 bindings changed: {preview!r}")

    if errors:
        print(f"Cloudflare config guard: FAIL ({len(errors)} issue(s))")
        for error in errors:
            print(f"  - {error}")
        print("If a binding change is intentional, review it as a dedicated Cloudflare task and update this guard in the same PR.")
        return 1

    print("Cloudflare config guard: PASS")
    print("  Pages output and production/preview D1 bindings match the known-good baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
