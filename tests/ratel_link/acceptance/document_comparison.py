"""Compare a subscriber document RatelLink wrote with a document the core made or accepts.

Build Plan, RatelLink "Done when": the Open5GS document "matches the template field for field,
apart from its own values". Field for field means the same fields, the same BSON types, and the
same values wherever a value is not the line's own. The type matters as much as the name: a double
where the core expects int32 can be read as 0 (Integration Guide, section 6).

Tests only. The template is a document the network team exported from a working subscriber, with
the keys left out (docs/RATELCORE_INTEGRATION_FACTS.md, N1), or the synthetic one below.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from fnmatch import fnmatchcase
from typing import Any

from bson import Int64

# Values that belong to the line. They must be present with the right type; the value may differ.
OWN_VALUES = (
    "imsi",
    "msisdn.*",
    "security.k",
    "security.opc",
    "ambr.*.*",
    "slice.0.session.0.ambr.*.*",
    "slice.0.session.0.ue.ipv4",
)

# What the HSS keeps in the document. RatelLink creates the arrays empty and never writes them
# again, so only the container type is compared; the template has them filled in by a real attach.
HSS_OWNED = ("imeisv", "mme_host", "mme_realm", "mm_realm", "mme_timestamp", "purge_flag")

# Present in a document that has attached, left out on create, never written by RatelLink.
NEVER_WRITTEN = ("security.sqn",)

# May be present or absent without making the documents differ.
OPTIONAL = ("slice.0.session.0.ue", "slice.0.session.0.ue.ipv4")

# The voice session is copied from the template unchanged, so it is compared value for value.
# (Its `ue` is the one thing taken out, and is optional above.)


def bson_type(value: Any) -> str:
    """The BSON type a value will be stored as."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, Int64):
        return "int64"
    if isinstance(value, int):
        return "int32" if -(2**31) <= value < 2**31 else "int64"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list | tuple):
        return "array"
    return type(value).__name__


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def differences(
    ours: Mapping[str, Any],
    template: Mapping[str, Any],
    *,
    own_values: tuple[str, ...] = OWN_VALUES,
    hss_owned: tuple[str, ...] = HSS_OWNED,
    never_written: tuple[str, ...] = NEVER_WRITTEN,
    optional: tuple[str, ...] = OPTIONAL,
) -> list[str]:
    """Every way `ours` differs from `template`, as readable lines. Empty means a match.

    Lines name paths and types, never values, so a report cannot carry a key.
    """
    found: list[str] = []

    def walk(mine: Any, theirs: Any, path: str) -> None:
        if _matches(path, never_written):
            if mine is not None:
                found.append(f"{path}: RatelLink must never write this")
            return
        if path in hss_owned:
            if bson_type(mine) != "array":
                found.append(f"{path}: must be created as an empty array, is {bson_type(mine)}")
            return
        if bson_type(mine) != bson_type(theirs):
            found.append(f"{path}: type {bson_type(mine)}, template has {bson_type(theirs)}")
            return
        if isinstance(theirs, Mapping):
            for key in sorted(set(mine) | set(theirs)):
                child = f"{path}.{key}" if path else key
                if key not in mine:
                    if not _matches(child, optional + never_written):
                        found.append(f"{child}: missing, the template has it")
                elif key not in theirs:
                    if not _matches(child, optional):
                        found.append(f"{child}: extra, the template does not have it")
                else:
                    walk(mine[key], theirs[key], child)
        elif isinstance(theirs, list):
            if len(mine) != len(theirs):
                found.append(f"{path}: {len(mine)} entries, template has {len(theirs)}")
                return
            for index, (a, b) in enumerate(zip(mine, theirs, strict=True)):
                walk(a, b, f"{path}.{index}")
        elif not _matches(path, own_values) and mine != theirs:
            found.append(f"{path}: value differs from the template")

    walk(dict(ours), dict(template), "")
    return found


def synthetic_template() -> dict[str, Any]:
    """A subscriber as the core holds it after the phone has attached, written from the Integration
    Guide's example document (section 4) and the HSS's fields, not from RatelLink's own builder.
    Synthetic values only. The voice rules are invented, as in tests/synthetic.py."""
    from tests.synthetic import SYNTHETIC_IMS_SESSION, SYNTHETIC_KI_HEX, SYNTHETIC_OPC_HEX

    ims = copy.deepcopy(SYNTHETIC_IMS_SESSION)
    del ims["ue"]
    return {
        "schema_version": 1,
        "imsi": "621002064730042",
        "msisdn": ["2342064730042"],
        "imeisv": ["3540000000000001"],
        "mme_host": ["mme.example.invalid"],
        "mme_realm": ["realm.example.invalid"],
        "mm_realm": ["realm.example.invalid"],
        "mme_timestamp": Int64(1760000000),
        "purge_flag": [],
        "security": {
            "k": SYNTHETIC_KI_HEX.upper(),
            "opc": SYNTHETIC_OPC_HEX.upper(),
            "op": None,
            "amf": "8000",
            "sqn": Int64(123456789012),
        },
        "ambr": {"downlink": {"value": 10, "unit": 2}, "uplink": {"value": 5, "unit": 2}},
        "slice": [
            {
                "sst": 1,
                "default_indicator": True,
                "session": [
                    {
                        "name": "internet",
                        "type": 3,
                        "qos": {
                            "index": 9,
                            "arp": {
                                "priority_level": 8,
                                "pre_emption_capability": 1,
                                "pre_emption_vulnerability": 2,
                            },
                        },
                        "ambr": {
                            "downlink": {"value": 10, "unit": 2},
                            "uplink": {"value": 5, "unit": 2},
                        },
                        "pcc_rule": [],
                    },
                    ims,
                ],
            }
        ],
        "subscriber_status": 0,
        "operator_determined_barring": 0,
        "access_restriction_data": 32,
        "network_access_mode": 2,
        "subscribed_rau_tau_timer": 12,
        "__v": 0,
    }
