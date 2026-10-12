#!/usr/bin/env python3
"""Verify deployed OutPOSt browser/site identity matches protected source.

Read-only. Fetches only canonical public sitemap HTML and the four root icon
assets from https://outpost.com.ua. Protected/backend/download routes are never called.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import hashlib
import os
import sys
import time

from verify_site_identity import (
    ROOT,
    SITE,
    PNG_DIMENSIONS,
    ROOT_ICON_PATHS,
    collect_icons,
    png_dimensions,
    sitemap_urls,
    html_path,
    REQUIRED_ICON_LINKS,
)


ORIGIN = "https://outpost.com.ua"
USER_AGENT = "OutPOSt-live-site-identity-verifier/1.0"
ATTEMPTS = max(1, int(os.environ.get("OUTPOST_LIVE_IDENTITY_ATTEMPTS", "4")))
DELAY_SECONDS = max(0.0, float(os.environ.get("OUTPOST_LIVE_IDENTITY_DELAY_SECONDS", "5")))
WORKERS = max(1, min(12, int(os.environ.get("OUTPOST_LIVE_IDENTITY_WORKERS", "8"))))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(NoRedirect)


def fetch_direct(url: str, accept: str) -> tuple[int, dict[str, str], bytes]:
    req = Request(
        url,
        method="GET",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Cache-Control": "no-cache",
        },
    )
    try:
        with OPENER.open(req, timeout=15) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()


def check_page(url: str) -> None:
    source = html_path(url)
    if not source.is_file():
        raise RuntimeError(f"source HTML missing: {source.relative_to(ROOT)}")
    source_icons = collect_icons(source.read_text(encoding="utf-8"))
    if not REQUIRED_ICON_LINKS.issubset(source_icons):
        raise RuntimeError("protected source is missing required modern icon links")

    status, headers, body = fetch_direct(url, "text/html,*/*;q=0.1")
    if status != 200:
        raise RuntimeError(f"expected direct HTTP 200, got {status}")
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "text/html":
        raise RuntimeError(f"expected text/html, got {headers.get('content-type', '')!r}")
    try:
        live_icons = collect_icons(body.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"live HTML is not UTF-8: {exc}") from exc

    if live_icons != source_icons:
        raise RuntimeError(
            f"live icon-link set differs from source; source={sorted(source_icons)!r} live={sorted(live_icons)!r}"
        )
    if not REQUIRED_ICON_LINKS.issubset(live_icons):
        raise RuntimeError("live page is missing required modern icon links")


def validate_ico(data: bytes) -> bool:
    if len(data) < 6 or data[:4] != b"\x00\x00\x01\x00":
        return False
    count = int.from_bytes(data[4:6], "little")
    return count >= 1 and len(data) >= 6 + 16 * count


def check_asset(href: str) -> tuple[str, str]:
    source = SITE / href.lstrip("/")
    if not source.is_file():
        raise RuntimeError(f"source icon missing: {source.relative_to(ROOT)}")
    source_bytes = source.read_bytes()

    status, headers, live_bytes = fetch_direct(ORIGIN + href, "image/*,*/*;q=0.1")
    if status != 200:
        raise RuntimeError(f"{href}: expected direct HTTP 200, got {status}")
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not content_type.startswith("image/"):
        raise RuntimeError(f"{href}: expected image/*, got {headers.get('content-type', '')!r}")
    if live_bytes != source_bytes:
        raise RuntimeError(
            f"{href}: live bytes differ from source; source_sha256={hashlib.sha256(source_bytes).hexdigest()} "
            f"live_sha256={hashlib.sha256(live_bytes).hexdigest()}"
        )

    if href in PNG_DIMENSIONS:
        actual = png_dimensions(live_bytes)
        if actual != PNG_DIMENSIONS[href]:
            raise RuntimeError(f"{href}: live PNG dimensions {actual!r} != {PNG_DIMENSIONS[href]!r}")
    elif href == "/favicon.ico" and not validate_ico(live_bytes):
        raise RuntimeError(f"{href}: live ICO header/directory is invalid")

    return href, hashlib.sha256(live_bytes).hexdigest()


def run_once() -> tuple[int, int]:
    urls = sitemap_urls()
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(check_page, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                future.result()
            except Exception as exc:
                errors.append(f"{url}: {exc}")

    asset_errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(WORKERS, len(ROOT_ICON_PATHS))) as pool:
        futures = {pool.submit(check_asset, href): href for href in ROOT_ICON_PATHS}
        for future in as_completed(futures):
            href = futures[future]
            try:
                future.result()
            except Exception as exc:
                asset_errors.append(str(exc))

    if errors or asset_errors:
        raise RuntimeError("; ".join(sorted(errors + asset_errors)))
    return len(urls), len(ROOT_ICON_PATHS)


def main() -> int:
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            pages, assets = run_once()
            print("OutPOSt live site identity: PASS")
            print(f"  source/live icon-link parity: {pages}/{pages} sitemap pages")
            print(f"  source/live icon byte parity: {assets}/{assets} root icon assets")
            print("  PNG dimensions and favicon.ico structure valid")
            print("  protected/backend/download routes were not called")
            return 0
        except Exception as exc:
            last_error = exc
            if attempt < ATTEMPTS:
                print(f"Attempt {attempt}/{ATTEMPTS} failed: {exc}", file=sys.stderr)
                time.sleep(DELAY_SECONDS)

    print(f"OutPOSt live site identity: FAIL: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
