"""Identifiers used across RatelLink: an IMSI and the id of a calling system. Pure, no I/O."""

from __future__ import annotations

import re

IMSI_PATTERN = r"^[0-9]{15}$"  # same pattern as the contract's Imsi schema


_IMSI_RE = re.compile(IMSI_PATTERN)

# A phone number as the core stores it and as the voice layer looks it up: 234 and ten digits, no
# plus sign (see docs/RATELCORE_INTEGRATION_FACTS.md).
# A line stored in any other form cannot be called.
MSISDN_PATTERN = r"^234[0-9]{10}$"


# Stable internal id of a calling system, for example `bss-app`. Not secret. A token such as
# `rlk_bss-app.<secret>` does not match, so one cannot be passed off as an id by mistake.
API_KEY_ID_PATTERN = r"[a-z][a-z0-9-]{2,31}"


_API_KEY_ID_RE = re.compile(API_KEY_ID_PATTERN)


def is_api_key_id(value: object) -> bool:
    return isinstance(value, str) and _API_KEY_ID_RE.fullmatch(value) is not None


_MSISDN_RE = re.compile(MSISDN_PATTERN)


def is_msisdn(value: object) -> bool:
    return isinstance(value, str) and _MSISDN_RE.fullmatch(value) is not None


def is_imsi(value: object) -> bool:
    return isinstance(value, str) and _IMSI_RE.fullmatch(value) is not None
