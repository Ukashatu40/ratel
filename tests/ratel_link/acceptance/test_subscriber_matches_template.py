"""Build Plan, RatelLink "Done when": the document RatelLink writes matches the template field for
field, apart from its own values.

Runs against the synthetic template always, and against the network team's real export when
`RATEL_LINK_TEMPLATE_COMPARE_FILE` names it (a working subscriber with the `ims` session, keys left
out, kept outside the repository; N1 in docs/RATELCORE_INTEGRATION_FACTS.md). The same comparison
also runs on a real MongoDB, on the types the database stores.
"""

from __future__ import annotations

import copy
import os
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from bson import Int64, json_util
from pydantic import SecretStr
from pymongo import MongoClient

from ratel_link.domain.subscriber import activation_fields, speed_from_mbps
from ratel_link.repositories.mongo import MongoSubscriberRepository
from tests.ratel_link.acceptance.document_comparison import (
    bson_type,
    differences,
    synthetic_template,
)
from tests.ratel_link.fakes import InMemorySubscriberRepository
from tests.synthetic import (
    SYNTHETIC_IMSI,
    SYNTHETIC_KI_HEX,
    SYNTHETIC_MSISDN,
    SYNTHETIC_OPC_HEX,
)

TEMPLATE_ENV = "RATEL_LINK_TEMPLATE_COMPARE_FILE"


def _templates() -> list[Any]:
    found: list[Any] = [pytest.param(synthetic_template, id="synthetic")]
    real = os.environ.get(TEMPLATE_ENV)
    if real:
        found.append(
            pytest.param(lambda: json_util.loads(Path(real).read_text()), id="network-export")
        )
    return found


def _written(template: dict[str, Any], *, voice: bool = True, **changes: Any) -> dict[str, Any]:
    """The document activation creates, for a line whose ims session comes from `template`."""
    ims = next(s for s in template["slice"][0]["session"] if s["name"] == "ims")
    arguments: dict[str, Any] = {
        "msisdn": SYNTHETIC_MSISDN,
        "ki": SecretStr(SYNTHETIC_KI_HEX),
        "opc": SecretStr(SYNTHETIC_OPC_HEX),
        "upload": speed_from_mbps(5),
        "download": speed_from_mbps(10),
        "voice": voice,
        "ue_ip": "10.45.0.2",
        "ims_session": ims,
    }
    arguments.update(changes)
    fields = activation_fields(**arguments)
    repository = InMemorySubscriberRepository()
    repository.upsert_line(SYNTHETIC_IMSI, fields.owned, fields.created_only)
    return repository.documents[SYNTHETIC_IMSI]


@pytest.fixture(params=_templates())
def template(request: pytest.FixtureRequest) -> dict[str, Any]:
    return request.param()  # type: ignore[no-any-return]


def test_the_document_activation_writes_matches_the_template(template: dict[str, Any]) -> None:
    assert differences(_written(template), template) == []


def test_a_different_plan_and_number_are_only_own_values(template: dict[str, Any]) -> None:
    other = _written(
        template,
        msisdn="2349999999999",
        upload=speed_from_mbps(0.256),
        download=speed_from_mbps(1.5),
        ue_ip="10.45.7.8",
    )
    assert differences(other, template) == []


def test_without_voice_the_only_difference_is_the_missing_ims_session(
    template: dict[str, Any],
) -> None:
    report = differences(_written(template, voice=False, ims_session=None), template)
    assert report == ["slice.0.session: 1 entries, template has 2"]


def test_the_voice_rules_are_the_templates_exactly(template: dict[str, Any]) -> None:
    mine = _written(template)
    ims_before = copy.deepcopy(
        next(s for s in template["slice"][0]["session"] if s["name"] == "ims")
    )
    ims_after = mine["slice"][0]["session"][1]
    assert ims_after == ims_before  # nothing edited, nothing added
    assert "ue" not in ims_after


@pytest.fixture
def stored_by_mongodb() -> Iterator[Any]:
    uri = os.environ.get("RATEL_TEST_MONGO_URI")
    if not uri:
        pytest.skip("RATEL_TEST_MONGO_URI is not set")
    client: MongoClient[Any] = MongoClient(uri, serverSelectionTimeoutMS=5000)
    database = client[f"open5gs_template_{secrets.token_hex(3)}"]
    try:
        yield database
    finally:
        client.drop_database(database.name)
        client.close()


@pytest.mark.integration
def test_the_document_as_mongodb_stores_it_matches_the_template(
    template: dict[str, Any], stored_by_mongodb: Any
) -> None:
    """The types that matter are the ones the database holds, not the ones Python meant."""
    fields = activation_fields(
        msisdn=SYNTHETIC_MSISDN,
        ki=SecretStr(SYNTHETIC_KI_HEX),
        opc=SecretStr(SYNTHETIC_OPC_HEX),
        upload=speed_from_mbps(5),
        download=speed_from_mbps(10),
        voice=True,
        ue_ip="10.45.0.2",
        ims_session=next(s for s in template["slice"][0]["session"] if s["name"] == "ims"),
    )
    MongoSubscriberRepository(stored_by_mongodb).upsert_line(
        SYNTHETIC_IMSI, fields.owned, fields.created_only
    )
    stored = stored_by_mongodb["subscribers"].find_one({"imsi": SYNTHETIC_IMSI}, {"_id": 0})
    assert stored is not None
    assert differences(stored, template) == []


# --- the comparison itself must be able to fail ------------------------------------------------


def _mutated(template: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    document = _written(template)
    node: Any = document
    *parents, last = path.split(".")
    for part in parents:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if isinstance(node, list):
        node[int(last)] = value
    elif value is _REMOVE:
        del node[last]
    else:
        node[last] = value
    return document


_REMOVE = object()

BREAKS = [
    ("an integer as a double", "network_access_mode", 2.0, "network_access_mode: type"),
    ("an integer as a string", "subscribed_rau_tau_timer", "12", "subscribed_rau_tau_timer"),
    ("an integer as int64", "access_restriction_data", Int64(32), "access_restriction_data"),
    ("a wrong constant", "network_access_mode", 0, "network_access_mode: value differs"),
    ("amf changed", "security.amf", "0000", "security.amf: value differs"),
    ("op instead of null", "security.op", "A" * 32, "security.op"),
    ("sqn written", "security.sqn", Int64(1), "security.sqn: RatelLink must never write this"),
    ("a field left out", "subscriber_status", _REMOVE, "subscriber_status: missing"),
    ("an extra field", "surprise", 1, "surprise: extra"),
    ("msisdn not an array", "msisdn", "2340000000001", "msisdn: type"),
    ("a speed as a double", "ambr.downlink.value", 10.0, "ambr.downlink.value: type"),
    ("internet not first", "slice.0.session.0.name", "ims", "slice.0.session.0.name: value"),
    ("wrong QCI", "slice.0.session.0.qos.index", 8, "slice.0.session.0.qos.index: value"),
    ("voice rules edited", "slice.0.session.1.pcc_rule.0.qos.index", 9, "pcc_rule.0.qos.index"),
    ("a fixed address on ims", "slice.0.session.1.ue", {"ipv4": "10.46.0.9"}, "session.1.ue"),
    ("hss array not created", "imeisv", "x", "imeisv: must be created as an empty array"),
]  # fmt: skip


@pytest.mark.parametrize(("what", "path", "value", "expected"), BREAKS, ids=[b[0] for b in BREAKS])
def test_the_comparison_catches(what: str, path: str, value: Any, expected: str) -> None:
    template = synthetic_template()
    report = differences(_mutated(template, path, value), template)
    assert any(expected in line for line in report), (what, report)


def test_a_report_names_paths_and_types_never_values() -> None:
    template = synthetic_template()
    report = differences(_mutated(template, "security.op", SYNTHETIC_KI_HEX), template)
    assert report and not any(
        SYNTHETIC_KI_HEX in line or SYNTHETIC_KI_HEX.upper() in line for line in report
    )


def test_bson_types_are_told_apart() -> None:
    assert [bson_type(v) for v in (1, 2**31, Int64(1), 1.0, True, None, "x", [], {})] == [
        "int32",
        "int64",
        "int64",
        "double",
        "bool",
        "null",
        "string",
        "array",
        "object",
    ]
