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
from app.bss_lines.repositories.desk_ports import DeskReadRepository
from app.bss_money.domain.allowance import Bucket
from app.bss_money.domain.entries import Posting
from app.bss_money.domain.plans import Bundle, Plan
from app.bss_money.domain.purchase import OfferKind
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
        """Active, out-of-data or expired lines that hold at least one bucket, lowest id first."""
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


@dataclass(frozen=True)
class StoredPayment:
    payment_id: int
    public_id: str
    line_id: int
    provider: str
    provider_ref: str
    amount_kobo: int
    status: str
    checkout_url: str | None
    created_at: datetime


class DuplicateKey(Exception):
    """A payment with this Idempotency-Key already exists (a retry that raced the first call)."""


class PaymentRepository(Protocol):
    """Storage for gateway payments. Works in the caller's transaction and never commits."""

    def add(
        self,
        *,
        public_id: str,
        line_id: int,
        provider: str,
        provider_ref: str,
        idempotency_key: str,
        amount_kobo: int,
    ) -> StoredPayment:
        """Store a new `pending` payment. Raises `DuplicateKey` if the key is already used."""
        ...

    def by_idempotency_key(self, key: str) -> StoredPayment | None: ...

    def by_public_id(self, public_id: str) -> StoredPayment | None: ...

    def by_reference(self, provider_ref: str, *, lock: bool = False) -> StoredPayment | None:
        """The payment for this provider reference. `lock` holds it until the transaction ends."""
        ...

    def set_checkout(self, payment_id: int, url: str) -> None: ...

    def mark_succeeded(
        self, payment_id: int, provider_txn_id: str | None, at: datetime
    ) -> None: ...

    def mark_failed(self, payment_id: int, provider_txn_id: str | None) -> None: ...

    def pending_references(self, older_than: datetime, limit: int) -> list[str]:
        """References of payments still pending that were started before `older_than`."""
        ...


@dataclass(frozen=True)
class PaymentRepositories:
    """Everything one payment step touches, all on the same transaction."""

    payments: PaymentRepository
    ledger: LedgerRepository
    lines: LineLookup


PaymentScope = Callable[[], AbstractContextManager[PaymentRepositories]]
"""Opens one transaction and yields the repositories on it: commit on exit, rollback on error."""


class PurchaseRepository(Protocol):
    """Storage for buying a plan or a bundle. Works in the caller's transaction, never commits."""

    def lock_line(self, line_id: int) -> RatedLine | None:
        """Take the line for this transaction, so two purchases cannot overdraw its wallet."""
        ...

    def get_offer(self, kind: OfferKind, offer_id: int) -> Plan | Bundle | None:
        """The offer, or None if there is none or it is not on sale."""
        ...

    def buckets(self, line_id: int) -> list[Bucket]: ...

    def add_bucket(self, line_id: int, bucket: Bucket) -> int:
        """Store a new bucket for the line and return its id (the id in `bucket` is ignored)."""
        ...


@dataclass(frozen=True)
class PurchaseRepositories:
    """Everything one purchase touches, all on the same transaction."""

    purchases: PurchaseRepository
    ledger: LedgerRepository


PurchaseScope = Callable[[], AbstractContextManager[PurchaseRepositories]]
"""Opens one transaction and yields the repositories on it: commit on exit, rollback on error."""


class BundleCatalog(Protocol):
    """Read-only storage for the list of bundles RatelPay shows."""

    def bundles_on_sale(self) -> list[Bundle]:
        """Every bundle that can be bought now, in `bundle_id` order."""
        ...


CatalogScope = Callable[[], AbstractContextManager[BundleCatalog]]
"""Opens one read-only transaction and yields the catalog."""


@dataclass(frozen=True)
class LedgerRow:
    entry_id: int
    line_id: int
    msisdn: str
    amount_kobo: int
    kind: str
    reference: str
    created_at: datetime


@dataclass(frozen=True)
class LineUsageRow:
    period_start: datetime
    period_end: datetime
    bytes_up: int
    bytes_down: int
    rated: bool


@dataclass(frozen=True)
class MoneyMoved:
    """Money that moved in a stretch of time. Both figures are positive kobo."""

    in_kobo: int
    out_kobo: int
    entries: int


class MoneyReadRepository(Protocol):
    """Read-only views of the wallets, the ledger and usage, for RatelDesk. Never writes."""

    def line_imsi(self, line_id: int) -> str | None:
        """The line's IMSI, or None if there is no such line."""
        ...

    def wallet_figures(self, line_id: int) -> tuple[int, int]:
        """The wallet's balance and the sum of the line's entries. Zero for both if none."""
        ...

    def ledger_page(
        self, *, line_id: int | None, kind: str | None, offset: int, limit: int
    ) -> tuple[list[LedgerRow], int]:
        """Newest first, with the total matching."""
        ...

    def ledger_kind_counts(self, line_id: int | None) -> dict[str, int]:
        """Entries per kind for the line (or all lines), ignoring any kind filter."""
        ...

    def wallet_totals(self) -> tuple[int, int]:
        """The sum of every balance and the number of wallets holding more than zero."""
        ...

    def moved_between(self, start: datetime, end: datetime) -> MoneyMoved:
        """Entries made at or after `start` and before `end`."""
        ...

    def topped_up_between(self, start: datetime, end: datetime) -> int:
        """Kobo of `top_up` entries made at or after `start` and before `end`."""
        ...

    def line_usage(
        self,
        imsi: str,
        *,
        start: datetime,
        end: datetime,
        before: datetime | None,
        limit: int,
    ) -> list[LineUsageRow]:
        """Records with `start <= period_start <= end` (and before `before`), newest first."""
        ...


@dataclass(frozen=True)
class DeskReads:
    """What RatelDesk's read-only money screens use, on one transaction."""

    money: MoneyReadRepository
    lines: DeskReadRepository


DeskReadScope = Callable[[], AbstractContextManager[DeskReads]]
"""Opens one read-only transaction and yields the views."""
