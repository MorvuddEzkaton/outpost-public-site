#!/usr/bin/env python3
"""Read-only production verifier for the public phone CTA dialog.

Only public outpost.com.ua HTML/JS/CSS is fetched. The verifier never follows a tel:
link and never calls Cabinet, Director, Sync, D1 or fiscal services.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import os
import sys
import time

from verify_phone_ctas import SCRIPT_INCLUDE_RE, TelAnchorParser, is_call_cta

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ORIGIN = "https://outpost.com.ua"
ALLOWED_HOST = "outpost.com.ua"

SCRIPT_MARKERS = (
    "isPhoneDialogTrigger",
    "event.preventDefault()",
    "showPhoneDialog()",
    "data-phone-dial",
    "+380 99 321 08 72",
    "tel:+380993210872",
    "/assets/phone-dialog.css?v=20260908",
)
CSS_MARKERS = (
    ".phone-dialog",
    ".phone-dialog::backdrop",
    ".phone-dialog-number",
    ".phone-dialog-close",
)


def local_cta_pages() -> list[str]:
    pages: list[str] = []
    for path in sorted(SITE.glob("*.html")):
        content = path.read_text(encoding="utf-8")
        parser = TelAnchorParser()
        parser.feed(content)
        if not any(is_call_cta(anchor) for anchor in parser.anchors):
            continue
        pages.append("/" if path.name == "index.html" else f"/{path.stem}")
    return pages


def fetch_public(path: str, nonce: str) -> str:
    separator = "&" if "?" in path else "?"
    url = f"{ORIGIN}{path}{separator}verify_phone={nonce}"
    request = Request(
        url,
        headers={
            "User-Agent": "OutPOSt-live-phone-verifier/1.0",
            "Accept": "text/html,application/javascript,text/css,*/*;q=0.1",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(request, timeout=15) as response:
        final_url = response.geturl()
        final_host = (urlparse(final_url).hostname or "").lower()
        if final_host != ALLOWED_HOST:
            raise RuntimeError(f"unexpected redirect outside public site: {final_url}")
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        return response.read().decode("utf-8")


def verify_once(nonce: str) -> list[str]:
    errors: list[str] = []
    pages = local_cta_pages()
    if not pages:
        return ["no local phone CTA pages found; verifier scope drifted"]

    for path in pages:
        try:
            html = fetch_public(path, nonce)
        except Exception as exc:  # network/read failure is a verification failure
            errors.append(f"{path}: {exc}")
            continue

        parser = TelAnchorParser()
        parser.feed(html)
        live_ctas = [anchor for anchor in parser.anchors if is_call_cta(anchor)]
        if not live_ctas:
            errors.append(f"{path}: live page has no phone CTA matching the source classifier")
        if not SCRIPT_INCLUDE_RE.search(html):
            errors.append(f"{path}: live phone CTA page does not include shared script.js")

    try:
        script = fetch_public("/script.js", nonce)
        for marker in SCRIPT_MARKERS:
            if marker not in script:
                errors.append(f"/script.js: missing phone-dialog marker {marker!r}")
    except Exception as exc:
        errors.append(f"/script.js: {exc}")

    try:
        css = fetch_public("/assets/phone-dialog.css?v=20260908", nonce)
        for marker in CSS_MARKERS:
            if marker not in css:
                errors.append(f"/assets/phone-dialog.css: missing selector {marker!r}")
    except Exception as exc:
        errors.append(f"/assets/phone-dialog.css: {exc}")

    return errors


def main() -> int:
    attempts = max(1, int(os.getenv("OUTPOST_LIVE_PHONE_ATTEMPTS", "6")))
    delay = max(0, int(os.getenv("OUTPOST_LIVE_PHONE_DELAY_SECONDS", "5")))
    pages = local_cta_pages()

    last_errors: list[str] = []
    for attempt in range(1, attempts + 1):
        nonce = f"{int(time.time())}-{attempt}"
        last_errors = verify_once(nonce)
        if not last_errors:
            print("Live phone CTA dialog: PASS")
            print(f"  public CTA pages verified: {len(pages)}")
            for path in pages:
                print(f"    - {path}")
            print("  live script.js + phone-dialog.css markers verified with cache busting")
            print("  tel: was never opened; protected services were not called")
            return 0
        if attempt < attempts:
            time.sleep(delay)

    print(f"Live phone CTA dialog: FAIL ({len(last_errors)} issue(s))", file=sys.stderr)
    for error in last_errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
