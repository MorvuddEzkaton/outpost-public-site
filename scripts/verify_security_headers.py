#!/usr/bin/env python3
"""Guard the known-good public-site browser security boundary.

Standard-library only. This script reads site/_headers and fails closed when a
protected browser-security boundary is removed or broadened unintentionally. It
also checks that source HTML remains compatible with the strict self-only script
and style CSP instead of relying on browser-side blocking.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
HEADERS_FILE = SITE / "_headers"

EXPECTED_SCALAR_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}

EXPECTED_CSP = {
    "default-src": {"'self'"},
    "script-src": {"'self'"},
    "style-src": {"'self'"},
    "img-src": {"'self'", "data:"},
    "font-src": {"'self'"},
    "connect-src": {"'self'", "https://cabinet.outpost.com.ua"},
    "object-src": {"'none'"},
    "base-uri": {"'self'"},
    "form-action": {"'none'"},
    "frame-ancestors": {"'none'"},
    "upgrade-insecure-requests": set(),
}

EXPECTED_PERMISSIONS = {
    "camera": "()",
    "microphone": "()",
    "geolocation": "()",
    "payment": "()",
    "usb": "()",
}

FORBIDDEN_CSP_TOKENS = {
    "'unsafe-inline'",
    "'unsafe-eval'",
    "*",
    "http:",
}

NON_EXECUTABLE_INLINE_SCRIPT_TYPES = {
    "application/ld+json",
    "application/json",
}


def parse_headers(text: str) -> tuple[list[str], dict[str, str]]:
    routes: list[str] = []
    headers: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if raw and not raw[0].isspace():
            routes.append(line)
            continue
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip()] = value.strip()
    return routes, headers


def header_route_errors(routes: list[str]) -> list[str]:
    """Shared fail-closed source/live contract: global security plus exact demo cache routes."""
    # Global CSP applies to every route. Only these five narrow cache overrides
    # may follow it; extra wildcard/public routes would weaken the boundary.
    allowed_demo_cache_routes = {
        "/assets/outpost-demo-v1.css",
        "/assets/outpost-demo-v1.js",
        "/assets/outpost-demo-modules-v1.js",
        "/assets/outpost-demo-returns-v1.js",
        "/assets/outpost-demo-products-v1.js",
    }
    if not routes or routes[0] != "/*" or routes.count("/*") != 1 or (
        len(routes) != 1 + len(allowed_demo_cache_routes)
        or set(routes[1:]) != allowed_demo_cache_routes
    ):
        return [
            "site/_headers: expected one global /* CSP plus exactly five "
            f"narrow demo revalidation rules; got {routes!r}"
        ]
    return []


def parse_csp(value: str) -> dict[str, set[str]]:
    directives: dict[str, set[str]] = {}
    for chunk in value.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split()
        directives[parts[0]] = set(parts[1:])
    return directives


def parse_permissions(value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, setting = chunk.split("=", 1)
        out[name.strip()] = setting.strip()
    return out


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def guard_csp_compatible_html() -> list[str]:
    errors: list[str] = []
    style_tag_re = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL)
    style_attr_re = re.compile(r"\sstyle\s*=\s*([\"']).*?\1", re.IGNORECASE | re.DOTALL)
    script_re = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)

    for path in sorted(SITE.glob("*.html")):
        text = path.read_text(encoding="utf-8")

        for match in style_tag_re.finditer(text):
            errors.append(
                f"site/{path.name}:{line_of(text, match.start())}: inline <style> is blocked by style-src 'self'; use a local stylesheet"
            )

        for match in style_attr_re.finditer(text):
            errors.append(
                f"site/{path.name}:{line_of(text, match.start())}: style= attribute is blocked by style-src 'self'; use a CSS class"
            )

        for match in script_re.finditer(text):
            attrs = match.group(1)
            if re.search(r"\bsrc\s*=", attrs, flags=re.IGNORECASE):
                continue
            type_match = re.search(
                r"\btype\s*=\s*([\"'])(.*?)\1",
                attrs,
                flags=re.IGNORECASE | re.DOTALL,
            )
            script_type = type_match.group(2).strip().lower() if type_match else ""
            if script_type in NON_EXECUTABLE_INLINE_SCRIPT_TYPES:
                continue
            errors.append(
                f"site/{path.name}:{line_of(text, match.start())}: executable inline <script> is blocked by script-src 'self'; use a local script file"
            )

    return errors


def main() -> int:
    errors: list[str] = []

    if not HEADERS_FILE.is_file():
        print("OutPOSt security headers guard: FAIL")
        print("  - missing site/_headers")
        return 1

    routes, headers = parse_headers(HEADERS_FILE.read_text(encoding="utf-8"))
    errors.extend(header_route_errors(routes))

    for name, expected in EXPECTED_SCALAR_HEADERS.items():
        actual = headers.get(name)
        if actual != expected:
            errors.append(f"site/_headers: {name} expected {expected!r}, got {actual!r}")

    csp_value = headers.get("Content-Security-Policy")
    if not csp_value:
        errors.append("site/_headers: Content-Security-Policy is missing")
    else:
        csp = parse_csp(csp_value)
        for directive, expected_tokens in EXPECTED_CSP.items():
            actual_tokens = csp.get(directive)
            if actual_tokens is None:
                errors.append(f"site/_headers: CSP directive missing: {directive}")
            elif actual_tokens != expected_tokens:
                errors.append(
                    f"site/_headers: CSP {directive} expected {sorted(expected_tokens)!r}, got {sorted(actual_tokens)!r}"
                )

        flattened = {token for tokens in csp.values() for token in tokens}
        for token in sorted(FORBIDDEN_CSP_TOKENS):
            if token in flattened:
                errors.append(f"site/_headers: forbidden CSP token present: {token}")

        unexpected = sorted(set(csp) - set(EXPECTED_CSP))
        if unexpected:
            errors.append(f"site/_headers: unexpected CSP directives require review: {unexpected!r}")

    permissions_value = headers.get("Permissions-Policy")
    if not permissions_value:
        errors.append("site/_headers: Permissions-Policy is missing")
    else:
        permissions = parse_permissions(permissions_value)
        if permissions != EXPECTED_PERMISSIONS:
            errors.append(
                f"site/_headers: Permissions-Policy changed; expected {EXPECTED_PERMISSIONS!r}, got {permissions!r}"
            )

    errors.extend(guard_csp_compatible_html())

    unique_errors = list(dict.fromkeys(errors))
    if unique_errors:
        print(f"OutPOSt security headers guard: FAIL ({len(unique_errors)} issue(s))")
        for item in unique_errors:
            print(f"  - {item}")
        return 1

    print("OutPOSt security headers guard: PASS")
    print("  global header rule is /*")
    print("  CSP keeps scripts/styles self-only and connect-src limited to OutPOSt cabinet")
    print("  public HTML contains no blocked inline style or executable inline script")
    print("  framing, objects, forms and sensitive browser capabilities remain blocked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
