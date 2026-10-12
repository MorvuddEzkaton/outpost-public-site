#!/usr/bin/env python3
"""Verify that production robots.txt matches the repository SEO contract.

Read-only safety model:
- reads local site/robots.txt;
- performs GET requests only to https://outpost.com.ua/robots.txt;
- compares normalized non-comment directives exactly;
- additionally requires public crawling, /admin blocking, and the canonical sitemap;
- does not call Cabinet, Worker APIs, D1, Director, Sync, PRRO or fiscal services.
"""

from __future__ import annotations

from pathlib import Path
import os
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROBOTS = ROOT / "site" / "robots.txt"
LIVE_ROBOTS_URL = "https://outpost.com.ua/robots.txt"
CANONICAL_SITEMAP = "Sitemap: https://outpost.com.ua/sitemap.xml"
USER_AGENT = "OutPOSt-Live-Robots-Verifier/1.0"


class RobotsError(RuntimeError):
    pass


def normalized_directives(text: str) -> list[str]:
    directives: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        directives.append(line)
    if not directives:
        raise RobotsError("robots.txt contains no directives")
    return directives


def validate_contract(directives: list[str], label: str) -> None:
    required = {
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        CANONICAL_SITEMAP,
    }
    missing = sorted(required - set(directives))
    if missing:
        raise RobotsError(f"{label}: missing required directive(s): {', '.join(missing)}")

    sitemap_lines = [line for line in directives if line.lower().startswith("sitemap:")]
    if sitemap_lines != [CANONICAL_SITEMAP]:
        raise RobotsError(
            f"{label}: expected exactly one canonical sitemap directive; got {sitemap_lines!r}"
        )

    disallows = [line for line in directives if line.lower().startswith("disallow:")]
    if "Disallow: /" in disallows:
        raise RobotsError(f"{label}: public root must not be disallowed")


def fetch_live() -> str:
    request = urllib.request.Request(
        LIVE_ROBOTS_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/plain,*/*;q=0.1",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise RobotsError(f"production robots.txt returned HTTP {status}")
            data = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RobotsError(f"production robots.txt request failed: {exc}") from exc

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RobotsError("production robots.txt is not valid UTF-8") from exc


def int_env(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RobotsError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RobotsError(f"{name} must be >= {minimum}")
    return value


def main() -> int:
    try:
        if not LOCAL_ROBOTS.is_file():
            raise RobotsError("local site/robots.txt is missing")

        expected = normalized_directives(LOCAL_ROBOTS.read_text(encoding="utf-8"))
        validate_contract(expected, "repository robots.txt")

        attempts = int_env("OUTPOST_LIVE_ROBOTS_ATTEMPTS", 6, 1)
        delay_seconds = int_env("OUTPOST_LIVE_ROBOTS_DELAY_SECONDS", 5, 0)
        last_error = ""

        for attempt in range(1, attempts + 1):
            try:
                actual = normalized_directives(fetch_live())
                validate_contract(actual, "production robots.txt")
                if actual == expected:
                    print("OutPOSt live robots verifier: PASS")
                    print(f"  production URL: {LIVE_ROBOTS_URL}")
                    print(f"  matched directives: {len(expected)}")
                    print("  public crawl allowed, /admin blocked, canonical sitemap declared")
                    print("  protected application services were not called")
                    return 0
                last_error = f"directive mismatch: repository={expected!r} production={actual!r}"
            except RobotsError as exc:
                last_error = str(exc)

            print(
                f"OutPOSt live robots verifier: mismatch on attempt {attempt}/{attempts}: {last_error}"
            )
            if attempt < attempts and delay_seconds:
                time.sleep(delay_seconds)

        print("OutPOSt live robots verifier: FAIL", file=sys.stderr)
        print(f"  - {last_error}", file=sys.stderr)
        return 1

    except RobotsError as exc:
        print("OutPOSt live robots verifier: FAIL", file=sys.stderr)
        print(f"  - {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
