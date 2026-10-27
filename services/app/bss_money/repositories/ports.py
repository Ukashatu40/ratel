"""What the money services need from storage, as an interface. No database code here.

The SQL implementation is in sql.py; tests use the in-memory fake in tests/app/bss_money/fakes.py.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.bss_lines.domain.state_machine import LineState
from app.bss_money.domain.allowance import Bucket
from app.bss_money.domain.entries import Posting
from app.bss_money.domain.plans import Plan
from app.bss_money.domain.rating import RatingResult, UsageRecord
from app.bss_money.domain.vouchers import VoucherState
from app.bss_money.domain.wallets import WalletMismatch


class DuplicateEntry(Exception):
    """An entry with this (line, kind, reference) already exists. Nothing was changed."""


class BalanceOutOfRange(Exception):
    """The wallet balance would not fit the column. Nothing was changed."""


@dataclass(frozen=True)
class StoredEntry:
    entry_id: int
    line_id: int
    amount_kobo: int
    kind: str
    reference: str
    created_at: datetime | None


class LedgerRepository(Protocol):
    def append(self, posting: Posting) -> tuple[StoredEntry, int]:
        """Append the entry and move the line's wallet by its amount, all or nothing.

        Creates the wallet on a line's first posting. Returns the stored entry and the new
        balance. Raises `DuplicateEntry` if (line, kind, reference) was already posted, and
        `BalanceOutOfRange` if the balance would not fit; in both cases nothing is kept and the
        caller's transaction stays usable.
        """
        ...

    def find(self, line_id: int, kind: str, reference: str) -> StoredEntry | None: ...

    def balance(self, line_id: int) -> int | None:
        """The wallet's balance, or None if the line has no wallet."""
        ...

    def mismatches(self) -> list[WalletMismatch]:
        """Every wallet whose balance is not the sum of its entries."""
        ...


@dataclass(frozen=True)
class RatedLine:
    """What the rating job needs to know about one line."""

    line_id: int
    imsi: str
    state: LineState
    plan: Plan


class RatingRepository(Protocol):
    """Storage for the rating job. Works inside the caller's transaction and never commits."""

    def lines_with_unrated_usage(self) -> list[int]:
        """Lines that own a usage record nobody has rated yet, lowest id first."""
        ...

    def lines_with_allowance(self) -> list[int]:
        """Active or out-of-data lines that hold at least one bucket, lowest id first."""
        ...

    def lock_line(self, line_id: int) -> RatedLine | None:
        """Take the line for this transaction; another run waits here until this one ends.

        None if there is no such line.
        """
        ...

    def unrated_records(self, line: RatedLine, limit: int) -> list[UsageRecord]:
        """The line's oldest unrated usage records, at most `limit`."""
        ...

    def buckets(self, line_id: int) -> list[Bucket]: ...

    def save_rating(self, line_id: int, result: RatingResult) -> None:
        """Store the new bucket totals and mark every rated record, all or nothing."""
        ...


@dataclass(frozen=True)
class StoredVoucher:
    """A card as the redemption needs it. The card number is not carried: callers have it."""

    voucher_id: int
    pin_hash: str
    face_value_kobo: int
    state: VoucherState
    expires_at: datetime | None
    used_by_line_id: int | None


@dataclass(frozen=True)
class NewVoucher:
    card_number: str
    pin_hash: str
    face_value_kobo: int
    batch: str
    expires_at: datetime | None


class VoucherNotRedeemable(Exception):
    """The card was not `on_sale` when it was marked used. Nothing was changed."""


class VoucherRepository(Protocol):
    """Storage for prepaid cards. Works inside the caller's transaction and never commits."""

    def add_all(self, vouchers: Sequence[NewVoucher]) -> list[int]:
        """Store new cards in the `requested` state; return their ids in the same order."""
        ...

    def lock_card(self, card_number: str) -> StoredVoucher | None:
        """Serialise everything done with this card number until the transaction ends.

        Takes the lock even when no card has the number, so that guessing at numbers that exist
        and numbers that do not behave alike. Returns the card, or None if there is none.
        """
        ...

    def failed_attempts_since(self, card_number: str, since: datetime) -> int: ...

    def record_failed_attempt(self, card_number: str, at: datetime) -> None: ...

    def mark_used(self, voucher_id: int, line_id: int, at: datetime) -> None:
        """Move the card from `on_sale` to `used`. Raises `VoucherNotRedeemable` if it is not."""
        ...

    def state_of(self, voucher_id: int) -> VoucherState | None: ...

    def batch_cards(self, batch: str) -> list[tuple[int, VoucherState]]:
        """Every card of the batch with its state, lowest id first."""
        ...

    def set_state(self, voucher_id: int, state: VoucherState) -> None: ...


class LineLookup(Protocol):
    def line_id_for_msisdn(self, msisdn: str) -> int | None:
        """The line that has this phone number, or None. A terminated line does not count."""
        ...


@dataclass(frozen=True)
class RedemptionRepositories:
    """Everything one redemption touches, all on the same transaction."""

    vouchers: VoucherRepository
    ledger: LedgerRepository
    lines: LineLookup


RedemptionScope = Callable[[], AbstractContextManager[RedemptionRepositories]]
"""Opens one transaction and yields the repositories on it: commit on exit, rollback on error."""
