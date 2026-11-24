#!/usr/bin/env python3
"""Offline MSI/EXE Partner Center CSV patcher for OutPOSt Lite en-US only.

No network, no credentials, no publication. Operates on a genuine export.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/store/english-lite-listing.json"
PRODUCT_ID = "9N5K4B1229VC"
LOCALE = "en-US"
PRODUCT_NAME = "OutPOSt Lite"
ALLOWED = {"Description": 10000, "ShortDescription": 1000}
ALLOWED.update({f"ProductFeatures{i}": 200 for i in range(1, 9)})
ALLOWED.update({f"SearchTerms{i}": 30 for i in range(1, 8)})

def load_fields() -> dict[str, str]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (data.get("productId"), data.get("locale"), data.get("productName")) != (PRODUCT_ID, LOCALE, PRODUCT_NAME):
        raise ValueError("Manifest product identity mismatch")
    fields = data["fields"]
    if set(fields) != set(ALLOWED):
        raise ValueError("Manifest contains missing or unapproved fields")
    for key, value in fields.items():
        if not isinstance(value, str) or not value.strip() or len(value) > ALLOWED[key]:
            raise ValueError(f"Invalid text length for {key}")
        if re.search(r"https?://|<[^>]+>", value):
            raise ValueError(f"URL or HTML in text field {key}")
    terms = [fields[f"SearchTerms{i}"] for i in range(1, 8)]
    if len(set(" ".join(terms).lower().split())) > 21 or len(set(terms)) != 7:
        raise ValueError("Search term limits exceeded")
    return fields

def patch_export(raw: bytes, fields: dict[str, str], *, allow_replace: bool = False) -> tuple[bytes, list[str]]:
    """Preserve CSV dimensions, row order, languages and all unrelated values."""
    if not raw:
        raise ValueError("Empty export")
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    if not rows or len(rows[0]) < 3:
        raise ValueError("Expected original Partner Center Field, Type and language columns")
    header = rows[0]
    if header[:2] != ["Field", "Type"] or len(set(header)) != len(header) or LOCALE not in header[2:]:
        raise ValueError("Unexpected template; add en-US in Partner Center and export again")
    index = header.index(LOCALE)
    if any(len(row) != len(header) for row in rows[1:]):
        raise ValueError("Non-rectangular export; no rows changed")
    names = [row[0] for row in rows[1:]]
    if any(not key for key in names) or len(names) != len(set(names)):
        raise ValueError("Empty or duplicate field name")
    mapped = {row[0]: row for row in rows[1:]}
    if not set(fields) <= set(mapped) or "ProductName" not in mapped:
        raise ValueError("Expected listing fields missing; export actual MSI/EXE template")
    # Never infer identity from an empty translated title.
    if not any(v.strip() == PRODUCT_NAME for v in mapped["ProductName"][2:]):
        raise ValueError("No exact OutPOSt Lite title in the original export")
    if mapped["ProductName"][index].strip() not in ("", PRODUCT_NAME):
        raise ValueError("English product name conflicts with reviewed product")
    changed = []
    for key, value in fields.items():
        row = mapped[key]
        if row[1].strip().lower() != "text":
            raise ValueError(f"Unexpected field type for {key}: {row[1]!r}")
        old = row[index]
        if old == value:
            continue
        if old.strip() and not allow_replace:
            raise ValueError(f"{key} already contains text; review before --allow-replace")
        row[index] = value
        changed.append(key)
    out = io.StringIO(newline="")
    csv.writer(out, lineterminator="\r\n").writerows(rows)
    result = out.getvalue().encode("utf-8")
    return ((b"\xef\xbb\xbf" + result) if bom else result), changed

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--input", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--product-id")
    ap.add_argument("--allow-replace", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PatchTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.product_id != PRODUCT_ID or not args.input or not args.output:
        ap.error("Require --product-id 9N5K4B1229VC, --input and --output; confirm the export belongs to Lite")
    try:
        if args.input.resolve() == args.output.resolve() or args.output.exists():
            raise ValueError("Output must be a new path; never overwrite original or another file")
        patched, changed = patch_export(args.input.read_bytes(), load_fields(), allow_replace=args.allow_replace)
        with args.output.open("xb") as handle:
            handle.write(patched)
        print("Offline draft created:", args.output)
        print("Changed English fields:", ", ".join(changed) or "(none)")
        print("Review the diff and real package/screenshots before importing. No submission performed.")
        return 0
    except (OSError, UnicodeError, csv.Error, ValueError, KeyError) as exc:
        print(f"Rejected: {exc}", file=sys.stderr)
        return 1

class PatchTests(unittest.TestCase):
    def fixture(self, *, locale=LOCALE, name=PRODUCT_NAME, occupied=False):
        rows = [["Field", "Type", "uk-UA", locale], ["ProductName", "Text", name, ""],
                ["Screenshots1", "Relative path", "ua.png", "en.png"],
                ["WhatsNew", "Text", "UA release", "EN release"]]
        rows += [[key, "Text", "UA, untouched", "Existing" if occupied else ""] for key in ALLOWED]
        out = io.StringIO(newline="")
        csv.writer(out).writerows(rows)
        return out.getvalue().encode("utf-8")
    def test_preserve_other_values_and_bom(self):
        raw = b"\xef\xbb\xbf" + self.fixture()
        new, changed = patch_export(raw, load_fields())
        before = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        after = list(csv.reader(io.StringIO(new.decode("utf-8-sig"))))
        self.assertTrue(new.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(len(changed), len(ALLOWED))
        self.assertEqual([r[:3] for r in before], [r[:3] for r in after])
        self.assertEqual(before[:4], after[:4])
    def test_wrong_product_rejected(self):
        with self.assertRaises(ValueError):
            patch_export(self.fixture(name="OutPOSt Retail"), load_fields())
    def test_missing_locale_rejected(self):
        with self.assertRaises(ValueError):
            patch_export(self.fixture(locale="en-GB"), load_fields())
    def test_existing_text_requires_review(self):
        with self.assertRaises(ValueError):
            patch_export(self.fixture(occupied=True), load_fields())
        _, changed = patch_export(self.fixture(occupied=True), load_fields(), allow_replace=True)
        self.assertEqual(len(changed), len(ALLOWED))
    def test_idempotence(self):
        first, _ = patch_export(self.fixture(), load_fields())
        second, changed = patch_export(first, load_fields())
        self.assertEqual(first, second)
        self.assertEqual(changed, [])
    def test_missing_field_rejected(self):
        raw = self.fixture().replace(b"Description,Text,", b"UnknownDescription,Text,", 1)
        with self.assertRaises(ValueError):
            patch_export(raw, load_fields())
    def test_non_rectangular_rejected(self):
        with self.assertRaises(ValueError):
            patch_export(self.fixture() + b"bad,row\r\n", load_fields())
    def test_duplicate_field_rejected(self):
        with self.assertRaises(ValueError):
            patch_export(self.fixture() + b"Description,Text,,\r\n", load_fields())
    def test_wrong_type_rejected(self):
        raw = self.fixture().replace(b"Description,Text,", b"Description,Relative path,", 1)
        with self.assertRaises(ValueError):
            patch_export(raw, load_fields())

if __name__ == "__main__":
    raise SystemExit(main())
