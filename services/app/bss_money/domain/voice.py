"""What a voice call costs. Pure: no database, no clock, no logging.

Decided by the project lead on 2026-11-24 (docs/catalogue.md): calls are paid from airtime, per
second, at the on-net rate when the other party is a Ratelplus number and the off-net rate
otherwise. Only answered calls cost anything; the time counted is from the answer to the end.

The charge is taken after the call ends (from its call record). A call is not refused while it is
running when the wallet is empty: that needs online charging in the IMS core, which is not built.
The part a wallet could not cover is recorded, not lost.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime

SECONDS_PER_MINUTE = 60
_DIGITS = re.compile(r"^[0-9]{7,15}$")


@dataclass(frozen=True)
class CallCost:
    seconds: int
    on_net: bool
    rate_kobo_per_min: int
    cost_kobo: int


def answered_seconds(answered_at: datetime | None, ended_at: datetime) -> int:
    """Whole seconds from the answer to the end, rounded up. 0 for a call nobody answered."""
    if answered_at is None:
        return 0
    seconds = (ended_at - answered_at).total_seconds()
    return max(0, math.ceil(seconds))


def call_cost(seconds: int, rate_kobo_per_min: int, *, on_net: bool) -> CallCost:
    """Per second: the rate is for a minute, the cost is rounded up to a whole kobo."""
    if seconds < 0 or rate_kobo_per_min < 0:
        raise ValueError("seconds and the rate cannot be negative")
    cost = -(-seconds * rate_kobo_per_min // SECONDS_PER_MINUTE)  # whole-number ceiling
    return CallCost(
        seconds=seconds, on_net=on_net, rate_kobo_per_min=rate_kobo_per_min, cost_kobo=cost
    )


def national_msisdn(number: str) -> str | None:
    """A Nigerian number in the 234 form the lines are kept in, or None if it is not one.

    Takes what the call records hold: 234XXXXXXXXXX, +234..., 0XXXXXXXXXX, or a SIP-style form with
    a leading '+'. Anything else (a short code, an international number) is not ours.
    """
    value = number.strip().removeprefix("+")
    if not _DIGITS.match(value):
        return None
    if value.startswith("0") and len(value) == 11:
        return "234" + value[1:]
    if value.startswith("234") and len(value) == 13:
        return value
    return None
