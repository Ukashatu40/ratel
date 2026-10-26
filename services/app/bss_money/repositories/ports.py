"""What the money services need from storage, as an interface. No database code here.

The SQL implementation is in sql.py; tests use the in-memory fake in tests/app/bss_money/fakes.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.bss_lines.domain.state_machine import LineState
from app.bss_money.domain.allowance import Bucket
from app.bss_money.domain.entries import Posting
from app.bss_money.domain.plans import Plan
from app.bss_money.domain.rating import RatingResult, UsageRecord
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
