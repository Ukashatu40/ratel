"""The Open5GS subscriber document: units, types, order, and what must never be written."""

from __future__ import annotations

import copy
import math
from typing import Any

import pytest
from pydantic import SecretStr

from ratel_link.domain.subscriber import (
    MAX_SPEED_MBPS,
    SpeedError,
    VoiceTemplateError,
    activation_fields,
    ims_session_from_template,
    internet_session,
    speed_from_mbps,
)
from tests.synthetic import (
    SYNTHETIC_IMS_SESSION,
    SYNTHETIC_KI_HEX,
    SYNTHETIC_MSISDN,
    SYNTHETIC_OPC_HEX,
)

KI, OPC = SecretStr(SYNTHETIC_KI_HEX), SecretStr(SYNTHETIC_OPC_HEX)


# --- speeds -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mbps", "value", "unit"),
    [
        (10, 10, 2),  # whole Mbps stays Mbps
        (10.0, 10, 2),
        (1.5, 1500, 1),  # the guide's own example
        (0.128, 128, 1),
        (0.001, 1, 1),
        (0.0005, 500, 0),  # not a whole Kbps, so bits per second
        (0.000001, 1, 0),
        (10_000, 10_000, 2),
        (0.1 + 0.2, 300, 1),  # 0.30000000000000004: float noise must not be refused
        (3.85, 3850, 1),
    ],
)
def test_a_speed_becomes_whole_numbers_in_the_largest_unit_that_fits(
    mbps: float, value: int, unit: int
) -> None:
    speed = speed_from_mbps(mbps)
    assert (speed.value, speed.unit) == (value, unit)
    assert type(speed.value) is int and type(speed.unit) is int


@pytest.mark.parametrize(
    "bad",
    [
        *(0, 0.0, -1, -0.001, math.nan, math.inf, -math.inf, True, False, "10", None),
        *(10_000.001, 1.23456789, 0.0000005, 1e-9, 1e30, 2**40),
    ],
)
def test_a_speed_that_cannot_be_written_whole_is_refused(bad: Any) -> None:
    with pytest.raises(SpeedError):
        speed_from_mbps(bad)


def test_a_refused_speed_message_never_contains_the_value() -> None:
    with pytest.raises(SpeedError) as caught:
        speed_from_mbps(1.23456789)
    assert "1.2345" not in str(caught.value)


def test_every_accepted_speed_fits_an_int32_in_its_unit() -> None:
    for mbps in (MAX_SPEED_MBPS, 9999.999, 0.000001, 1234.567):
        assert 1 <= speed_from_mbps(mbps).value <= 2**31 - 1


# --- the document -----------------------------------------------------------------------------


def _fields(voice: bool = True, ims: Any = "default") -> Any:
    return activation_fields(
        msisdn=SYNTHETIC_MSISDN,
        ki=KI,
        opc=OPC,
        upload=speed_from_mbps(5),
        download=speed_from_mbps(10),
        voice=voice,
        ue_ip="10.45.0.2",
        ims_session=ims_session_from_template({"slice": [{"session": [SYNTHETIC_IMS_SESSION]}]})
        if ims == "default"
        else ims,
    )


def _walk(value: Any) -> Any:
    """Every scalar inside nested dicts and lists."""
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)
    else:
        yield value


def test_no_number_in_the_document_is_a_float() -> None:
    # The core reads a double where it expects int32 as 0, so one float would silently break a line.
    fields = _fields()
    for part in (fields.owned, fields.created_only):
        for scalar in _walk(part):
            assert not isinstance(scalar, float), scalar


def test_the_integers_are_the_values_the_guide_lists() -> None:
    owned = _fields().owned
    assert (
        owned["subscriber_status"],
        owned["operator_determined_barring"],
        owned["access_restriction_data"],
        owned["network_access_mode"],
    ) == (0, 0, 32, 2)
    assert all(type(owned[k]) is int for k in ("subscriber_status", "network_access_mode"))


def test_keys_are_written_in_upper_case_and_op_is_null() -> None:
    owned = _fields().owned
    assert owned["security.k"] == SYNTHETIC_KI_HEX.upper()
    assert owned["security.opc"] == SYNTHETIC_OPC_HEX.upper()
    assert owned["security.op"] is None
    assert owned["security.amf"] == "8000"


def test_the_sequence_number_is_never_written() -> None:
    fields = _fields()
    every_path = {*fields.owned, *fields.created_only}
    assert not any("sqn" in path for path in every_path)
    assert "security" not in every_path  # only named sub-paths, so a whole object is never replaced


def test_the_msisdn_is_a_one_item_array_in_the_stored_form() -> None:
    assert _fields().owned["msisdn"] == [SYNTHETIC_MSISDN]


def test_the_internet_session_is_first_and_the_voice_session_second() -> None:
    sessions = _fields().owned["slice"][0]["session"]
    assert [s["name"] for s in sessions] == ["internet", "ims"]


def test_without_voice_there_is_only_the_internet_session() -> None:
    sessions = _fields(voice=False, ims=None).owned["slice"][0]["session"]
    assert [s["name"] for s in sessions] == ["internet"]


def test_the_internet_session_carries_the_fixed_address_and_the_plan_speeds() -> None:
    internet = _fields().owned["slice"][0]["session"][0]
    assert internet["ue"] == {"ipv4": "10.45.0.2"}
    assert internet["ambr"] == {
        "downlink": {"value": 10, "unit": 2},
        "uplink": {"value": 5, "unit": 2},
    }
    assert (internet["type"], internet["qos"]["index"]) == (3, 9)
    assert internet["pcc_rule"] == []


def test_the_top_level_speed_is_the_plan_speed() -> None:
    owned = _fields().owned
    assert owned["ambr"] == owned["slice"][0]["session"][0]["ambr"]


def test_a_voice_session_that_arrives_with_an_address_loses_it() -> None:
    # Even if a template source forgot to clean it: the builder is the last line of defence.
    ims = _fields(ims=copy.deepcopy(SYNTHETIC_IMS_SESSION)).owned["slice"][0]["session"][1]
    assert "ue" not in ims


def test_the_voice_session_has_no_fixed_address() -> None:
    ims = _fields().owned["slice"][0]["session"][1]
    assert "ue" not in ims
    assert ims["pcc_rule"] == SYNTHETIC_IMS_SESSION["pcc_rule"]  # the voice rules, copied exactly


def test_fields_the_hss_owns_are_only_created_never_set_on_update() -> None:
    fields = _fields()
    for name in ("imeisv", "mme_host", "mm_realm", "mme_timestamp", "purge_flag"):
        assert fields.created_only[name] == []
        assert name not in fields.owned
    assert fields.created_only["schema_version"] == 1
    assert fields.created_only["subscribed_rau_tau_timer"] == 12


def test_owned_and_created_only_never_share_a_path() -> None:
    # MongoDB refuses an update that touches one path twice, and the split must stay clean.
    fields = _fields()
    for mine in fields.owned:
        for theirs in fields.created_only:
            nested = mine.startswith(theirs + ".") or theirs.startswith(mine + ".")
            assert mine != theirs and not nested


def test_voice_without_a_template_is_refused() -> None:
    with pytest.raises(VoiceTemplateError):
        _fields(voice=True, ims=None)


def test_printing_the_fields_shows_no_key() -> None:
    fields = _fields()
    for text in (repr(fields), str(fields), f"{fields}", f"{fields!r}"):
        assert SYNTHETIC_KI_HEX.upper() not in text and SYNTHETIC_OPC_HEX.upper() not in text
        assert SYNTHETIC_KI_HEX not in text and SYNTHETIC_OPC_HEX not in text


def test_building_the_fields_does_not_change_the_template() -> None:
    template = copy.deepcopy(SYNTHETIC_IMS_SESSION)
    fields = _fields(ims=ims_session_from_template({"slice": [{"session": [template]}]}))
    fields.owned["slice"][0]["session"][1]["pcc_rule"].clear()
    assert template == SYNTHETIC_IMS_SESSION


def test_the_internet_session_helper_copies_its_speeds() -> None:
    ambr = {"downlink": {"value": 1, "unit": 2}, "uplink": {"value": 1, "unit": 2}}
    session = internet_session(ambr, "10.45.0.9")
    session["ambr"]["downlink"]["value"] = 99
    assert ambr["downlink"]["value"] == 1


# --- the voice template -----------------------------------------------------------------------


def _template(*sessions: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {**(extra or {}), "slice": [{"session": list(sessions)}]}


def test_the_ims_session_is_taken_from_an_exported_document() -> None:
    internet = {"name": "internet", "type": 3}
    ims = ims_session_from_template(_template(internet, SYNTHETIC_IMS_SESSION))
    assert ims["name"] == "ims" and "ue" not in ims
    assert ims["pcc_rule"] == SYNTHETIC_IMS_SESSION["pcc_rule"]


def test_everything_else_in_the_export_is_ignored_including_keys() -> None:
    leftover = {"security": {"k": "SHOULD-NEVER-BE-READ", "opc": "SHOULD-NEVER-BE-READ"}}
    ims = ims_session_from_template(_template(SYNTHETIC_IMS_SESSION, extra=leftover))
    assert "SHOULD-NEVER-BE-READ" not in repr(ims)
    assert "security" not in ims


def test_the_extracted_session_is_a_copy() -> None:
    export = _template(copy.deepcopy(SYNTHETIC_IMS_SESSION))
    ims = ims_session_from_template(export)
    ims["pcc_rule"].clear()
    assert export["slice"][0]["session"][0]["pcc_rule"] != []


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"slice": []},
        {"slice": "nope"},
        {"slice": [{"session": []}]},
        {"slice": [{"session": [{"name": "internet"}]}]},  # no ims session
        {"slice": [{"session": [SYNTHETIC_IMS_SESSION, SYNTHETIC_IMS_SESSION]}]},  # two of them
        {"slice": [{"session": [{"name": "ims", "pcc_rule": []}]}]},  # no voice rules
        {"slice": [{"session": [{"name": "ims"}]}]},
        {"slice": [{"session": [{"name": "ims", "pcc_rule": "x"}]}]},
        {"slice": ["x", 1, None]},
    ],
)
def test_an_unusable_template_is_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(VoiceTemplateError):
        ims_session_from_template(bad)
