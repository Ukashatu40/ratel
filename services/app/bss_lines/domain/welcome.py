"""The welcome SMS text (docs/welcome-sms.md). Decided by the project lead on 2026-11-25."""

from __future__ import annotations

import re

SMS_LIMIT = 160  # one SMS in the GSM 7-bit alphabet
_MSISDN = re.compile(r"^234[0-9]{10}$")


def national_number(msisdn: str) -> str:
    """2348000000000 as a customer dials it: 08000000000."""
    if not _MSISDN.match(msisdn):
        raise ValueError("not a Nigerian number in 234 form")
    return "0" + msisdn[3:]


def welcome_text(msisdn: str) -> str:
    return (
        f"Welcome to Ratelplus! Your number is {national_number(msisdn)}. "
        "Text MENU to 647 for balance, bundles and top-up."
    )
