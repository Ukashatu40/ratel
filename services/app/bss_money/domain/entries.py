"""The ledger rules: what a money movement is, and what is never allowed.

Pure rules only: no database, no web framework, no logging, no clock. Money is whole kobo, an
`int`. A wallet's balance is the sum of its ledger entries: credits are positive, debits negative.
The ledger is append-only. A mistake is fixed by appending a correcting entry, never by editing
or deleting the old one (docs/adr/0009-ledger-append-only-in-the-database.md).

Source: Build Plan, RatelBSS: money ("Ledger and wallet"); docs/DATABASE_AND_MIGRATIONS.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

BIGINT_MAX = 2**63 - 1
REFERENCE_MAX_LENGTH = 120


class EntryKind(StrEnum):
    """What a ledger entry is for.

    TODO(PRD): the final list of entry kinds. These four are the least the Build Plan implies:
    money in, money out, VAT as its own entry (never folded into a price), and a correction.
    The names are provisional. The ledger is append-only, so no real entry may be written until
    the PRD fixes them; a wrong name could never be edited afterwards.
    """

    TOP_UP = "top_up"  # money in: a payment or a voucher redemption
    PURCHASE = "purchase"  # money out: a plan or a bundle bought from the wallet
    VAT = "vat"  # its own entry. TODO(finance): the rate (7.5% when the plan was written)
    CORRECTION = "correction"  # fixes an earlier entry by adding a new one


class InvalidPosting(ValueError):
    """A money movement the ledger refuses to record."""


@dataclass(frozen=True)
class Posting:
    """One validated movement. `amount_kobo` is positive for money in, negative for money out."""

    line_id: int
    amount_kobo: int
    kind: EntryKind
    reference: str


def new_posting(line_id: int, amount_kobo: int, kind: str, reference: str) -> Posting:
    """Check a movement and return it, or raise `InvalidPosting` saying which rule it broke.

    `reference` is an opaque id that makes a replay safe: a payment's `provider_ref`, a voucher
    id, a purchase id. It is never a card number, a PIN or a phone number.
    """
    if not _is_int(line_id) or line_id <= 0:
        raise InvalidPosting("line_id must be a positive whole number")
    if not _is_int(amount_kobo):
        raise InvalidPosting("amount_kobo must be a whole number of kobo, never a float")
    if amount_kobo == 0:
        raise InvalidPosting("amount_kobo must not be zero")
    if abs(amount_kobo) > BIGINT_MAX:
        raise InvalidPosting("amount_kobo is outside the supported range")
    try:
        entry_kind = EntryKind(kind)
    except ValueError:
        raise InvalidPosting("kind is not a known entry kind") from None
    if not isinstance(reference, str) or not reference.strip():
        raise InvalidPosting("reference must not be empty")
    if len(reference) > REFERENCE_MAX_LENGTH:
        raise InvalidPosting(f"reference must be at most {REFERENCE_MAX_LENGTH} characters")
    return Posting(line_id, amount_kobo, entry_kind, reference)


def apply_to_balance(balance_kobo: int, amount_kobo: int) -> int:
    """The balance after one movement. Refuses a result outside the database's range."""
    result = balance_kobo + amount_kobo
    if abs(result) > BIGINT_MAX:
        raise InvalidPosting("the balance would leave the supported range")
    return result


def _is_int(value: object) -> bool:
    # bool is an int in Python; True as a number of kobo is a bug, not a payment.
    return isinstance(value, int) and not isinstance(value, bool)
