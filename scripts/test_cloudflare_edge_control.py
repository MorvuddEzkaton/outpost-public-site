#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "cloudflare_edge_control.py"

spec = importlib.util.spec_from_file_location("cloudflare_edge_control", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class FakeClient:
    def __init__(self, ready: bool) -> None:
        self.ready = ready

    def result(self, method: str, path: str, body=None):
        assert method == "GET"
        if "/rules/lists?" in path:
            if not self.ready:
                return []
            return [{"id": "list-1", "name": mod.REDIRECT_LIST_NAME, "kind": "redirect"}]

        if path.endswith("/rules/lists/list-1/items?per_page=100"):
            return mod.desired_redirect_items()

        if path.endswith("/rulesets"):
            if not self.ready:
                return []
            if path.startswith("/accounts/"):
                return [{
                    "id": "account-ruleset",
                    "phase": "http_request_redirect",
                    "kind": "root",
                }]
            if path.startswith("/zones/"):
                return [{
                    "id": "zone-ruleset",
                    "phase": "http_config_settings",
                    "kind": "zone",
                }]

        if path.endswith("/rulesets/account-ruleset"):
            return {
                "id": "account-ruleset",
                "phase": "http_request_redirect",
                "kind": "root",
                "rules": [{**mod.desired_redirect_rule(), "id": "redirect-rule-id"}],
            }

        if path.endswith("/rulesets/zone-ruleset"):
            return {
                "id": "zone-ruleset",
                "phase": "http_config_settings",
                "kind": "zone",
                "rules": [{**mod.desired_rum_rule(), "id": "rum-rule-id"}],
            }

        raise AssertionError(f"Unexpected fake request: {method} {path}")


def test_redirect_payload() -> None:
    items = mod.desired_redirect_items()
    assert len(items) == 3
    assert [x["redirect"]["source_url"] for x in items] == [
        "https://www.outpost.com.ua/",
        "https://outpostua.pages.dev/",
        "https://outpost-web.pages.dev/",
    ]
    for item in items:
        redirect = item["redirect"]
        assert redirect["target_url"] == "https://outpost.com.ua/"
        assert redirect["status_code"] == 301
        assert redirect["subpath_matching"] is True
        assert redirect["preserve_path_suffix"] is True
        assert redirect["preserve_query_string"] is True
        assert redirect["include_subdomains"] is False


def test_rum_rule_payload() -> None:
    rule = mod.desired_rum_rule()
    assert rule["ref"] == "outpost_disable_rum"
    assert rule["action"] == "set_config"
    assert rule["expression"] == '(http.host eq "outpost.com.ua")'
    assert rule["action_parameters"] == {"disable_rum": True}
    assert rule["enabled"] is True


def test_redirect_rule_payload() -> None:
    rule = mod.desired_redirect_rule()
    assert rule["ref"] == "outpost_enable_canonical_host_redirects"
    assert rule["action"] == "redirect"
    assert rule["expression"] == "http.request.full_uri in $outpost_production_host_redirects"
    assert rule["action_parameters"] == {
        "from_list": {
            "name": "outpost_production_host_redirects",
            "key": "http.request.full_uri",
        }
    }


def test_empty_account_plan() -> None:
    ctx = mod.ZoneContext(zone_id="zone-id", account_id="account-id", zone_name=mod.ZONE_NAME)
    state = mod.plan_state(FakeClient(False), ctx)
    assert state["redirect_list_exists"] is False
    assert state["redirect_items_match"] is False
    assert state["redirect_rule_match"] is False
    assert state["rum_rule_match"] is False
    assert state["actions"] == [
        {"component": "redirect_list", "action": "create"},
        {"component": "redirect_rule", "action": "create_ruleset_and_rule"},
        {"component": "disable_rum", "action": "create_ruleset_and_rule"},
    ]


def test_ready_account_plan() -> None:
    ctx = mod.ZoneContext(zone_id="zone-id", account_id="account-id", zone_name=mod.ZONE_NAME)
    state = mod.plan_state(FakeClient(True), ctx)
    assert state["redirect_list_exists"] is True
    assert state["redirect_items_match"] is True
    assert state["redirect_rule_match"] is True
    assert state["rum_rule_match"] is True
    assert state["actions"] == []


def main() -> int:
    tests = [
        test_redirect_payload,
        test_rum_rule_payload,
        test_redirect_rule_payload,
        test_empty_account_plan,
        test_ready_account_plan,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Cloudflare edge control offline tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
