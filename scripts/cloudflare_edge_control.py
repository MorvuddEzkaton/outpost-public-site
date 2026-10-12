#!/usr/bin/env python3
"""Plan or apply the two Cloudflare account-level fixes tracked by issues #61 and #95.

Default mode is read-only. Writes require both --apply and the exact confirmation
string APPLY-OUTPOST-CLOUDFLARE.

Required token capabilities:
- Zone > Zone > Read
- Zone > Config Rules > Edit
- Account > Bulk URL Redirects > Edit
- Account > Account Filter Lists > Edit

The script discovers the zone/account IDs from outpost.com.ua, so only one secret
(CLOUDFLARE_API_TOKEN) is required.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://api.cloudflare.com/client/v4"
ZONE_NAME = "outpost.com.ua"
TOKEN_ENV = "CLOUDFLARE_API_TOKEN"
CONFIRMATION = "APPLY-OUTPOST-CLOUDFLARE"

REDIRECT_LIST_NAME = "outpost_production_host_redirects"
REDIRECT_LIST_DESCRIPTION = "OutPOSt alternate production hosts -> canonical apex"
REDIRECT_RULE_REF = "outpost_enable_canonical_host_redirects"
REDIRECT_RULE_DESCRIPTION = "Enable OutPOSt canonical-host Bulk Redirect list"

RUM_RULE_REF = "outpost_disable_rum"
RUM_RULE_DESCRIPTION = "Disable Cloudflare RUM on canonical OutPOSt public host"

ALTERNATE_HOSTS = (
    "www.outpost.com.ua",
    "outpostua.pages.dev",
    "outpost-web.pages.dev",
)


class CloudflareError(RuntimeError):
    pass


@dataclass(frozen=True)
class ZoneContext:
    zone_id: str
    account_id: str
    zone_name: str


class CloudflareClient:
    def __init__(self, token: str, *, api_base: str = API_BASE) -> None:
        if not token:
            raise CloudflareError(f"{TOKEN_ENV} is required")
        self.token = token
        self.api_base = api_base.rstrip("/")

    def request(self, method: str, path: str, body: Any | None = None) -> Any:
        url = f"{self.api_base}{path}"
        data = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "OutPOSt-Cloudflare-edge-control/1.0",
        }
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(url, data=data, method=method, headers=headers)
        try:
            with urlopen(req, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"success": False, "errors": [{"message": raw or str(exc)}]}
            raise CloudflareError(
                f"Cloudflare API {method} {path} failed with HTTP {exc.code}: "
                f"{format_api_errors(payload)}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise CloudflareError(f"Cloudflare API {method} {path} network error: {exc}") from exc

        if not payload.get("success", False):
            raise CloudflareError(
                f"Cloudflare API {method} {path} returned success=false: "
                f"{format_api_errors(payload)}"
            )
        return payload

    def result(self, method: str, path: str, body: Any | None = None) -> Any:
        return self.request(method, path, body).get("result")


def format_api_errors(payload: dict[str, Any]) -> str:
    parts = []
    for item in payload.get("errors") or []:
        if isinstance(item, dict):
            code = item.get("code")
            msg = item.get("message")
            parts.append(f"{code}: {msg}" if code is not None else str(msg))
        else:
            parts.append(str(item))
    return "; ".join(parts) or "unknown API error"


def discover_context(client: CloudflareClient) -> ZoneContext:
    query = urlencode({"name": ZONE_NAME, "status": "active", "per_page": 50})
    zones = client.result("GET", f"/zones?{query}") or []
    exact = [z for z in zones if z.get("name") == ZONE_NAME and z.get("status") == "active"]
    if len(exact) != 1:
        raise CloudflareError(
            f"Expected exactly one active Cloudflare zone named {ZONE_NAME}, found {len(exact)}"
        )
    zone = exact[0]
    account_id = ((zone.get("account") or {}).get("id") or "").strip()
    zone_id = (zone.get("id") or "").strip()
    if not zone_id or not account_id:
        raise CloudflareError("Cloudflare zone response is missing zone/account ID")
    return ZoneContext(zone_id=zone_id, account_id=account_id, zone_name=ZONE_NAME)


def desired_redirect_items() -> list[dict[str, Any]]:
    items = []
    for host in ALTERNATE_HOSTS:
        items.append(
            {
                "redirect": {
                    "source_url": f"https://{host}/",
                    "target_url": f"https://{ZONE_NAME}/",
                    "status_code": 301,
                    "include_subdomains": False,
                    "subpath_matching": True,
                    "preserve_query_string": True,
                    "preserve_path_suffix": True,
                },
                "comment": f"OutPOSt canonical host normalization: {host}",
            }
        )
    return items


def normalize_redirect(item: dict[str, Any]) -> dict[str, Any]:
    redirect = item.get("redirect") or {}
    return {
        "redirect": {
            "source_url": redirect.get("source_url"),
            "target_url": redirect.get("target_url"),
            "status_code": redirect.get("status_code", 301),
            "include_subdomains": bool(redirect.get("include_subdomains", False)),
            "subpath_matching": bool(redirect.get("subpath_matching", False)),
            "preserve_query_string": bool(redirect.get("preserve_query_string", False)),
            "preserve_path_suffix": bool(redirect.get("preserve_path_suffix", True)),
        },
        "comment": item.get("comment") or "",
    }


def desired_redirect_rule() -> dict[str, Any]:
    return {
        "ref": REDIRECT_RULE_REF,
        "description": REDIRECT_RULE_DESCRIPTION,
        "expression": f"http.request.full_uri in ${REDIRECT_LIST_NAME}",
        "action": "redirect",
        "action_parameters": {
            "from_list": {
                "name": REDIRECT_LIST_NAME,
                "key": "http.request.full_uri",
            }
        },
        "enabled": True,
    }


def desired_rum_rule() -> dict[str, Any]:
    return {
        "ref": RUM_RULE_REF,
        "description": RUM_RULE_DESCRIPTION,
        "expression": f'(http.host eq "{ZONE_NAME}")',
        "action": "set_config",
        "action_parameters": {"disable_rum": True},
        "enabled": True,
    }


def list_account_redirect_lists(client: CloudflareClient, ctx: ZoneContext) -> list[dict[str, Any]]:
    query = urlencode({"per_page": 100})
    result = client.result("GET", f"/accounts/{ctx.account_id}/rules/lists?{query}")
    return result or []


def list_items(client: CloudflareClient, ctx: ZoneContext, list_id: str) -> list[dict[str, Any]]:
    result = client.result(
        "GET",
        f"/accounts/{ctx.account_id}/rules/lists/{list_id}/items?per_page=100",
    )
    return result or []


def list_rulesets(client: CloudflareClient, scope: str, scope_id: str) -> list[dict[str, Any]]:
    result = client.result("GET", f"/{scope}/{scope_id}/rulesets")
    return result or []


def get_ruleset(client: CloudflareClient, scope: str, scope_id: str, ruleset_id: str) -> dict[str, Any]:
    result = client.result("GET", f"/{scope}/{scope_id}/rulesets/{ruleset_id}")
    if not isinstance(result, dict):
        raise CloudflareError(f"Ruleset {ruleset_id} did not return an object")
    return result


def find_ruleset(
    rulesets: list[dict[str, Any]],
    *,
    phase: str,
    kind: str,
) -> dict[str, Any] | None:
    matches = [
        r
        for r in rulesets
        if r.get("phase") == phase and r.get("kind") == kind
    ]
    if len(matches) > 1:
        raise CloudflareError(f"Found multiple {kind} rulesets for phase {phase}")
    return matches[0] if matches else None


def find_managed_rule(rules: list[dict[str, Any]], ref: str) -> dict[str, Any] | None:
    matches = [r for r in rules if r.get("ref") == ref]
    if len(matches) > 1:
        raise CloudflareError(f"Found duplicate managed rule ref {ref}")
    return matches[0] if matches else None


def comparable_rule(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": rule.get("ref"),
        "description": rule.get("description") or "",
        "expression": rule.get("expression"),
        "action": rule.get("action"),
        "action_parameters": rule.get("action_parameters") or {},
        "enabled": bool(rule.get("enabled", True)),
    }


def wait_bulk_operation(
    client: CloudflareClient,
    ctx: ZoneContext,
    operation_id: str,
    *,
    attempts: int = 24,
    delay_seconds: int = 2,
) -> None:
    for _ in range(attempts):
        result = client.result(
            "GET",
            f"/accounts/{ctx.account_id}/rules/lists/bulk_operations/{operation_id}",
        ) or {}
        status = result.get("status")
        if status == "completed":
            return
        if status == "failed":
            raise CloudflareError(f"Cloudflare bulk list operation {operation_id} failed")
        time.sleep(delay_seconds)
    raise CloudflareError(f"Cloudflare bulk list operation {operation_id} did not complete in time")


def plan_state(client: CloudflareClient, ctx: ZoneContext) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []

    redirect_lists = list_account_redirect_lists(client, ctx)
    named_lists = [x for x in redirect_lists if x.get("name") == REDIRECT_LIST_NAME]
    if len(named_lists) > 1:
        raise CloudflareError(f"Duplicate redirect lists named {REDIRECT_LIST_NAME}")
    redirect_list = named_lists[0] if named_lists else None

    if redirect_list is None:
        actions.append({"component": "redirect_list", "action": "create"})
        redirect_items_match = False
    else:
        current_items = [normalize_redirect(x) for x in list_items(client, ctx, redirect_list["id"])]
        wanted_items = [normalize_redirect(x) for x in desired_redirect_items()]
        redirect_items_match = sorted(
            current_items, key=lambda x: x["redirect"]["source_url"] or ""
        ) == sorted(wanted_items, key=lambda x: x["redirect"]["source_url"] or "")
        if not redirect_items_match:
            actions.append(
                {
                    "component": "redirect_list_items",
                    "action": "replace_dedicated_list_items",
                    "current_count": len(current_items),
                    "desired_count": len(wanted_items),
                }
            )

    account_rulesets = list_rulesets(client, "accounts", ctx.account_id)
    account_redirect = find_ruleset(
        account_rulesets, phase="http_request_redirect", kind="root"
    )
    current_redirect_rule = None
    if account_redirect:
        account_redirect = get_ruleset(
            client, "accounts", ctx.account_id, account_redirect["id"]
        )
        current_redirect_rule = find_managed_rule(account_redirect.get("rules") or [], REDIRECT_RULE_REF)

    if current_redirect_rule is None:
        actions.append(
            {
                "component": "redirect_rule",
                "action": "create_ruleset_and_rule" if account_redirect is None else "add_rule",
            }
        )
    elif comparable_rule(current_redirect_rule) != comparable_rule(desired_redirect_rule()):
        actions.append({"component": "redirect_rule", "action": "update_rule"})

    zone_rulesets = list_rulesets(client, "zones", ctx.zone_id)
    config_ruleset = find_ruleset(zone_rulesets, phase="http_config_settings", kind="zone")
    current_rum_rule = None
    if config_ruleset:
        config_ruleset = get_ruleset(client, "zones", ctx.zone_id, config_ruleset["id"])
        current_rum_rule = find_managed_rule(config_ruleset.get("rules") or [], RUM_RULE_REF)

    if current_rum_rule is None:
        actions.append(
            {
                "component": "disable_rum",
                "action": "create_ruleset_and_rule" if config_ruleset is None else "add_rule",
            }
        )
    elif comparable_rule(current_rum_rule) != comparable_rule(desired_rum_rule()):
        actions.append({"component": "disable_rum", "action": "update_rule"})

    return {
        "zone": {"name": ctx.zone_name, "zone_id": ctx.zone_id, "account_id": ctx.account_id},
        "redirect_list_exists": redirect_list is not None,
        "redirect_items_match": redirect_items_match,
        "redirect_rule_match": (
            current_redirect_rule is not None
            and comparable_rule(current_redirect_rule) == comparable_rule(desired_redirect_rule())
        ),
        "rum_rule_match": (
            current_rum_rule is not None
            and comparable_rule(current_rum_rule) == comparable_rule(desired_rum_rule())
        ),
        "actions": actions,
    }


def create_redirect_list(client: CloudflareClient, ctx: ZoneContext) -> dict[str, Any]:
    result = client.result(
        "POST",
        f"/accounts/{ctx.account_id}/rules/lists",
        {
            "name": REDIRECT_LIST_NAME,
            "description": REDIRECT_LIST_DESCRIPTION,
            "kind": "redirect",
        },
    )
    if not isinstance(result, dict) or not result.get("id"):
        raise CloudflareError("Creating redirect list did not return a list ID")
    return result


def replace_redirect_items(
    client: CloudflareClient,
    ctx: ZoneContext,
    list_id: str,
) -> None:
    result = client.result(
        "PUT",
        f"/accounts/{ctx.account_id}/rules/lists/{list_id}/items",
        desired_redirect_items(),
    ) or {}
    operation_id = result.get("operation_id")
    if not operation_id:
        raise CloudflareError("Replacing redirect list items did not return operation_id")
    wait_bulk_operation(client, ctx, operation_id)


def upsert_redirect_rule(client: CloudflareClient, ctx: ZoneContext) -> None:
    rulesets = list_rulesets(client, "accounts", ctx.account_id)
    ruleset = find_ruleset(rulesets, phase="http_request_redirect", kind="root")
    wanted = desired_redirect_rule()

    if ruleset is None:
        client.result(
            "POST",
            f"/accounts/{ctx.account_id}/rulesets",
            {
                "name": "OutPOSt Bulk Redirects",
                "description": "Account-level redirects managed by OutPOSt repository tooling",
                "kind": "root",
                "phase": "http_request_redirect",
                "rules": [wanted],
            },
        )
        return

    full = get_ruleset(client, "accounts", ctx.account_id, ruleset["id"])
    current = find_managed_rule(full.get("rules") or [], REDIRECT_RULE_REF)
    if current is None:
        client.result(
            "POST",
            f"/accounts/{ctx.account_id}/rulesets/{ruleset['id']}/rules",
            wanted,
        )
    elif comparable_rule(current) != comparable_rule(wanted):
        client.result(
            "PATCH",
            f"/accounts/{ctx.account_id}/rulesets/{ruleset['id']}/rules/{current['id']}",
            wanted,
        )


def upsert_rum_rule(client: CloudflareClient, ctx: ZoneContext) -> None:
    rulesets = list_rulesets(client, "zones", ctx.zone_id)
    ruleset = find_ruleset(rulesets, phase="http_config_settings", kind="zone")
    wanted = desired_rum_rule()

    if ruleset is None:
        client.result(
            "POST",
            f"/zones/{ctx.zone_id}/rulesets",
            {
                "name": "OutPOSt Configuration Rules",
                "description": "Zone configuration managed by OutPOSt repository tooling",
                "kind": "zone",
                "phase": "http_config_settings",
                "rules": [wanted],
            },
        )
        return

    full = get_ruleset(client, "zones", ctx.zone_id, ruleset["id"])
    current = find_managed_rule(full.get("rules") or [], RUM_RULE_REF)
    if current is None:
        client.result(
            "POST",
            f"/zones/{ctx.zone_id}/rulesets/{ruleset['id']}/rules",
            wanted,
        )
    elif comparable_rule(current) != comparable_rule(wanted):
        client.result(
            "PATCH",
            f"/zones/{ctx.zone_id}/rulesets/{ruleset['id']}/rules/{current['id']}",
            wanted,
        )


def apply_state(client: CloudflareClient, ctx: ZoneContext) -> dict[str, Any]:
    redirect_lists = list_account_redirect_lists(client, ctx)
    named_lists = [x for x in redirect_lists if x.get("name") == REDIRECT_LIST_NAME]
    if len(named_lists) > 1:
        raise CloudflareError(f"Duplicate redirect lists named {REDIRECT_LIST_NAME}")
    redirect_list = named_lists[0] if named_lists else create_redirect_list(client, ctx)

    current_items = [normalize_redirect(x) for x in list_items(client, ctx, redirect_list["id"])]
    wanted_items = [normalize_redirect(x) for x in desired_redirect_items()]
    if sorted(current_items, key=lambda x: x["redirect"]["source_url"] or "") != sorted(
        wanted_items, key=lambda x: x["redirect"]["source_url"] or ""
    ):
        replace_redirect_items(client, ctx, redirect_list["id"])

    upsert_redirect_rule(client, ctx)
    upsert_rum_rule(client, ctx)
    return plan_state(client, ctx)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the exact OutPOSt Cloudflare edge state. Default is read-only plan.",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help=f"Required with --apply: {CONFIRMATION}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the state summary as JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.getenv(TOKEN_ENV, "").strip()
    if not token:
        print(
            f"{TOKEN_ENV} is not configured. Add a scoped Cloudflare API token before running "
            "this control workflow.",
            file=sys.stderr,
        )
        return 2
    if args.apply and args.confirm != CONFIRMATION:
        print(
            f"Refusing Cloudflare mutation: --confirm must equal {CONFIRMATION!r}",
            file=sys.stderr,
        )
        return 2

    client = CloudflareClient(token)
    try:
        ctx = discover_context(client)
        before = plan_state(client, ctx)
        if args.apply and before["actions"]:
            after = apply_state(client, ctx)
        else:
            after = before
    except CloudflareError as exc:
        print(f"Cloudflare edge control: FAIL\n  - {exc}", file=sys.stderr)
        return 1

    payload = {
        "mode": "apply" if args.apply else "plan",
        "before": before,
        "after": after,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Cloudflare edge control: {'APPLIED' if args.apply else 'PLAN'}")
        print(f"  zone: {ctx.zone_name}")
        print(f"  planned actions before run: {len(before['actions'])}")
        for item in before["actions"]:
            print(f"    - {item['component']}: {item['action']}")
        print(f"  remaining actions after run: {len(after['actions'])}")
        print(f"  host redirects ready: {after['redirect_items_match'] and after['redirect_rule_match']}")
        print(f"  RUM disable rule ready: {after['rum_rule_match']}")

    if args.apply and after["actions"]:
        print("Cloudflare edge control: FAIL — desired state not reached after apply", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
