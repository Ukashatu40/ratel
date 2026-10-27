"""Prepaid cards: the number, the PIN with its check digit, and the states a card moves through.

Pure: no database, no clock, no logging. The rules (Build Plan, RatelBSS: money; PRODUCT_RULES.md,
Vouchers):
- A card has a 20 digit number and a PIN of 13 digits plus one Luhn check digit (14 digits as
  printed and as typed). The PIN is never stored: see `domain/pins.py`.
- States: requested, approved, sent_to_printer, in_stock, on_sale, used, expired, and locked for a
  lost or stolen card. A card can be redeemed only while it is `on_sale`.
- At most 5 failed redemption attempts per card number per hour.

TODO(PRD): face values and expiry; who moves a batch from state to state and how (the table below
is the order the Build Plan lists, nothing more); and whether the Luhn digit belongs to the PIN, as
assumed here, or whether the card number carries one too.
"""

from __future__ import annotations

import secrets
from enum import StrEnum

CARD_NUMBER_LENGTH = 20
PIN_BODY_LENGTH = 13
PIN_LENGTH = PIN_BODY_LENGTH + 1  # the body and its Luhn check digit
MAX_FAILED_ATTEMPTS = 5
ATTEMPT_WINDOW_SECONDS = 3600


class VoucherState(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    SENT_TO_PRINTER = "sent_to_printer"
    IN_STOCK = "in_stock"
    ON_SALE = "on_sale"
    USED = "used"
    EXPIRED = "expired"
    LOCKED = "locked"


S = VoucherState
# From -> where it may go. `used` is final; `expired` and `locked` are not left either.
_TRANSITIONS: dict[VoucherState, frozenset[VoucherState]] = {
    S.REQUESTED: frozenset({S.APPROVED, S.LOCKED}),
    S.APPROVED: frozenset({S.SENT_TO_PRINTER, S.LOCKED}),
    S.SENT_TO_PRINTER: frozenset({S.IN_STOCK, S.LOCKED}),
    S.IN_STOCK: frozenset({S.ON_SALE, S.EXPIRED, S.LOCKED}),
    S.ON_SALE: frozenset({S.USED, S.EXPIRED, S.LOCKED}),
    S.USED: frozenset(),
    S.EXPIRED: frozenset(),
    S.LOCKED: frozenset(),
}


class InvalidVoucherTransition(ValueError):
    """A card cannot move between these two states."""


def check_transition(current: VoucherState, target: VoucherState) -> None:
    """Raise `InvalidVoucherTransition` unless a card may move from `current` to `target`."""
    if target not in _TRANSITIONS[current]:
        raise InvalidVoucherTransition(f"{current.value} -> {target.value}")


def luhn_check_digit(body: str) -> str:
    """The Luhn digit that makes `body` plus the digit pass `is_luhn_valid`."""
    _require_digits(body)
    total = 0
    for position, char in enumerate(reversed(body)):
        digit = int(char)
        if position % 2 == 0:  # the body's last digit is doubled, once the check digit is added
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - total % 10) % 10)


def is_luhn_valid(number: str) -> bool:
    """Does `number` (its last digit the check digit) pass the Luhn check?"""
    if not number.isascii() or not number.isdigit() or len(number) < 2:
        return False
    return luhn_check_digit(number[:-1]) == number[-1]


def is_card_number(value: str) -> bool:
    return len(value) == CARD_NUMBER_LENGTH and value.isascii() and value.isdigit()


def is_pin(value: str) -> bool:
    """Well formed: 14 digits with a right check digit. Says nothing about being the right PIN."""
    return len(value) == PIN_LENGTH and is_luhn_valid(value)


def new_card_number() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(CARD_NUMBER_LENGTH))


def new_pin() -> str:
    body = "".join(secrets.choice("0123456789") for _ in range(PIN_BODY_LENGTH))
    return body + luhn_check_digit(body)


def _require_digits(value: str) -> None:
    if not value.isascii() or not value.isdigit():
        raise ValueError("expected digits only")
