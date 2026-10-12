#!/usr/bin/env python3
"""Regression guard for the user-provided seven-step debt-sale screenshot tour.

This checks our own local WebP assets and HTML structure; no network, secrets or
live customer data are read. Real UX/accessibility is separately tested in CI.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_FILE = ROOT / "site/prodazh-v-borg.html"
ASSET_DIR = ROOT / "site/assets/screenshots/02410/debt-sale"
ASSETS = (
    ("01-cart.webp", "00774b6e84941d9269f840423c6992f8bc0f46642706b49f0afeb43242a5c76b", 1429, 817),
    ("02-customer.webp", "4e87c00e9826b173b43864cce8bd34e661fb5096e749c86e781892edd60b9ace", 1429, 817),
    ("03-debt-dialog.webp", "2ef14aac15895d048ddba4e7ebb4705dd32465c23891378293c3a67373085558", 1432, 815),
    ("04-confirmation.webp", "be2e727f72d3f947847c1d78f26ded8a44cf4dd6d62eda64d6c78aea1df6e4b9", 1430, 814),
    ("05-debt-history.webp", "120cd9478910cabb288dcdf4c368ad8fd4b9479a57cf1e30377fdb238571c612", 1432, 814),
    ("06-repayment-dialog.webp", "3d74881c9efeab68c722abccf6809cd419822965bd9a20baa6f63d3ca1d6f341", 1433, 816),
    ("07-after-repayment.webp", "6915e0f6c5f2df5d9f403ee001312a8b1d17b77817c11d9781eaeb76d1bd8f88", 1431, 818),
)


def main() -> int:
    html = HTML_FILE.read_text(encoding="utf-8")
    assert html.count('class="feature-tour debt-story debt-single-slider"') == 1, "one full showcase required"
    assert html.count('class="debt-story-sequence"') == 1, "all frames in one slider"
    assert 'id="debt-sale-gallery"' in html and 'id="debt-repayment-gallery"' not in html
    assert html.count('class="debt-story-item"') == 7, "all seven frames retained"
    assert "debt-story-zoom" not in html and "debt-story-nav" not in html
    assert html.index('class="scenario-related"') < html.index('class="feature-tour debt-story debt-single-slider"') < html.index('class="scenario-cta"'), "showcase must be close to page bottom"
    assert 'height="undefined"' not in html, "broken image sizing"
    assert "Цей приклад демонструє повне погашення" in html, "do not call full repayment partial"
    positions: list[int] = []
    for name, expected_sha, width, height in ASSETS:
        asset = ASSET_DIR / name
        assert asset.is_file(), f"missing asset: {name}"
        data = asset.read_bytes()
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP", f"not a WebP file: {name}"
        assert hashlib.sha256(data).hexdigest() == expected_sha, f"unexpected edit: {name}"
        assert 5_000 < len(data) < 180_000, f"unexpected file size: {name}"
        url = f"/assets/screenshots/02410/debt-sale/{name}"
        assert html.count(f'src="{url}"') == 1, f"expected exactly one embedded image: {name}"
        assert html.count(f'href="{url}"') == 1, f"expected a single clickable image link: {name}"
        tag = re.search(r'<img\b[^>]*src="' + re.escape(url) + r'"[^>]*>', html)
        assert tag is not None, f"image tag not found: {name}"
        assert f'width="{width}"' in tag.group() and f'height="{height}"' in tag.group(), f"bad dimensions: {name}"
        assert re.search(r'alt="[^"]{35,}"', tag.group()), f"meaningful alt is required: {name}"
        expected_loading = 'loading="eager"' if name == "01-cart.webp" else 'loading="lazy"'
        assert expected_loading in tag.group() and 'decoding="async"' in tag.group(), f"missing perf hints: {name}"
        positions.append(html.index(f'src="{url}"'))
    assert positions == sorted(positions), "walkthrough image sequence changed"
    print("PASS: one bottom-positioned seven-step debt slider with original ordered images, hashes and accessible links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
