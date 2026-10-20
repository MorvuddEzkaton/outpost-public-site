#!/usr/bin/env python3
"""Offline negative regression tests for the first-party local-asset guard."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_first_party_resources import (  # noqa: E402
    ResourceCollector,
    check_local_static_resource,
    is_forbidden_external,
    local_static_target,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="outpost-static-assets-") as directory:
        root = Path(directory) / "site"
        assets = root / "assets"
        assets.mkdir(parents=True)
        page = root / "index.html"
        css = assets / "style.css"
        existing = assets / "picture.webp"
        page.write_text("test", encoding="utf-8")
        css.write_text("test", encoding="utf-8")
        existing.write_bytes(b"fixture")

        assert local_static_target(page, "/assets/picture.webp?v=2#crop", root) == existing.resolve()
        assert local_static_target(css, "./picture.webp", root) == existing.resolve()
        assert local_static_target(page, "https://outpost.com.ua/assets/picture.webp", root) == existing.resolve()
        assert local_static_target(page, "https://other.example/picture.webp", root) is None
        assert local_static_target(css, "data:image/png;base64,aGVsbG8=", root) is None
        assert local_static_target(css, "#gradient", root) is None
        assert local_static_target(page, "/api/session", root) is None

        errors: list[str] = []
        check_local_static_resource(css, "css url()", "../assets/picture.webp", errors, root)
        assert not errors, errors
        check_local_static_resource(css, "css url()", "./missing.webp", errors, root)
        assert len(errors) == 1 and "missing local asset" in errors[0], errors

        errors.clear()
        check_local_static_resource(css, "css url()", "../../private.png", errors, root)
        assert len(errors) == 1 and "escapes public site root" in errors[0], errors

        collector = ResourceCollector()
        collector.feed(
            '<img src="/assets/picture.webp" '
            'srcset="/assets/picture.webp 1x, /assets/missing@2x.webp 2x">'
            '<video poster="/assets/video-poster.webp"></video>'
            '<source srcset="/assets/missing-mobile.webp 640w">'
        )
        resources = collector.resources
        assert ("img[srcset]", "/assets/missing@2x.webp") in resources, resources
        assert ("video[poster]", "/assets/video-poster.webp") in resources, resources
        assert ("source[srcset]", "/assets/missing-mobile.webp") in resources, resources

        errors.clear()
        for context, value in resources:
            if not is_forbidden_external(value):
                check_local_static_resource(page, context, value, errors, root)
        assert len(errors) == 3 and all("missing local asset" in error for error in errors), errors

    print("First-party local asset negative regression tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
