#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
STYLES = SITE / "styles.css"


def luminance(value: str) -> float:
    h = value.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Expected 6-digit hex color, got {value!r}")
    rgb = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]

    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = map(linear, rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(foreground: str, background: str) -> float:
    hi, lo = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def token(css: str, name: str) -> str:
    match = re.search(rf"--{re.escape(name)}:\s*(#[0-9a-fA-F]{{6}})", css)
    if not match:
        raise SystemExit(f"Missing CSS token --{name}")
    return match.group(1).lower()


def require_ratio(label: str, fg: str, bg: str, minimum: float = 4.5) -> None:
    value = contrast(fg, bg)
    print(f"{label}: {value:.2f}:1")
    if value + 1e-9 < minimum:
        raise SystemExit(f"{label}: {value:.2f}:1 is below {minimum:.1f}:1")


css = STYLES.read_text(encoding="utf-8")
blue_text = token(css, "blue-text")
orange_text = token(css, "orange-text")
muted = token(css, "muted")
navy_950 = token(css, "navy-950")

for name, fg in (("blue-text", blue_text), ("orange-text", orange_text), ("muted", muted)):
    require_ratio(f"{name} on white", fg, "#ffffff")
    require_ratio(f"{name} on soft", fg, "#f5f7fa")

require_ratio("small neutral on screenshot soft", "#65717e", "#f2f5f8")
require_ratio("footer small text on navy", "#8291a1", navy_950)

question_css = (SITE / "assets" / "outpost-public-question-v02444.css").read_text(encoding="utf-8")
question_blue = token(question_css, "outpost-q-blue")
require_ratio("public question blue on white", question_blue, "#ffffff")

# These files use blue specifically as small text/link accents. The brighter brand
# blue remains available for decorative/background use elsewhere, but must not be
# reintroduced as normal-size text in these components.
text_css_files = [
    SITE / "assets" / "outpost-seo-wave1-v02450.css",
    SITE / "assets" / "outpost-seo-wave2-v02451.css",
    SITE / "assets" / "outpost-seo-internal-links-v02452.css",
]
for path in text_css_files:
    text = path.read_text(encoding="utf-8")
    if re.search(r"color\s*:\s*#2f7df6\b", text, re.IGNORECASE):
        raise SystemExit(f"{path}: legacy low-contrast brand blue used as text color")

# SEO detail cards are dark, so their kicker needs an inverse/light accent rather
# than the normal text-blue used on white surfaces.
for path in text_css_files[:2]:
    text = path.read_text(encoding="utf-8")
    required = ".seo-detail-card .seo-kicker{color:#7bb2ff}"
    if required not in text:
        raise SystemExit(f"{path}: missing accessible dark-card kicker override")
require_ratio("SEO detail-card kicker on navy", "#7bb2ff", "#101927")

internal_links_css = text_css_files[2].read_text(encoding="utf-8")
if ".seo-link-strip>span{margin-right:2px;color:#687789;" not in internal_links_css:
    raise SystemExit("SEO internal-link strip label must use accessible #687789 text")
require_ratio("SEO link-strip label on white", "#687789", "#ffffff")

support_css = (SITE / "assets" / "outpost-support-v02460.css").read_text(encoding="utf-8")
for required in ("var(--blue-text)", "var(--orange-text)"):
    if required not in support_css:
        raise SystemExit(f"Support CSS is missing accessible text token {required}")

print("Public color contrast guard: PASS")
