#!/usr/bin/env python3
"""Verify deployed OutPOSt social metadata matches the protected source contract.

Read-only. The verifier fetches only public sitemap HTML pages and their public
Open Graph images from https://outpost.com.ua. It never calls Cabinet, protected
APIs, downloads, Director, Sync, D1 or fiscal services.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import os
import sys
import time
import xml.etree.ElementTree as ET

from verify_public_site import (
    LinkCollector,
    PUBLIC_ORIGIN,
    REQUIRED_SOCIAL_META,
    normalize_internal_path,
    resolve_target_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "site"
USER_AGENT = "OutPOSt-live-social-metadata-verifier/1.0"
ATTEMPTS = max(1, int(os.environ.get("OUTPOST_LIVE_SOCIAL_ATTEMPTS", "4")))
DELAY_SECONDS = max(0.0, float(os.environ.get("OUTPOST_LIVE_SOCIAL_DELAY_SECONDS", "5")))
WORKERS = max(1, min(12, int(os.environ.get("OUTPOST_LIVE_SOCIAL_WORKERS", "8"))))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(NoRedirect)


def fail(message: str) -> None:
    raise RuntimeError(message)


def read_sitemap_urls() -> list[str]:
    root = ET.fromstring((SITE / "sitemap.xml").read_text(encoding="utf-8"))
    urls = [
        elem.text.strip()
        for elem in root.iter()
        if elem.tag.endswith("loc") and elem.text and elem.text.strip()
    ]
    if not urls:
        fail("site/sitemap.xml contains no URLs")
    if len(urls) != len(set(urls)):
        fail("site/sitemap.xml contains duplicate URLs")
    return urls


def source_metadata(url: str) -> dict[str, str]:
    resolved = normalize_internal_path(url)
    if resolved is None:
        fail(f"cannot resolve source target for {url}")
    target = resolve_target_file(resolved)
    if target is None:
        fail(f"source target missing for {url}: {resolved}")

    parser = LinkCollector()
    parser.feed(target.read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    for key in REQUIRED_SOCIAL_META:
        values = parser.meta.get(key, [])
        if len(values) != 1 or not values[0]:
            fail(f"source metadata contract is invalid for {url}: {key}={values!r}")
        result[key] = values[0]
    return result


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


def parse_live_metadata(url: str, body: bytes) -> dict[str, str]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{url}: live HTML is not UTF-8: {exc}")

    parser = LinkCollector()
    parser.feed(text)
    result: dict[str, str] = {}
    for key in REQUIRED_SOCIAL_META:
        values = parser.meta.get(key, [])
        if len(values) != 1 or not values[0]:
            fail(f"{url}: live {key} must exist exactly once and be non-empty; got {values!r}")
        result[key] = values[0]
    return result


def check_page(url: str) -> tuple[str, str, tuple[int, int]]:
    expected = source_metadata(url)
    status, headers, body = fetch_direct(url, "text/html,*/*;q=0.1")
    if status != 200:
        fail(f"{url}: expected direct HTTP 200, got {status}")
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "text/html":
        fail(f"{url}: expected text/html, got {headers.get('content-type', '')!r}")

    actual = parse_live_metadata(url, body)
    for key in REQUIRED_SOCIAL_META:
        if actual[key] != expected[key]:
            fail(
                f"{url}: live {key} differs from protected source; "
                f"source={expected[key]!r} live={actual[key]!r}"
            )

    if actual["og:url"] != url:
        fail(f"{url}: live og:url must equal sitemap canonical exactly; got {actual['og:url']!r}")
    if actual["twitter:card"] != "summary_large_image":
        fail(f"{url}: live twitter:card must be summary_large_image; got {actual['twitter:card']!r}")

    image = actual["og:image"]
    parsed = urlparse(image)
    if parsed.scheme != "https" or parsed.netloc != "outpost.com.ua" or not parsed.path.startswith("/"):
        fail(f"{url}: live og:image is not canonical public HTTPS: {image!r}")

    try:
        dimensions = (int(actual["og:image:width"]), int(actual["og:image:height"]))
    except ValueError:
        fail(
            f"{url}: live og:image dimensions must be integers; "
            f"got {actual['og:image:width']!r}x{actual['og:image:height']!r}"
        )
    if dimensions[0] <= 0 or dimensions[1] <= 0:
        fail(f"{url}: live og:image dimensions must be positive; got {dimensions!r}")
    return url, image, dimensions


def png_dimensions(body: bytes) -> tuple[int, int] | None:
    if len(body) < 24 or body[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return (
        int.from_bytes(body[16:20], "big"),
        int.from_bytes(body[20:24], "big"),
    )


def check_image(url: str, expected_dimensions: tuple[int, int]) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "outpost.com.ua":
        fail(f"refusing non-public og:image URL: {url}")
    if parsed.path.startswith(("/downloads/", "/admin", "/api/", "/functions/", "/cdn-cgi/")):
        fail(f"refusing protected/download og:image URL: {url}")

    status, headers, body = fetch_direct(url, "image/*,*/*;q=0.1")
    if status != 200:
        fail(f"{url}: og:image expected direct HTTP 200, got {status}")
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not content_type.startswith("image/"):
        fail(f"{url}: og:image expected image/* Content-Type, got {headers.get('content-type', '')!r}")
    if parsed.path.lower().endswith(".png") and content_type != "image/png":
        fail(
            f"{url}: .png og:image must be served as image/png, "
            f"got {headers.get('content-type', '')!r}"
        )
    if not body:
        fail(f"{url}: og:image returned an empty body")
    if parsed.path.lower().endswith(".png"):
        actual_dimensions = png_dimensions(body)
        if actual_dimensions is None:
            fail(f"{url}: .png og:image has invalid PNG signature/IHDR")
        if actual_dimensions != expected_dimensions:
            fail(
                f"{url}: og:image dimensions mismatch; "
                f"declared={expected_dimensions[0]}x{expected_dimensions[1]} "
                f"actual={actual_dimensions[0]}x{actual_dimensions[1]}"
            )
    return url


def run_once() -> tuple[int, int]:
    urls = read_sitemap_urls()
    images: dict[str, tuple[int, int]] = {}
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(check_page, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                _, image, dimensions = future.result()
                previous = images.get(image)
                if previous is not None and previous != dimensions:
                    raise RuntimeError(
                        f"{image}: sitemap pages disagree on og:image dimensions; "
                        f"{previous!r} vs {dimensions!r}"
                    )
                images[image] = dimensions
            except Exception as exc:
                errors.append(f"{url}: {exc}")

    if errors:
        raise RuntimeError("; ".join(sorted(errors)))

    image_errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(WORKERS, max(1, len(images)))) as pool:
        futures = {
            pool.submit(check_image, image, dimensions): image
            for image, dimensions in sorted(images.items())
        }
        for future in as_completed(futures):
            image = futures[future]
            try:
                future.result()
            except Exception as exc:
                image_errors.append(f"{image}: {exc}")

    if image_errors:
        raise RuntimeError("; ".join(sorted(image_errors)))
    return len(urls), len(images)


def main() -> int:
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            page_count, image_count = run_once()
            print("OutPOSt live social metadata: PASS")
            print(f"  source/live metadata parity: {page_count}/{page_count} sitemap pages")
            print(f"  reachable Open Graph images with matching live dimensions: {image_count}/{image_count}")
            print("  protected/backend/download routes were not called")
            return 0
        except Exception as exc:
            last_error = exc
            if attempt < ATTEMPTS:
                print(f"Attempt {attempt}/{ATTEMPTS} failed: {exc}", file=sys.stderr)
                time.sleep(DELAY_SECONDS)

    print(f"OutPOSt live social metadata: FAIL: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
