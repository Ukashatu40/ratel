"""Prepaid control of calls and SMS: the rules (ADR 0013, decided by the project lead 2026-11-26).

Pure: no database, no clock, no logging. Money is whole kobo; rates and prices include VAT.

- A call is limited to what the caller's available airtime buys at the call's rate, at most
  MAX_CALL_SECONDS. Less than MIN_CALL_SECONDS of airtime refuses it.
- Emergency and free numbers (112, 199, customer care: a deployment setting) are never refused or
  limited. Neither are calls while charging is off, nor callers that are not a line in RatelBSS
  (lab SIMs provisioned straight into the HSS; every customer line comes through RatelBSS).
- An SMS to another Ratelplus line costs the catalogue's SMS price; to the self-care number 555
  it is free; to anything else (other networks, other short codes) it is refused and not charged,
  as there is no SMS interconnect.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

SECONDS_PER_MINUTE = 60
MIN_CALL_SECONDS = 10
MAX_CALL_SECONDS = 3 * 60 * 60
# An open reservation nobody settled stops counting this long after its limit would have ended.
RESERVATION_GRACE_SECONDS = 15 * 60
SELF_CARE_NUMBER = "555"


class CallReason(StrEnum):
    CHARGING_OFF = "charging_off"
    FREE_NUMBER = "free_number"
    NOT_BILLED = "not_billed"  # the caller is not a line in RatelBSS
    LIMITED = "limited"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    LINE_NOT_IN_SERVICE = "line_not_in_service"


@dataclass(frozen=True)
class CallDecision:
    allowed: bool
    max_seconds: int  # 0: no limit
    reason: CallReason


class SmsOutcome(StrEnum):
    CHARGED = "charged"
    FREE_SELF_CARE = "free_self_care"  # to 555
    FREE_CHARGING_OFF = "free_charging_off"
    NOT_BILLED = "not_billed"  # the sender is not a line in RatelBSS
    REFUSED_BALANCE = "refused_balance"
    REFUSED_OFF_NET = "refused_off_net"
    REFUSED_NOT_IN_SERVICE = "refused_not_in_service"

    @property
    def send(self) -> bool:
        return not self.value.startswith("refused_")


def digits(number: str) -> str:
    """The digits of a dialled number or URI user part: 'tel:+234 80...' gives '23480...'."""
    value = number.strip()
    for prefix in ("tel:", "sip:", "sips:"):
        if value.lower().startswith(prefix):
            value = value[len(prefix) :]
    value = value.split("@", 1)[0].split(";", 1)[0]
    return "".join(ch for ch in value if ch.isdigit())


def parse_free_numbers(setting: str) -> frozenset[str]:
    """'112, 199, 0700...' as the set of their digits. Empty entries are ignored."""
    return frozenset(d for d in (digits(part) for part in setting.split(",")) if d)


def is_free_number(dialled: str, free: frozenset[str]) -> bool:
    return digits(dialled) in free


def affordable_seconds(available_kobo: int, rate_kobo_per_min: int) -> int:
    """Whole seconds `available_kobo` buys at the rate, at most MAX_CALL_SECONDS."""
    if available_kobo <= 0:
        return 0
    if rate_kobo_per_min <= 0:
        return MAX_CALL_SECONDS
    return min(available_kobo * SECONDS_PER_MINUTE // rate_kobo_per_min, MAX_CALL_SECONDS)


def cost_of(seconds: int, rate_kobo_per_min: int) -> int:
    """What `seconds` cost at the rate, rounded up to a whole kobo (as the call charge is)."""
    if seconds <= 0 or rate_kobo_per_min <= 0:
        return 0
    return -(-seconds * rate_kobo_per_min // SECONDS_PER_MINUTE)


def limited_call(available_kobo: int, rate_kobo_per_min: int) -> tuple[CallDecision, int]:
    """The decision for a billed caller, and the kobo to reserve for it."""
    seconds = affordable_seconds(available_kobo, rate_kobo_per_min)
    if seconds < MIN_CALL_SECONDS:
        return CallDecision(False, 0, CallReason.INSUFFICIENT_BALANCE), 0
    return CallDecision(True, seconds, CallReason.LIMITED), cost_of(seconds, rate_kobo_per_min)
