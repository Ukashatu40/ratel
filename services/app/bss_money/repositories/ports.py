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
from app.bss_money.domain.catalogue import CatalogueSettings
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
class PendingSms:
    sms_id: int
    line_id: int
    msisdn: str
    kind: str
    text: str


class CustomerSmsRepository(Protocol):
    """SMS to customers, sent from 555 by the voice VM (`customer_sms`, docs/customer-sms.md)."""

    def add(self, *, line_id: int, kind: str, dedupe_key: str, text: str) -> None:
        """Queue one, once per `dedupe_key`: a second add with the same key changes nothing."""
        ...

    def pending(self, limit: int) -> list[PendingSms]:
        """Unsent SMS of lines in service (active, out of data, expired), oldest first."""
        ...

    def mark_sent(self, sms_id: int, at: datetime) -> datetime | None:
        """Record it sent (the first time only) and return when; None if there is no such SMS."""
        ...


@dataclass(frozen=True)
class BatchView:
    """A voucher batch as RatelDesk shows it (domain/voucher_batches.py)."""

    batch_id: int
    name: str
    face_value_kobo: int
    card_count: int
    state: str
    requested_by: str
    requested_at: datetime | None
    approved_by: str | None
    printed_by: str | None
    printed_at: datetime | None
    cards_used: int


@dataclass(frozen=True)
class CardView:
    """One card as staff may see it: never its PIN or PIN hash."""

    voucher_id: int
    card_number: str
    batch: str
    face_value_kobo: int
    state: VoucherState
    used_by_msisdn: str | None
    used_at: datetime | None


class VoucherAdminRepository(Protocol):
    """Voucher batches and cards as staff manage them. Inside the caller's transaction."""

    def batches(self, limit: int) -> list[BatchView]:
        """Newest first."""
        ...

    def batch(self, batch_id: int, *, lock: bool = False) -> BatchView | None: ...

    def batch_for_key(self, idempotency_key: str) -> BatchView | None: ...

    def add_batch(
        self, *, face_value_kobo: int, card_count: int, requested_by: str, idempotency_key: str
    ) -> BatchView:
        """A new batch in `requested`, named from its id (V-00007)."""
        ...

    def set_batch(
        self,
        batch_id: int,
        *,
        state: str,
        approved_by: str | None = None,
        printed_by: str | None = None,
        printed_at: datetime | None = None,
    ) -> None:
        """Move the batch; the who and when given are recorded, the others left as they are."""
        ...

    def add_cards(self, cards: Sequence[NewVoucher], state: VoucherState) -> list[int]: ...

    def cards_of(self, batch: str) -> list[tuple[int, VoucherState]]:
        """Every card of the batch with its state, lowest id first."""
        ...

    def set_card_states(self, voucher_ids: Sequence[int], state: VoucherState) -> None: ...

    def card(self, card_number: str) -> CardView | None: ...

    def card_by_id(self, voucher_id: int, *, lock: bool = False) -> CardView | None: ...

    def add_event(
        self,
        *,
        actor: str,
        action: str,
        reason: str,
        detail: str,
        batch_id: int | None = None,
        voucher_id: int | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class VoucherAdminRepositories:
    admin: VoucherAdminRepository
    vouchers: VoucherRepository  # for the failed redemption attempts
    catalogue: CatalogueRepository


VoucherAdminScope = Callable[[], AbstractContextManager[VoucherAdminRepositories]]
"""Opens one transaction and yields the repositories on it: commit on exit, rollback on error."""


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
class LineCallRow:
    """One call record, as RatelDesk's line page shows it. Personal data: never logged."""

    call_id: str
    from_msisdn: str
    to_msisdn: str
    started_at: datetime
    answered_at: datetime | None
    ended_at: datetime
    end_reason: str


@dataclass(frozen=True)
class MoneyMoved:
    """Money that moved in a stretch of time. Both figures are positive kobo."""

    in_kobo: int
    out_kobo: int
    entries: int


class MoneyReadRepository(Protocol):
    """Read-only views of the wallets, the ledger and usage, for RatelDesk. Never writes."""

    def line_msisdn(self, line_id: int) -> str | None:
        """The line's number, or None if there is no such line."""
        ...

    def line_calls(
        self,
        msisdn: str,
        *,
        start: datetime,
        end: datetime,
        before: tuple[datetime, str] | None,
        limit: int,
    ) -> list[LineCallRow]:
        """Calls the number made or received with `start <= started_at <= end`, newest first.

        With `before`, only those that sort after (started_at, call_id) in that order.
        """
        ...

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


# The catalogue and call charging (docs/catalogue.md).


@dataclass(frozen=True)
class OfferView:
    """A plan or a bundle as the catalogue screen shows it, whatever its state."""

    kind: OfferKind
    offer_id: int
    name: str
    price_kobo: int
    data_bytes: int
    validity_days: int
    channels: list[str]
    state: str
    # Plans only (None for a bundle).
    speed_dl_mbps: float | None = None
    speed_ul_mbps: float | None = None
    on_exhaustion: str | None = None
    slow_dl_mbps: float | None = None
    slow_ul_mbps: float | None = None


@dataclass(frozen=True)
class NewOffer:
    kind: OfferKind
    name: str
    price_kobo: int
    data_bytes: int
    validity_days: int
    channels: str  # stored form, already checked
    speed_dl_mbps: float | None = None
    speed_ul_mbps: float | None = None
    on_exhaustion: str | None = None
    slow_dl_mbps: float | None = None
    slow_ul_mbps: float | None = None


@dataclass(frozen=True)
class AuditRow:
    audit_id: int
    actor: str
    action: str
    offer_kind: str | None
    offer_id: int | None
    reason: str
    detail: str
    created_at: datetime | None


class CatalogueRepository(Protocol):
    """Works inside the caller's transaction and never commits."""

    def offers(self) -> list[OfferView]:
        """Every plan and bundle, on sale or retired, plans first, oldest first."""
        ...

    def add_offer(self, offer: NewOffer) -> int:
        """Store a new offer, on sale. Returns its id."""
        ...

    def lock_offer_state(self, kind: OfferKind, offer_id: int) -> str | None:
        """The offer's state, locked until the transaction ends, or None if there is no offer."""
        ...

    def retire(self, kind: OfferKind, offer_id: int) -> None: ...

    def settings(self) -> CatalogueSettings | None:
        """What an admin saved, or None if nothing was ever saved."""
        ...

    def save_settings(self, settings: CatalogueSettings) -> None: ...

    def audit_for_key(self, idempotency_key: str) -> AuditRow | None: ...

    def add_audit(
        self,
        *,
        actor: str,
        action: str,
        offer_kind: str | None,
        offer_id: int | None,
        idempotency_key: str | None,
        reason: str,
        detail: str,
    ) -> int: ...

    def audit_page(self, limit: int, before_id: int | None) -> list[AuditRow]:
        """Newest first."""
        ...


CatalogueScope = Callable[[], AbstractContextManager[CatalogueRepository]]


@dataclass(frozen=True)
class CallToCharge:
    record_id: int
    call_id: str  # the SIP Call-ID: settles the call's reservation (ADR 0013)
    from_msisdn: str
    to_msisdn: str
    answered_at: datetime | None
    ended_at: datetime


class CallChargeRepository(Protocol):
    """Works inside the caller's transaction and never commits."""

    def uncharged_calls(self, limit: int) -> list[CallToCharge]:
        """Call records with no charge row yet, oldest first."""
        ...

    def lock_line_for_msisdn(self, msisdn: str) -> int | None:
        """The live (not terminated) line with this number, locked, or None."""
        ...

    def is_ratel_number(self, msisdn: str) -> bool:
        """Whether the number belongs to a live Ratelplus line (an on-net call)."""
        ...

    def save_charge(
        self,
        *,
        record_id: int,
        line_id: int | None,
        seconds: int,
        on_net: bool,
        rate_kobo_per_min: int,
        charged_kobo: int,
        uncovered_kobo: int,
    ) -> None: ...

    def settle_reservation(self, call_id: str) -> None:
        """The call's reservation, if any, is settled: its record has been charged."""
        ...


@dataclass(frozen=True)
class CallChargeRepositories:
    calls: CallChargeRepository
    ledger: LedgerRepository
    catalogue: CatalogueRepository
    sms: CustomerSmsRepository


CallChargeScope = Callable[[], AbstractContextManager[CallChargeRepositories]]


@dataclass(frozen=True)
class PrepaidLine:
    line_id: int
    state: LineState


@dataclass(frozen=True)
class ReservationView:
    call_id: str
    line_id: int
    rate_kobo_per_min: int
    max_seconds: int
    reserved_kobo: int
    state: str  # open, ended, settled


@dataclass(frozen=True)
class SmsChargeView:
    outcome: str
    charged_kobo: int


class PrepaidRepository(Protocol):
    """Call reservations and SMS charges (ADR 0013). Works inside the caller's transaction."""

    def lock_line(self, msisdn: str) -> PrepaidLine | None:
        """The line with this number (not terminated), locked until the transaction ends, so two
        calls or texts from one line take turns over its balance."""
        ...

    def is_ratel_number(self, msisdn: str) -> bool: ...

    def held_kobo(self, line_id: int, now: datetime) -> int:
        """Kobo set aside by the line's open and ended reservations that have not expired."""
        ...

    def reservation(self, call_id: str) -> ReservationView | None: ...

    def add_reservation(
        self,
        *,
        call_id: str,
        line_id: int,
        rate_kobo_per_min: int,
        max_seconds: int,
        reserved_kobo: int,
        expires_at: datetime,
    ) -> None: ...

    def end_reservation(self, call_id: str, used_seconds: int, reserved_kobo: int) -> None:
        """An open reservation becomes ended, holding `reserved_kobo` (the call's cost)."""
        ...

    def sms_charge(self, message_id: str) -> SmsChargeView | None: ...

    def add_sms_charge(
        self, *, message_id: str, line_id: int | None, outcome: str, charged_kobo: int
    ) -> None: ...


@dataclass(frozen=True)
class PrepaidRepositories:
    prepaid: PrepaidRepository
    ledger: LedgerRepository
    catalogue: CatalogueRepository


PrepaidScope = Callable[[], AbstractContextManager[PrepaidRepositories]]
