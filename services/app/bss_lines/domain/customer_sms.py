"""SMS to customers: kinds, limits and the welcome text (docs/customer-sms.md).

Decided by the project lead on 2026-11-25. Every text fits one SMS in the GSM 7-bit alphabet: 160
characters, ASCII only. The naira sign is written N, because it is not in that alphabet and would
make the phone count 70 characters per SMS.
"""

from __future__ import annotations

import re
from enum import StrEnum

SMS_LIMIT = 160
_MSISDN = re.compile(r"^234[0-9]{10}$")


class SmsKind(StrEnum):
    WELCOME = "welcome"  # once per line, after activation
    CALL = "call"  # after each charged call: duration, cost, balance


def national_number(msisdn: str) -> str:
    """2348000000000 as a customer dials it: 08000000000."""
    if not _MSISDN.match(msisdn):
        raise ValueError("not a Nigerian number in 234 form")
    return "0" + msisdn[3:]


def check_text(text: str) -> str:
    """The text if it fits one SMS of plain characters, else ValueError."""
    if not text or len(text) > SMS_LIMIT or not text.isascii():
        raise ValueError("an SMS text must be 1 to 160 plain (ASCII) characters")
    return text


def welcome_text(msisdn: str) -> str:
    return check_text(
        f"Welcome to Ratelplus! Your number is {national_number(msisdn)}. "
        "Text MENU to 647 for balance, bundles and top-up."
    )
