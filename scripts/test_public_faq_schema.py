#!/usr/bin/env python3
"""Synthetic regressions for public FAQ JSON-LD uniqueness validation."""

from __future__ import annotations

from pathlib import Path

from verify_public_site import validate_faq_schema_question_uniqueness


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_real_veteran_page_passes() -> None:
    path = SITE / "bezkoshtovna-programa-dlya-magazynu.html"
    html = path.read_text(encoding="utf-8")
    errors = validate_faq_schema_question_uniqueness(path.name, html)
    require(not errors, f"real veteran FAQ schema must pass: {errors}")


def test_duplicate_question_name_fails() -> None:
    html = """
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
      {"@type":"Question","name":"Same question?","acceptedAnswer":{"@type":"Answer","text":"One"}},
      {"@type":"Question","name":"Same question?","acceptedAnswer":{"@type":"Answer","text":"Two"}}
    ]}
    </script>
    """
    errors = validate_faq_schema_question_uniqueness("fixture.html", html)
    require(
        any("duplicate FAQ Question.name" in error and "Same question?" in error for error in errors),
        "duplicate FAQ question name must fail",
    )


def test_duplicate_across_json_ld_blocks_fails() -> None:
    html = """
    <script type="application/ld+json">
    {"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"Cross-block?","acceptedAnswer":{"@type":"Answer","text":"One"}}]}
    </script>
    <script type="application/ld+json">
    {"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"Cross-block?","acceptedAnswer":{"@type":"Answer","text":"Two"}}]}
    </script>
    """
    errors = validate_faq_schema_question_uniqueness("fixture.html", html)
    require(
        any("duplicate FAQ Question.name" in error and "Cross-block?" in error for error in errors),
        "duplicate FAQ question across JSON-LD blocks must fail",
    )


def test_malformed_json_ld_fails() -> None:
    html = '<script type="application/ld+json">{"@type":"FAQPage",</script>'
    errors = validate_faq_schema_question_uniqueness("fixture.html", html)
    require(any("malformed JSON-LD" in error for error in errors), "malformed JSON-LD must fail")


def test_non_question_names_do_not_collide() -> None:
    html = """
    <script type="application/ld+json">
    {"@graph":[
      {"@type":"WebPage","name":"Same label"},
      {"@type":"Organization","name":"Same label"}
    ]}
    </script>
    """
    require(
        not validate_faq_schema_question_uniqueness("fixture.html", html),
        "non-Question schema names must not participate in FAQ uniqueness checks",
    )


def main() -> int:
    tests = (
        test_real_veteran_page_passes,
        test_duplicate_question_name_fails,
        test_duplicate_across_json_ld_blocks_fails,
        test_malformed_json_ld_fails,
        test_non_question_names_do_not_collide,
    )
    for test in tests:
        test()

    print("Public FAQ JSON-LD regression: PASS")
    print(f"  {len(tests)}/{len(tests)} tests passed")
    print("  malformed JSON-LD and duplicate FAQ Question.name values fail closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
