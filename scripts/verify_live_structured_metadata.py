#!/usr/bin/env python3
"""Verify deployed OutPOSt JSON-LD matches protected source commercial metadata.

Read-only. Fetches only public sitemap HTML pages from https://outpost.com.ua and
never calls Cabinet, protected APIs, downloads, Director, Sync, D1 or fiscal services.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import json
import os
import sys
import time

from verify_public_license_terms import (
    JsonLdCollector,
    html_path,
    sitemap_urls,
    validate_structured_commercial_facts,
)


USER_AGENT = "OutPOSt-live-structured-metadata-verifier/1.0"
ATTEMPTS = max(1, int(os.environ.get("OUTPOST_LIVE_STRUCTURED_ATTEMPTS", "4")))
DELAY_SECONDS = max(0.0, float(os.environ.get("OUTPOST_LIVE_STRUCTURED_DELAY_SECONDS", "5")))
WORKERS = max(1, min(12, int(os.environ.get("OUTPOST_LIVE_STRUCTURED_WORKERS", "8"))))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(NoRedirect)


def parse_blocks(url: str, text: str, side: str) -> list[object]:
    parser = JsonLdCollector()
    parser.feed(text)
    result: list[object] = []
    for index, raw in enumerate(parser.blocks, start=1):
        if not raw:
            raise RuntimeError(f"{url}: {side} JSON-LD block #{index} is empty")
        try:
            result.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"{url}: {side} JSON-LD block #{index} is invalid JSON: {exc}"
            ) from exc
    return result


def fetch_direct(url: str) -> tuple[int, dict[str, str], str]:
    req = Request(
        url,
        method="GET",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,*/*;q=0.1",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with OPENER.open(req, timeout=15) as response:
            status = response.status
            headers = {k.lower(): v for k, v in response.headers.items()}
            body = response.read()
    except HTTPError as exc:
        status = exc.code
        headers = {k.lower(): v for k, v in exc.headers.items()}
        body = exc.read()

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{url}: live HTML is not UTF-8: {exc}") from exc
    return status, headers, text


def check_page(url: str) -> tuple[int, int, int]:
    source_path = html_path(url)
    if not source_path.is_file():
        raise RuntimeError(f"{url}: source HTML is missing: {source_path}")
    source_text = source_path.read_text(encoding="utf-8")
    source_blocks = parse_blocks(url, source_text, "source")

    status, headers, live_text = fetch_direct(url)
    if status != 200:
        raise RuntimeError(f"{url}: expected direct HTTP 200, got {status}")
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "text/html":
        raise RuntimeError(
            f"{url}: expected text/html, got {headers.get('content-type', '')!r}"
        )

    live_blocks = parse_blocks(url, live_text, "live")
    if live_blocks != source_blocks:
        if len(live_blocks) != len(source_blocks):
            raise RuntimeError(
                f"{url}: JSON-LD block count differs; source={len(source_blocks)} live={len(live_blocks)}"
            )
        for index, (source, live) in enumerate(zip(source_blocks, live_blocks), start=1):
            if source != live:
                raise RuntimeError(
                    f"{url}: live JSON-LD block #{index} differs semantically from protected source"
                )
        raise RuntimeError(f"{url}: live JSON-LD differs from protected source")

    validation_errors: list[str] = []
    blocks, offers, contacts = validate_structured_commercial_facts(
        url, live_text, validation_errors
    )
    if validation_errors:
        raise RuntimeError("; ".join(validation_errors))
    if blocks != len(live_blocks):
        raise RuntimeError(
            f"{url}: validator parsed {blocks} blocks but collector found {len(live_blocks)}"
        )
    return blocks, offers, contacts


def run_once() -> tuple[int, int, int, int]:
    urls = sitemap_urls()
    if not urls:
        raise RuntimeError("site/sitemap.xml contains no public URLs")

    errors: list[str] = []
    block_total = 0
    offer_total = 0
    contact_total = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(check_page, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                blocks, offers, contacts = future.result()
                block_total += blocks
                offer_total += offers
                contact_total += contacts
            except Exception as exc:
                errors.append(f"{url}: {exc}")

    if errors:
        raise RuntimeError("; ".join(sorted(errors)))
    return len(urls), block_total, offer_total, contact_total


def main() -> int:
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            pages, blocks, offers, contacts = run_once()
            print("OutPOSt live structured metadata: PASS")
            print(f"  source/live JSON-LD parity: {pages}/{pages} sitemap pages")
            print(f"  valid JSON-LD blocks checked: {blocks}")
            print(f"  structured Offer facts checked: {offers}")
            print(f"  structured email/telephone facts checked: {contacts}")
            print("  protected/backend/download routes were not called")
            return 0
        except Exception as exc:
            last_error = exc
            if attempt < ATTEMPTS:
                print(f"Attempt {attempt}/{ATTEMPTS} failed: {exc}", file=sys.stderr)
                time.sleep(DELAY_SECONDS)

    print(f"OutPOSt live structured metadata: FAIL: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
