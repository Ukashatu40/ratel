"""Static checks on contracts/openapi.yaml: valid OpenAPI plus the Build Plan's conventions.

Each rule is a function over a spec dict so it can be run against the real contract and against
a deliberately broken copy, proving the rule can fail.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from openapi_spec_validator import validate

from tests.contract.helpers import load_contract, operations, resolve

TAGS = {"RatelLink", "RatelMeter"}
EPOCH_FIELDS = {"period_start", "period_end", "started_at", "answered_at", "ended_at", "from", "to"}
SECRET_FIELDS = {"ki", "opc"}


def check_unique_ids_and_tags(spec: dict[str, Any]) -> list[str]:
    ops = operations(spec)
    problems = [
        f"{o.op_id}: tag {o.tag!r} not one of {sorted(TAGS)}" for o in ops if o.tag not in TAGS
    ]
    ids = [o.op_id for o in ops]
    problems += [f"duplicate operationId {i}" for i in set(ids) if ids.count(i) > 1]
    return problems


def check_auth_everywhere(spec: dict[str, Any]) -> list[str]:
    problems = []
    if spec.get("security") != [{"ApiKeyAuth": []}]:
        problems.append("global security must be ApiKeyAuth")
    for o in operations(spec):
        if "security" in o.raw and o.raw["security"] != [{"ApiKeyAuth": []}]:
            problems.append(f"{o.op_id}: overrides global API-key auth")
    scheme = spec["components"]["securitySchemes"]["ApiKeyAuth"]
    if (scheme["type"], scheme["in"], scheme["name"]) != ("apiKey", "header", "Authorization"):
        problems.append("ApiKeyAuth must be an apiKey in the Authorization header")
    return problems


def check_idempotency_on_state_changes(spec: dict[str, Any]) -> list[str]:
    problems = []
    for o in operations(spec):
        if o.method == "GET":
            continue
        params = [resolve(spec, p) for p in o.raw.get("parameters", [])]
        if not any(p.get("in") == "header" and p.get("name") == "Idempotency-Key" for p in params):
            problems.append(f"{o.op_id}: state-changing but no Idempotency-Key header")
    return problems


def check_error_shape(spec: dict[str, Any]) -> list[str]:
    problems = []
    error_schema = spec["components"]["schemas"]["Error"]
    for o in operations(spec):
        for status, resp in o.raw["responses"].items():
            if status.startswith("2"):
                continue
            body = resolve(spec, resp)["content"]["application/json"]["schema"]
            if resolve(spec, body) != error_schema:
                problems.append(f"{o.op_id} {status}: not the standard error shape")
    return problems


def _walk_properties(spec: dict[str, Any], node: Any, seen: set[int] | None = None) -> set[str]:
    seen = seen or set()
    node = resolve(spec, node)
    if id(node) in seen or not isinstance(node, dict):
        return set()
    seen.add(id(node))
    names: set[str] = set()
    for key, child in node.get("properties", {}).items():
        names.add(key)
        names |= _walk_properties(spec, child, seen)
    if "items" in node:
        names |= _walk_properties(spec, node["items"], seen)
    return names


def check_no_secrets_in_responses(spec: dict[str, Any]) -> list[str]:
    problems = []
    for o in operations(spec):
        for status, resp in o.raw["responses"].items():
            content = resolve(spec, resp).get("content", {})
            for media in content.values():
                leaked = _walk_properties(spec, media["schema"]) & SECRET_FIELDS
                if leaked:
                    problems.append(f"{o.op_id} {status}: response exposes {sorted(leaked)}")
    return problems


def check_epoch_fields_are_integers(spec: dict[str, Any]) -> list[str]:
    problems = []

    def is_int(schema: Any) -> bool:
        t = resolve(spec, schema).get("type")
        return t == "integer" or (isinstance(t, list) and set(t) <= {"integer", "null"})

    for name, schema in spec["components"]["schemas"].items():
        for prop, ps in schema.get("properties", {}).items():
            if prop in EPOCH_FIELDS and not is_int(ps):
                problems.append(f"schema {name}.{prop}: epoch seconds must be integer")
    for name, p in spec["components"]["parameters"].items():
        if p["name"] in EPOCH_FIELDS and not is_int(p["schema"]):
            problems.append(f"parameter {name}: epoch seconds must be integer")
    return problems


def check_page_size_cap(spec: dict[str, Any]) -> list[str]:
    problems = []
    for name in ("UsageList", "CallList"):
        records = spec["components"]["schemas"][name]["properties"]["records"]
        if records.get("maxItems") != 5000:
            problems.append(f"{name}.records must cap at 5000 items")
        if "next_cursor" not in spec["components"]["schemas"][name]["properties"]:
            problems.append(f"{name} must have next_cursor")
    return problems


CHECKS = [
    check_unique_ids_and_tags,
    check_auth_everywhere,
    check_idempotency_on_state_changes,
    check_error_shape,
    check_no_secrets_in_responses,
    check_epoch_fields_are_integers,
    check_page_size_cap,
]


def test_contract_is_valid_openapi() -> None:
    validate(load_contract())


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.__name__)
def test_contract_follows_build_plan_conventions(check: Any) -> None:
    assert check(load_contract()) == []


def _mutations() -> dict[str, tuple[Any, Any]]:
    def drop_idempotency(s: dict[str, Any]) -> None:
        s["paths"]["/v1/sims"]["post"]["parameters"] = []

    def leak_ki(s: dict[str, Any]) -> None:
        s["components"]["schemas"]["LineStatus"]["properties"]["ki"] = {"type": "string"}

    def float_time(s: dict[str, Any]) -> None:
        s["components"]["schemas"]["UsageRecord"]["properties"]["period_start"] = {"type": "number"}

    def bad_error(s: dict[str, Any]) -> None:
        s["components"]["responses"]["NotFound"]["content"]["application/json"]["schema"] = {
            "type": "object"
        }

    def open_endpoint(s: dict[str, Any]) -> None:
        s["paths"]["/v1/assignments"]["get"]["security"] = []

    return {
        "drop_idempotency": (drop_idempotency, check_idempotency_on_state_changes),
        "leak_ki": (leak_ki, check_no_secrets_in_responses),
        "float_time": (float_time, check_epoch_fields_are_integers),
        "bad_error": (bad_error, check_error_shape),
        "open_endpoint": (open_endpoint, check_auth_everywhere),
    }


@pytest.mark.parametrize("name", sorted(_mutations()))
def test_each_rule_fails_on_a_broken_contract(name: str) -> None:
    mutate, check = _mutations()[name]
    broken = copy.deepcopy(load_contract())
    mutate(broken)
    assert check(broken), f"{check.__name__} did not catch mutation {name}"
