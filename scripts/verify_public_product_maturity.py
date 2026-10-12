#!/usr/bin/env python3
"""Guard public product maturity/status wording across key OutPOSt pages.

Read-only, standard-library only, and intentionally limited to static public HTML.
It does not call Cabinet, Director, Sync, D1, Workers, payment systems, PRRO APIs,
or any other protected service.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
from accounting_release_meta import load_accounting_release

ACCOUNTING_VERSION = load_accounting_release().version

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"

PAGE_CONTRACTS: dict[str, dict[str, object]] = {
    "/": {
        "file": "index.html",
        "required": (
            "власний робочий Native-контур",
            "Native ПРРО — власний робочий контур OutPOSt",
            "фінальні польові перевірки перед об’єднанням",
            "Доступна окрема OutPOSt Бухгалтерія без додаткової ліцензії на модуль.",
        ),
        "forbidden": (
            "Native ПРРО — production-ready",
            "Native ПРРО повністю готовий до production",
            "після клієнтського релізу — без окремої ліцензії",
        ),
        "forbidden_regex": (r"TEST[-‑ ]?прийман",),
    },
    "/prro": {
        "file": "prro.html",
        "required": (
            "Вбудований модуль · робочий контур",
            "<strong>Робочий</strong>",
            "фінальні польові перевірки перед об’єднанням",
            "не концепт «на майбутнє»",
            "не функція «в розробці»",
        ),
        "forbidden": (
            "Native ПРРО — production-ready",
            "Native ПРРО повністю готовий до production",
            "бойова активація завершена",
            "production-транспорт",
        ),
        "forbidden_regex": (r"TEST[-‑ ]?прийман",),
    },
    "/prro-checkbox": {
        "file": "prro-checkbox.html",
        "required": (
            "ПРРО CheckBox — модуль за потреби",
            "опціональна автофіскалізація",
            "Підключайте CheckBox лише тоді, коли він потрібен",
            '<span class="status-ok">Робочий контур</span>',
            "Native ПРРО — власний робочий контур OutPOSt",
        ),
        "forbidden": (),
        "forbidden_regex": (r"TEST[-‑ ]?прийман",),
    },
    "/features": {
        "file": "features.html",
        "required": (
            "Бухгалтерія входить до основного пакета OutPOSt без окремої ліцензії та встановлюється окремим Windows-інсталятором.",
            "Доступний Windows-інсталятор пройшов Windows RC 406/406",
            '<span class="status-ok">Робочий контур</span>',
            "Native ПРРО — поточний статус",
            f'<span>Для завантаження</span><strong>Бухгалтерія v{ACCOUNTING_VERSION}</strong><small>Windows · x86 · .NET 4.8</small>',
            '<span>Пакет</span><strong>Без окремої ліцензії</strong><small>у складі OutPOSt</small>',
            '<a href="/eakcyz">еАкциз/XTrace</a> має необов’язковий read-only Sandbox-контур',
            "production та write-операції заблоковані",
        ),
        "forbidden": (
            "Після завершення входить до основного пакета OutPOSt без окремої ліцензії",
            '<small>після клієнтського релізу</small>',
            "після клієнтського релізу входить до основного пакета без окремої ліцензії за модуль",
            "еАкциз/XTrace лишається інтеграційним напрямком",
            "сценарії Data Matrix і електронних марок готуються",
        ),
        "forbidden_regex": (r"TEST[-‑ ]?прийман",),
    },
    "/programa-dlya-nevelykogo-magazynu": {
        "file": "programa-dlya-nevelykogo-magazynu.html",
        "required": (
            "Власний Native-контур OutPOSt уже реалізований",
            "фінальні польові перевірки перед об’єднанням",
        ),
        "forbidden": (
            "після завершення фінального приймання, Native ПРРО",
        ),
        "forbidden_regex": (r"TEST[-‑ ]?прийман",),
    },
    "/programa-dlya-fop": {
        "file": "programa-dlya-fop.html",
        "required": (
            "Вбудований робочий контур OutPOSt",
            "фінальні польові перевірки перед об’єднанням",
            "OutPOSt Бухгалтерія входить до основного пакета без окремої ліцензії на модуль",
        ),
        "forbidden": (
            "Native ПРРО після приймання",
            "OutPOSt Бухгалтерія розробляється як частина основного пакета",
        ),
        "forbidden_regex": (r"TEST[-‑ ]?прийман",),
    },
    "/programa-dlya-kasy-windows": {
        "file": "programa-dlya-kasy-windows.html",
        "required": (
            "Власний робочий контур OutPOSt",
            "фінальні польові перевірки перед об’єднанням",
        ),
        "forbidden": (),
        "forbidden_regex": (r"TEST[-‑ ]?прийман",),
    },
    "/avtomatyzatsiya-rozdribnoi-torgivli": {
        "file": "avtomatyzatsiya-rozdribnoi-torgivli.html",
        "required": (
            "Власний робочий контур OutPOSt",
            "фінальні польові перевірки перед об’єднанням",
        ),
        "forbidden": (),
        "forbidden_regex": (r"TEST[-‑ ]?прийман",),
    },
    "/avtomatyzatsiya-magazynu": {
        "file": "avtomatyzatsiya-magazynu.html",
        "required": (
            "Native ПРРО — робочий інтегрований контур",
            "фінальні польові перевірки перед об’єднанням",
            "еАкциз/XTrace — необов’язковий read-only Sandbox-контур",
            "production та write-операції залишаються заблокованими",
        ),
        "forbidden": (
            "еАкциз/XTrace — напрямок інтеграції, який ще не заявлений production-ready",
        ),
        "forbidden_regex": (r"TEST[-‑ ]?прийман",),
    },
    "/offline-programa-dlya-magazynu": {
        "file": "offline-programa-dlya-magazynu.html",
        "required": (
            "еАкциз/XTrace — read-only Sandbox-запити",
            "production і write-операції залишаються заблокованими",
        ),
        "forbidden": (
            "Майбутні державні API, зокрема еАкциз/XTrace.",
        ),
    },
    "/buhgalteriya": {
        "file": "buhgalteriya.html",
        "required": (
            "Доступна Windows-версія",
            "Windows RC 406/406",
            "без окремої ліцензії",
            "не підписаний Authenticode",
            "Регламентовані форми, КЕП",
        ),
        "forbidden": (
            "Бухгалтерія — стабільний реліз",
            "готовий production-реліз Бухгалтерії",
            "Після завершення клієнтського релізу Бухгалтерія планується",
        ),
    },
    "/buhgalterska-programa-dlya-fop": {
        "file": "buhgalterska-programa-dlya-fop.html",
        "required": (
            "OutPOSt Бухгалтерія входить до основного продуктового пакета OutPOSt без окремої ліцензії",
            "і встановлюється окремою Windows-програмою",
            '<span>Пакет</span><strong>0 грн окремо</strong><small>у пакеті OutPOSt</small>',
        ),
        "forbidden": (
            "Після клієнтського релізу Бухгалтерія планується",
            '<small>після клієнтського релізу</small>',
        ),
    },
    "/bezkoshtovna-programa-dlya-magazynu": {
        "file": "bezkoshtovna-programa-dlya-magazynu.html",
        "required": (
            "Бухгалтерія входить до продуктового пакета OutPOSt без окремої ліцензії за модуль",
            "окрема Windows-програма Бухгалтерії доступна для завантаження",
        ),
        "forbidden": (
            "Бухгалтерія після клієнтського релізу входить до продуктового пакета",
        ),
    },
    "/support": {
        "file": "support.html",
        "required": (
            "OutPOSt Бухгалтерія входить до основного пакета OutPOSt без окремої ліцензії на модуль і встановлюється окремою Windows-програмою.",
            "Бухгалтерія входить до основного пакета OutPOSt і передбачає імпорт та обмін даними",
        ),
        "forbidden": (
            "Після клієнтського релізу OutPOSt Бухгалтерія входить",
            "Бухгалтерія розробляється як частина екосистеми OutPOSt",
        ),
    },
    "/license": {
        "file": "license.html",
        "required": (
            "OutPOSt Бухгалтерія входить до основного пакета без окремої ліцензії на модуль",
            "Для Windows доступна окрема програма Бухгалтерії, що пройшла приймальні перевірки.",
        ),
        "forbidden": (
            "Після публічного клієнтського релізу OutPOSt Бухгалтерія входить",
        ),
    },
    "/eakcyz": {
        "file": "eakcyz.html",
        "required": (
            "Доступний локальний read-only Sandbox-контур",
            "Production і будь-які віддалені записи залишаються заблокованими",
            "11 GET",
            "не активує і не погашає марку",
            "не надсилає АЕД",
        ),
        "forbidden": (
            "еАкциз готовий до production",
            "XTrace production-ready",
            "бойові записи XTrace доступні",
            "POST/PUT/PATCH/DELETE доступні",
        ),
    },
}

ACCOUNTING_SECTION_RE = re.compile(
    r'<section\b(?=[^>]*\bid="accounting")[^>]*>.*?</section>',
    re.DOTALL,
)
ACCOUNTING_VERSION_RE = re.compile(r"\bv\d+\.\d+(?:\.\d+)?\b", re.IGNORECASE)

RUNTIME_REQUIRED = (
    "OutPOSt Бухгалтерія входить до пакета OutPOSt без окремої ліцензії на модуль",
    "OutPOSt Бухгалтерія</a> входить до основного пакета без окремої ліцензії",
)
RUNTIME_FORBIDDEN = (
    "після клієнтського релізу модуль входить до основного пакета OutPOSt",
    "модуль входитиме до основного пакета без окремої ліцензії",
)

GLOBAL_HTML_EXCLUDED = {"changelog.html"}
GLOBAL_HTML_FORBIDDEN = (
    "еАкциз/XTrace — напрямок інтеграції, який ще не заявлений production-ready",
    "Майбутні державні API, зокрема еАкциз/XTrace.",
    "еАкциз/XTrace лишається інтеграційним напрямком",
    "сценарії Data Matrix і електронних марок готуються",
)


def validate_runtime_script_text(text: str) -> list[str]:
    errors: list[str] = []
    for marker in RUNTIME_REQUIRED:
        if marker not in text:
            errors.append(f"/script.js: missing runtime maturity/status marker {marker!r}")
    for marker in RUNTIME_FORBIDDEN:
        if marker in text:
            errors.append(f"/script.js: forbidden runtime maturity/status claim detected {marker!r}")
    return errors


def validate_global_html_text(filename: str, text: str) -> list[str]:
    if filename in GLOBAL_HTML_EXCLUDED:
        return []
    errors: list[str] = []
    for marker in GLOBAL_HTML_FORBIDDEN:
        if marker in text:
            errors.append(f"/site/{filename}: forbidden global maturity/status claim detected {marker!r}")
    return errors


def validate_page_text(pathname: str, text: str) -> list[str]:
    contract = PAGE_CONTRACTS[pathname]
    errors: list[str] = []

    for marker in contract["required"]:  # type: ignore[index]
        if marker not in text:
            errors.append(f"{pathname}: missing maturity/status marker {marker!r}")

    for marker in contract["forbidden"]:  # type: ignore[index]
        if marker in text:
            errors.append(f"{pathname}: forbidden maturity/status claim detected {marker!r}")

    for pattern in contract.get("forbidden_regex", ()):  # type: ignore[union-attr]
        if re.search(str(pattern), text, re.IGNORECASE):
            errors.append(f"{pathname}: forbidden maturity/status pattern detected {pattern!r}")

    if pathname == "/features":
        match = ACCOUNTING_SECTION_RE.search(text)
        if not match:
            errors.append("/features: accounting section id='accounting' is missing")
        else:
            # The visible public release number must remain consistent with the
            # canonical release manifest, not an arbitrary hard-coded version.
            from accounting_release_meta import load_accounting_release
            current = "v" + load_accounting_release().version
            version = ACCOUNTING_VERSION_RE.search(match.group(0))
            if not version or version.group(0) != current:
                errors.append(
                    "/features: Accounting section release must match canonical manifest; "
                    f"expected {current!r}, got {version.group(0) if version else None!r}"
                )

    return errors


def source_text(pathname: str) -> str:
    filename = str(PAGE_CONTRACTS[pathname]["file"])
    return (SITE / filename).read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []
    checked = 0

    for pathname in PAGE_CONTRACTS:
        filename = str(PAGE_CONTRACTS[pathname]["file"])
        path = SITE / filename
        if not path.is_file():
            errors.append(f"{pathname}: source file missing: site/{filename}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{pathname}: cannot read site/{filename}: {exc}")
            continue
        errors.extend(validate_page_text(pathname, text))
        checked += 1

    for html_path in sorted(SITE.glob("*.html")):
        try:
            html_text = html_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"/site/{html_path.name}: cannot read file: {exc}")
            continue
        errors.extend(validate_global_html_text(html_path.name, html_text))

    runtime_path = SITE / "script.js"
    try:
        runtime_text = runtime_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"/script.js: cannot read site/script.js: {exc}")
    else:
        errors.extend(validate_runtime_script_text(runtime_text))

    if errors:
        print(f"Public product maturity guard: FAIL ({len(errors)} issue(s))", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Public product maturity guard: PASS")
    print(f"  key public pages checked: {checked}")
    print("  Native ПРРО is a working contour in final field validation before desktop merge")
    print("  CheckBox remains an optional working integration path")
    print("  Accounting is available as an unsigned verified Windows installer")
    print("  runtime-injected Accounting copy matches the same included-package and unsigned-installer policy")
    print("  /features Accounting version matches the canonical release manifest")
    print("  eАкциз/XTrace remains explicitly non-production until real integration validation")
    print("  global public-HTML sweep blocks known stale еАкциз/XTrace status wording outside historical changelog")
    print("  no protected service was called")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
