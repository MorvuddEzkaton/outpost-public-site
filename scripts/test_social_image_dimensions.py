#!/usr/bin/env python3
"""Offline regressions for source/live Open Graph PNG dimension parsing."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from verify_live_social_metadata import png_dimensions as live_png_dimensions
from verify_public_site import png_dimensions as source_png_dimensions


ROOT = Path(__file__).resolve().parents[1]
SOCIAL_IMAGE = ROOT / "site" / "assets" / "outpost-sales-v0231.png"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def png_header(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


def test_live_parser_reads_ihdr_dimensions() -> None:
    require(
        live_png_dimensions(png_header(1350, 689)) == (1350, 689),
        "live PNG parser must read IHDR dimensions",
    )


def test_source_parser_reads_ihdr_dimensions() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "fixture.png"
        path.write_bytes(png_header(1350, 689))
        require(
            source_png_dimensions(path) == (1350, 689),
            "source PNG parser must read IHDR dimensions",
        )


def test_invalid_png_fails_closed() -> None:
    require(live_png_dimensions(b"not-a-png") is None, "invalid live PNG bytes must fail")
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "broken.png"
        path.write_bytes(b"not-a-png")
        require(source_png_dimensions(path) is None, "invalid source PNG bytes must fail")


def test_current_social_image_is_1350x689() -> None:
    require(SOCIAL_IMAGE.is_file(), "current Open Graph image is missing")
    require(
        source_png_dimensions(SOCIAL_IMAGE) == (1350, 689),
        "current Open Graph image dimensions changed; update page metadata intentionally",
    )


def main() -> int:
    tests = (
        test_live_parser_reads_ihdr_dimensions,
        test_source_parser_reads_ihdr_dimensions,
        test_invalid_png_fails_closed,
        test_current_social_image_is_1350x689,
    )
    for test in tests:
        test()
    print("Social image dimension regression tests: PASS")
    print(f"  {len(tests)}/{len(tests)} offline tests passed")
    print("  current source social image: 1350x689")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
