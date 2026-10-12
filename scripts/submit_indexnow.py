#!/usr/bin/env python3
"""Submit changed public OutPOSt URLs to IndexNow after a verified production deploy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
ORIGIN = "https://outpost.com.ua"
HOST = "outpost.com.ua"
KEY = "0e9134a8bef16d4343aa1a75d8be5ecd"
KEY_RELATIVE_PATH = f"site/{KEY}.txt"
KEY_URL = f"{ORIGIN}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
USER_AGENT = "OutPOSt-IndexNow/1.0"


class IndexNowError(RuntimeError):
    pass


def source_path_for_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != HOST:
        raise IndexNowError(f"sitemap URL is outside canonical origin: {url}")
    if parsed.query or parsed.fragment:
        raise IndexNowError(f"sitemap URL must not contain query/fragment: {url}")
    path = parsed.path
    if path == "/":
        return "site/index.html"
    if not path.startswith("/") or path.endswith("/"):
        raise IndexNowError(f"unsupported canonical public path: {path}")
    return f"site{path}.html"


def parse_sitemap(text: str) -> dict[str, str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise IndexNowError(f"cannot parse sitemap: {exc}") from exc

    mapping: dict[str, str] = {}
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "loc" or not node.text:
            continue
        url = node.text.strip()
        source = source_path_for_url(url)
        if source in mapping and mapping[source] != url:
            raise IndexNowError(f"duplicate sitemap source mapping for {source}")
        mapping[source] = url
    if not mapping:
        raise IndexNowError("sitemap contains no public URLs")
    return mapping


def git_text(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def git_changed_paths(base: str, head: str) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base, head, "--", "site"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def select_urls(
    changed_paths: set[str],
    current_map: dict[str, str],
    base_map: dict[str, str],
) -> list[str]:
    # First deployment of the ownership key seeds all current public URLs once.
    if KEY_RELATIVE_PATH in changed_paths:
        return sorted(current_map.values())

    source_to_url = dict(base_map)
    source_to_url.update(current_map)
    urls = {source_to_url[path] for path in changed_paths if path in source_to_url}
    return sorted(urls)


def changed_public_urls(base: str, head: str) -> list[str]:
    current_text = (SITE / "sitemap.xml").read_text(encoding="utf-8")
    current_map = parse_sitemap(current_text)
    base_text = git_text(base, "site/sitemap.xml")
    base_map = parse_sitemap(base_text) if base_text.strip() else {}
    return select_urls(git_changed_paths(base, head), current_map, base_map)


def build_payload(urls: list[str]) -> bytes:
    if not urls:
        raise IndexNowError("cannot build IndexNow payload with no URLs")
    if len(urls) > 10_000:
        raise IndexNowError("IndexNow payload exceeds 10,000 URLs")
    body = {
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_URL,
        "urlList": urls,
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def verify_live_key() -> None:
    request = urllib.request.Request(
        KEY_URL,
        headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = int(getattr(response, "status", response.getcode()))
            body = response.read(1024).decode("utf-8", "replace").strip()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise IndexNowError(f"cannot verify live key file: {type(exc).__name__}: {exc}") from exc
    if status != 200:
        raise IndexNowError(f"live key file returned HTTP {status}")
    if body != KEY:
        raise IndexNowError("live IndexNow key file content does not match repository key")


def submit(urls: list[str]) -> int:
    request = urllib.request.Request(
        ENDPOINT,
        data=build_payload(urls),
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json,text/plain,*/*",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return int(getattr(response, "status", response.getcode()))
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", "replace").strip()
        raise IndexNowError(f"IndexNow returned HTTP {exc.code}: {detail or '-'}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise IndexNowError(f"IndexNow request failed: {type(exc).__name__}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="HEAD^")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--all", action="store_true", help="submit all current sitemap URLs")
    args = parser.parse_args()

    try:
        key_file = SITE / f"{KEY}.txt"
        if not key_file.is_file() or key_file.read_text(encoding="utf-8").strip() != KEY:
            raise IndexNowError("repository IndexNow key file is missing or invalid")

        current_map = parse_sitemap((SITE / "sitemap.xml").read_text(encoding="utf-8"))
        urls = sorted(current_map.values()) if args.all else changed_public_urls(args.base, args.head)
        if not urls:
            print("OutPOSt IndexNow: SKIP — no changed public sitemap URLs")
            return 0

        verify_live_key()
        status = submit(urls)
        if status not in (200, 202):
            raise IndexNowError(f"unexpected successful-response status: HTTP {status}")

        print(f"OutPOSt IndexNow: ACCEPTED HTTP {status}")
        print(f"  submitted public URLs: {len(urls)}")
        for url in urls:
            print(f"  - {url}")
        print("  HTTP acceptance confirms receipt, not crawl or indexing")
        return 0
    except (IndexNowError, subprocess.SubprocessError, OSError) as exc:
        print(f"OutPOSt IndexNow: FAIL\n  - {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
