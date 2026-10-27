"""The Open5GS subscriber document RatelLink writes into RatelCore. Pure, no I/O.

Everything here follows the network team's RatelLink Developer Integration Guide (11 Oct 2026),
summarised without addresses in docs/RATELCORE_INTEGRATION_FACTS.md. The rules that matter:

- an existing document is never replaced, only changed with `$set` on named paths, because the HSS
  writes `sqn`, `imeisv`, `mme_host`, `mme_realm`, `mme_timestamp` and `purge_flag` into it;
- `security.sqn` is never written;
- every integer is a Python `int` (stored as int32), never a float, and keys are strings;
- the `internet` session is always first in the session list;
- the voice (`ims`) session comes from a template exported from the lab, never from this file.

The documents built here hold Ki and OPc. They are wrapped so that printing them shows nothing.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import SecretStr

INTERNET = "internet"
IMS = "ims"

# Speed units in the subscriber document: 0 bps, 1 Kbps, 2 Mbps, 3 Gbps, 4 Tbps.
UNIT_BPS, UNIT_KBPS, UNIT_MBPS = 0, 1, 2
MAX_INT32 = 2**31 - 1

# TODO(project lead): the Build Plan gives no maximum. This is a sanity limit (10 Gbit/s) so that a
# typing mistake cannot become a plan, and it keeps every value inside int32 in any unit.
MAX_SPEED_MBPS = 10_000

_WHOLE = Decimal("1e-9")  # how far from a whole number still counts as whole (float noise only)


class SpeedError(ValueError):
    """A speed that cannot be written as a whole number in one of the core's units."""


@dataclass(frozen=True, slots=True)
class Speed:
    value: int
    unit: int

    def to_document(self) -> dict[str, int]:
        return {"value": self.value, "unit": self.unit}


def speed_from_mbps(mbps: float) -> Speed:
    """Convert a plan speed in Mbit/s to the core's `{value, unit}`.

    The core wants whole numbers, so 10 becomes 10 Mbps and 1.5 becomes 1500 Kbps. A speed that is
    not a whole number of bits per second, is zero or negative, or is larger than MAX_SPEED_MBPS is
    refused. The message never contains the value.
    """
    if isinstance(mbps, bool) or not isinstance(mbps, int | float) or not math.isfinite(mbps):
        raise SpeedError("speed must be a finite number")
    if not 0 < mbps <= MAX_SPEED_MBPS:
        raise SpeedError("speed is outside the allowed range")
    exact = Decimal(repr(mbps))  # repr gives the shortest text that round-trips: 0.3 stays 0.3
    for unit, per_mbps in ((UNIT_MBPS, 1), (UNIT_KBPS, 1_000), (UNIT_BPS, 1_000_000)):
        scaled = exact * per_mbps
        whole = scaled.to_integral_value()
        if abs(scaled - whole) <= _WHOLE and 1 <= whole <= MAX_INT32:
            return Speed(int(whole), unit)
    raise SpeedError("speed must be a whole number of bits per second")


def ambr_document(upload: Speed, download: Speed) -> dict[str, dict[str, int]]:
    return {"downlink": download.to_document(), "uplink": upload.to_document()}


# The internet session is IPv4 only (Open5GS session type 1). Usage is counted per IPv4 address
# on core-up (deploy/core-up/ratel-meter.nft); an IPv4v6 session (type 3) would let IPv6 traffic
# through uncounted. The core was changed to IPv4 only on 2026-10-22 (SMF, UPF, ogstun). Do not
# change this without counting IPv6 first.
INTERNET_SESSION_TYPE = 1


def internet_session(ambr: Mapping[str, Any], ue_ip: str) -> dict[str, Any]:
    """The data session: QCI 9, ARP 8, the plan speeds, and the line's fixed address."""
    return {
        "name": INTERNET,
        "type": INTERNET_SESSION_TYPE,
        "qos": {
            "index": 9,
            "arp": {
                "priority_level": 8,
                "pre_emption_capability": 1,
                "pre_emption_vulnerability": 2,
            },
        },
        "ambr": copy.deepcopy(dict(ambr)),
        "ue": {"ipv4": ue_ip},
        "pcc_rule": [],
    }


class VoiceTemplateError(ValueError):
    """The voice template is unusable. The message names the problem, never the content."""


def ims_session_from_template(template: Mapping[str, Any]) -> dict[str, Any]:
    """Take the `ims` session out of a subscriber document exported from the lab.

    The voice rules (`pcc_rule`) and the QCI 5 settings are the network team's and must not be
    edited, so they are copied exactly. Only the fixed-address field is removed: the guide says the
    `ims` session never gets `ue.ipv4`. Anything else in the exported document, including keys if
    someone left them in, is ignored and never read.
    """
    sessions: list[Mapping[str, Any]] = []
    slices = template.get("slice")
    if isinstance(slices, list):
        for one_slice in slices:
            found = one_slice.get("session") if isinstance(one_slice, Mapping) else None
            if isinstance(found, list):
                sessions.extend(s for s in found if isinstance(s, Mapping) and s.get("name") == IMS)
    if len(sessions) != 1:
        raise VoiceTemplateError("the template must contain exactly one session named ims")
    ims = copy.deepcopy(dict(sessions[0]))
    ims.pop("ue", None)
    rules = ims.get("pcc_rule")
    if not isinstance(rules, list) or not rules:
        raise VoiceTemplateError("the ims session in the template has no pcc_rule entries")
    return ims


@dataclass(frozen=True, slots=True, repr=False)
class SubscriberFields:
    """What activation writes.

    `owned` is set on create and on update, `created_only` only on create.

    `owned` holds the plaintext Ki and OPc, so printing this object shows nothing.
    """

    owned: dict[str, Any]
    created_only: dict[str, Any]

    def __repr__(self) -> str:
        return "SubscriberFields(<redacted>)"

    __str__ = __repr__


def activation_fields(
    *,
    msisdn: str,
    ki: SecretStr,
    opc: SecretStr,
    upload: Speed,
    download: Speed,
    voice: bool,
    ue_ip: str,
    ims_session: Mapping[str, Any] | None,
) -> SubscriberFields:
    """The fields RatelLink owns, plus the ones it creates once and then leaves to the HSS."""
    ambr = ambr_document(upload, download)
    sessions = [internet_session(ambr, ue_ip)]
    if voice:
        if ims_session is None:
            raise VoiceTemplateError("voice was requested but there is no ims template")
        ims = copy.deepcopy(dict(ims_session))
        ims.pop("ue", None)  # the ims session never gets a fixed address, whatever the source says
        sessions.append(ims)
    owned: dict[str, Any] = {
        "msisdn": [msisdn],
        "security.k": ki.get_secret_value().upper(),
        "security.opc": opc.get_secret_value().upper(),
        "security.op": None,
        "security.amf": "8000",
        "ambr": ambr,
        "slice": [{"sst": 1, "default_indicator": True, "session": sessions}],
        "subscriber_status": 0,
        "operator_determined_barring": 0,
        "access_restriction_data": 32,
        "network_access_mode": 2,
    }
    created_only: dict[str, Any] = {
        "schema_version": 1,
        "imeisv": [],
        "mme_host": [],
        # Open5GS names this field `mme_realm` (the HSS writes it at attach). The guide's `mm_realm`
        # is not an Open5GS field, but the working documents carry both, so both are created to
        # match them field for field. TODO(network team): can `mm_realm` be dropped?
        "mme_realm": [],
        "mm_realm": [],
        "mme_timestamp": [],
        "purge_flag": [],
        "subscribed_rau_tau_timer": 12,
        "__v": 0,
    }
    return SubscriberFields(owned=owned, created_only=created_only)
