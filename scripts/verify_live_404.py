#!/usr/bin/env python3
"""Read-only post-deploy verification for live OutPOSt 404 behavior."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import os
import sys
import time

ORIGIN = "https://outpost.com.ua"
USER_AGENT = "OutPOSt-Live-404-Verify/1.0"


class MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.robots: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        data = {key.lower(): (value or "") for key, value in attrs}
        if data.get("name", "").lower() == "robots":
            self.robots.append(data.get("content", ""))


class VerifyError(RuntimeError):
    pass


def fetch_404(path: str) -> tuple[int, dict[str, str], str]:
    request = Request(
        ORIGIN + path,
        headers={
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Accept": "text/html,*/*;q=0.1",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            status = int(getattr(response, "status", response.getcode()))
            headers = {key.lower(): value for key, value in response.headers.items()}
            body = response.read().decode("utf-8", errors="replace")
            return status, headers, body
    except HTTPError as exc:
        status = int(exc.code)
        headers = {key.lower(): value for key, value in exc.headers.items()}
        body = exc.read().decode("utf-8", errors="replace")
        return status, headers, body
    except (URLError, TimeoutError, OSError) as exc:
        raise VerifyError(f"request failed for {path}: {exc}") from exc


def verify_once() -> None:
    nonce = f"{int(time.time())}-{os.getpid()}"
    paths = (
        f"/definitely-missing-{nonce}",
        f"/nested/definitely-missing-{nonce}",
        f"/definitely-missing-{nonce}.html",
    )

    errors: list[str] = []
    for path in paths:
        status, headers, body = fetch_404(path)
        parser = MetaParser()
        parser.feed(body)
        x_robots = headers.get("x-robots-tag", "")

        if status != 404:
            errors.append(f"{path}: expected HTTP 404, got {status}")
        if not any("noindex" in value.lower() for value in parser.robots) and "noindex" not in x_robots.lower():
            errors.append(f"{path}: live 404 response lacks noindex")
        if "Сторінку не знайдено" not in body:
            errors.append(f"{path}: OutPOSt 404 body marker is missing")
        content_type = headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            errors.append(f"{path}: expected text/html error response, got {content_type or 'missing content-type'}")

    if errors:
        raise VerifyError("; ".join(errors))

    print(f"  {len(paths)}/{len(paths)} unknown routes return real noindex HTTP 404")


def main() -> int:
    attempts = max(1, int(os.environ.get("OUTPOST_LIVE_404_ATTEMPTS", "4")))
    delay = max(0, int(os.environ.get("OUTPOST_LIVE_404_DELAY_SECONDS", "5")))
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            verify_once()
            print("OutPOSt live 404 verification: PASS")
            print("  unknown extensionless, nested and .html routes are not soft-404s")
            print("  error responses remain non-indexable")
            print("  protected services were not called")
            return 0
        except Exception as exc:
            last_error = exc
            print(f"Attempt {attempt}/{attempts}: {exc}")
            if attempt < attempts:
                time.sleep(delay)

    print(f"OutPOSt live 404 verification: FAIL\n  - {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
