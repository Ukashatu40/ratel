"""The ledger on PostgreSQL (and SQLite in unit tests), through SQLAlchemy.

Only this module talks to the database for RatelBSS: money. It works inside the transaction the
caller owns and never commits, so a purchase can post a debit and its VAT entry together or not
at all. No rules here: those are in the domain and the services.

The rating job's storage (`SqlRatingRepository`) also reads the RatelMeter API's `usage_record`
table and the lines of bss_lines, which BSS: money is allowed to do (docs/DEPENDENCIES.md), and
writes only BSS: money's own tables.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.bss_lines.domain.state_machine import LineState
from app.bss_lines.models.lines import Bundle as BundleRow
from app.bss_lines.models.lines import Line
from app.bss_lines.models.lines import Plan as PlanRow
from app.bss_money.domain.allowance import Bucket
from app.bss_money.domain.entries import Posting
from app.bss_money.domain.plans import Bundle as BundleOffer
from app.bss_money.domain.plans import OnExhaustion, Plan
from app.bss_money.domain.purchase import OfferKind
from app.bss_money.domain.rating import RatingResult, UsageRecord
from app.bss_money.domain.vouchers import VoucherState
from app.bss_money.domain.wallets import WalletMismatch
from app.bss_money.models.allowance import AllowanceBucket
from app.bss_money.models.ledger import LedgerEntry, Wallet
from app.bss_money.models.payments import Payment
from app.bss_money.models.rating import UsageRating
from app.bss_money.models.vouchers import Voucher, VoucherAttempt
from app.bss_money.repositories.ports import (
    BalanceOutOfRange,
    DuplicateEntry,
    DuplicateKey,
    NewVoucher,
    RatedLine,
    StoredEntry,
    StoredPayment,
    StoredVoucher,
    VoucherNotRedeemable,
)
from app.meter_api.models import UsageRecordModel


class SqlLedgerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, posting: Posting) -> tuple[StoredEntry, int]:
        self._ensure_wallet(posting.line_id)
        try:
            # A savepoint: if the entry or the balance update fails, neither is kept, and the
            # caller's transaction can carry on.
            with self._session.begin_nested():
                entry = LedgerEntry(
                    line_id=posting.line_id,
                    amount_kobo=posting.amount_kobo,
                    kind=posting.kind.value,
                    reference=posting.reference,
                )
                self._session.add(entry)
                self._session.flush()
                balance = self._add_to_balance(posting.line_id, posting.amount_kobo)
        except IntegrityError as exc:
            if self.find(posting.line_id, posting.kind.value, posting.reference) is None:
                raise  # some other rule failed: do not call it a duplicate
            raise DuplicateEntry from exc
        except DataError as exc:
            raise BalanceOutOfRange from exc
        return _stored(entry), balance

    def find(self, line_id: int, kind: str, reference: str) -> StoredEntry | None:
        entry = self._session.execute(
            select(LedgerEntry).where(
                LedgerEntry.line_id == line_id,
                LedgerEntry.kind == kind,
                LedgerEntry.reference == reference,
            )
        ).scalar_one_or_none()
        return None if entry is None else _stored(entry)

    def balance(self, line_id: int) -> int | None:
        value = self._session.execute(
            select(Wallet.balance_kobo).where(Wallet.line_id == line_id)
        ).scalar_one_or_none()
        return None if value is None else int(value)

    def mismatches(self) -> list[WalletMismatch]:
        # Starts from the wallets: an entry cannot exist without one (foreign key), and a wallet
        # with no entries must have a zero balance.
        totals = (
            select(LedgerEntry.line_id, func.sum(LedgerEntry.amount_kobo).label("total"))
            .group_by(LedgerEntry.line_id)
            .subquery()
        )
        ledger_total = func.coalesce(totals.c.total, 0)
        rows = self._session.execute(
            select(Wallet.line_id, Wallet.balance_kobo, ledger_total)
            .outerjoin(totals, totals.c.line_id == Wallet.line_id)
            .where(Wallet.balance_kobo != ledger_total)
            .order_by(Wallet.line_id)
        ).all()
        return [WalletMismatch(int(r[0]), int(r[1]), int(r[2])) for r in rows]

    def _ensure_wallet(self, line_id: int) -> None:
        """Create the wallet with a zero balance if there is none. Safe to repeat and to race."""
        dialect = self._session.get_bind().dialect.name
        if dialect == "postgresql":
            pg = postgresql.insert(Wallet).values(line_id=line_id, balance_kobo=0)
            self._session.execute(pg.on_conflict_do_nothing(index_elements=[Wallet.line_id]))
        elif dialect == "sqlite":
            lite = sqlite.insert(Wallet).values(line_id=line_id, balance_kobo=0)
            self._session.execute(lite.on_conflict_do_nothing(index_elements=[Wallet.line_id]))
        else:
            raise NotImplementedError(
                f"the ledger supports PostgreSQL (and SQLite in tests), not {dialect}"
            )

    def _add_to_balance(self, line_id: int, amount_kobo: int) -> int:
        """One statement, so two postings to a line at the same moment cannot lose one."""
        new_balance = self._session.execute(
            update(Wallet)
            .where(Wallet.line_id == line_id)
            .values(balance_kobo=Wallet.balance_kobo + amount_kobo)
            .returning(Wallet.balance_kobo)
        ).scalar_one()
        return int(new_balance)


def _stored(entry: LedgerEntry) -> StoredEntry:
    return StoredEntry(
        entry.entry_id,
        entry.line_id,
        entry.amount_kobo,
        entry.kind,
        entry.reference,
        entry.created_at,
    )


class SqlVoucherRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_all(self, vouchers: Sequence[NewVoucher]) -> list[int]:
        rows = [
            Voucher(
                card_number=v.card_number,
                pin_hash=v.pin_hash,
                face_value_kobo=v.face_value_kobo,
                state=VoucherState.REQUESTED.value,
                batch=v.batch,
                expires_at=v.expires_at,
            )
            for v in vouchers
        ]
        self._session.add_all(rows)
        self._session.flush()
        return [row.voucher_id for row in rows]

    def lock_card(self, card_number: str) -> StoredVoucher | None:
        if self._session.get_bind().dialect.name == "postgresql":
            # Held to the end of the transaction. It exists even when there is no row to lock.
            self._session.execute(
                select(func.pg_advisory_xact_lock(func.hashtextextended(card_number, 0)))
            )
        row = self._session.execute(
            select(Voucher)
            .where(Voucher.card_number == card_number)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if row is None:
            return None
        return StoredVoucher(
            voucher_id=row.voucher_id,
            pin_hash=row.pin_hash,
            face_value_kobo=row.face_value_kobo,
            state=VoucherState(row.state),
            expires_at=None if row.expires_at is None else _utc(row.expires_at),
            used_by_line_id=row.used_by_line_id,
        )

    def failed_attempts_since(self, card_number: str, since: datetime) -> int:
        return (
            self._session.scalar(
                select(func.count(VoucherAttempt.attempt_id)).where(
                    VoucherAttempt.card_number == card_number,
                    VoucherAttempt.attempted_at > since,
                )
            )
            or 0
        )

    def record_failed_attempt(self, card_number: str, at: datetime) -> None:
        self._session.add(VoucherAttempt(card_number=card_number, attempted_at=at))
        self._session.flush()

    def mark_used(self, voucher_id: int, line_id: int, at: datetime) -> None:
        result = self._session.execute(
            update(Voucher)
            .where(Voucher.voucher_id == voucher_id, Voucher.state == VoucherState.ON_SALE.value)
            .values(state=VoucherState.USED.value, used_by_line_id=line_id, used_at=at)
        )
        if result.rowcount != 1:  # type: ignore[attr-defined]  # CursorResult has it
            raise VoucherNotRedeemable

    def state_of(self, voucher_id: int) -> VoucherState | None:
        state = self._session.scalar(select(Voucher.state).where(Voucher.voucher_id == voucher_id))
        return None if state is None else VoucherState(state)

    def batch_cards(self, batch: str) -> list[tuple[int, VoucherState]]:
        rows = self._session.execute(
            select(Voucher.voucher_id, Voucher.state)
            .where(Voucher.batch == batch)
            .order_by(Voucher.voucher_id)
            .with_for_update()
        )
        return [(voucher_id, VoucherState(state)) for voucher_id, state in rows]

    def set_state(self, voucher_id: int, state: VoucherState) -> None:
        self._session.execute(
            update(Voucher).where(Voucher.voucher_id == voucher_id).values(state=state.value)
        )


_IN_SERVICE = (LineState.ACTIVE.value, LineState.OUT_OF_DATA.value, LineState.EXPIRED.value)


def _utc(moment: datetime) -> datetime:
    """SQLite hands back naive times; they were stored as UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


class SqlRatingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lines_with_unrated_usage(self) -> list[int]:
        rows = self._session.execute(
            select(Line.line_id)
            .join(UsageRecordModel, UsageRecordModel.imsi == Line.imsi)
            .outerjoin(UsageRating, UsageRating.usage_record_id == UsageRecordModel.id)
            .where(UsageRating.usage_record_id.is_(None))
            .distinct()
            .order_by(Line.line_id)
        )
        return list(rows.scalars())

    def lines_with_allowance(self) -> list[int]:
        has_bucket = exists().where(AllowanceBucket.line_id == Line.line_id)
        rows = self._session.execute(
            select(Line.line_id)
            .where(Line.state.in_(_IN_SERVICE), has_bucket)
            .order_by(Line.line_id)
        )
        return list(rows.scalars())

    def lock_line(self, line_id: int) -> RatedLine | None:
        # FOR UPDATE: a second run (or a purchase) waits here until this transaction ends, then
        # sees what this one stored. populate_existing: re-read the row after waiting.
        line = self._session.execute(
            select(Line)
            .where(Line.line_id == line_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if line is None:
            return None
        return RatedLine(
            line_id=line.line_id,
            imsi=line.imsi,
            state=LineState(line.state),
            plan=_plan_offer(line.plan),
        )

    def unrated_records(self, line: RatedLine, limit: int) -> list[UsageRecord]:
        rows = self._session.execute(
            select(UsageRecordModel)
            .outerjoin(UsageRating, UsageRating.usage_record_id == UsageRecordModel.id)
            .where(UsageRecordModel.imsi == line.imsi, UsageRating.usage_record_id.is_(None))
            .order_by(UsageRecordModel.period_start, UsageRecordModel.id)
            .limit(limit)
        )
        return [
            UsageRecord(
                record_id=str(row.id),
                period_start=_utc(row.period_start),
                bytes_up=row.bytes_up,
                bytes_down=row.bytes_down,
            )
            for row in rows.scalars()
        ]

    def buckets(self, line_id: int) -> list[Bucket]:
        rows = self._session.execute(
            select(AllowanceBucket)
            .where(AllowanceBucket.line_id == line_id)
            .order_by(AllowanceBucket.valid_to, AllowanceBucket.bucket_id)
            .with_for_update()
        )
        return [
            Bucket(
                bucket_id=row.bucket_id,
                source_kind=row.source_kind,  # type: ignore[arg-type]  # validated by Bucket
                source_id=row.source_id,
                data_bytes_total=row.data_bytes_total,
                data_bytes_used=row.data_bytes_used,
                valid_from=_utc(row.valid_from),
                valid_to=_utc(row.valid_to),
            )
            for row in rows.scalars()
        ]

    def save_rating(self, line_id: int, result: RatingResult) -> None:
        for bucket in result.buckets:
            self._session.execute(
                update(AllowanceBucket)
                .where(AllowanceBucket.bucket_id == bucket.bucket_id)
                .values(data_bytes_used=bucket.data_bytes_used)
            )
        for rating in result.ratings:
            self._session.add(
                UsageRating(
                    usage_record_id=int(rating.record_id),
                    line_id=line_id,
                    deducted_bytes=rating.deducted_bytes,
                    uncovered_bytes=rating.uncovered_bytes,
                )
            )
        self._session.flush()


class SqlLineLookup:
    def __init__(self, session: Session) -> None:
        self._session = session

    def line_id_for_msisdn(self, msisdn: str) -> int | None:
        return self._session.scalar(
            select(Line.line_id).where(
                Line.msisdn == msisdn, Line.state != LineState.TERMINATED.value
            )
        )


def _stored_payment(row: Payment) -> StoredPayment:
    return StoredPayment(
        payment_id=row.payment_id,
        public_id=row.public_id,
        line_id=row.line_id,
        provider=row.provider,
        provider_ref=row.provider_ref,
        amount_kobo=row.amount_kobo,
        status=row.status,
        checkout_url=row.checkout_url,
        created_at=_utc(row.created_at),
    )


class SqlPaymentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

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
        row = Payment(
            public_id=public_id,
            line_id=line_id,
            provider=provider,
            provider_ref=provider_ref,
            idempotency_key=idempotency_key,
            amount_kobo=amount_kobo,
            status="pending",
        )
        try:
            # A savepoint: if the key is already used, only this insert is undone.
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            if self.by_idempotency_key(idempotency_key) is None:
                raise  # some other rule failed: do not call it a retry
            raise DuplicateKey from exc
        self._session.refresh(row)  # the database's created_at
        return _stored_payment(row)

    def _one(self, *conditions: object, lock: bool = False) -> StoredPayment | None:
        statement = select(Payment).where(*conditions)  # type: ignore[arg-type]
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        row = self._session.execute(statement).scalar_one_or_none()
        return None if row is None else _stored_payment(row)

    def by_idempotency_key(self, key: str) -> StoredPayment | None:
        return self._one(Payment.idempotency_key == key)

    def by_public_id(self, public_id: str) -> StoredPayment | None:
        return self._one(Payment.public_id == public_id)

    def by_reference(self, provider_ref: str, *, lock: bool = False) -> StoredPayment | None:
        return self._one(Payment.provider_ref == provider_ref, lock=lock)

    def set_checkout(self, payment_id: int, url: str) -> None:
        self._session.execute(
            update(Payment).where(Payment.payment_id == payment_id).values(checkout_url=url)
        )

    def mark_succeeded(self, payment_id: int, provider_txn_id: str | None, at: datetime) -> None:
        self._session.execute(
            update(Payment)
            .where(Payment.payment_id == payment_id)
            .values(status="succeeded", provider_txn_id=provider_txn_id, credited_at=at)
        )

    def mark_failed(self, payment_id: int, provider_txn_id: str | None) -> None:
        self._session.execute(
            update(Payment)
            .where(Payment.payment_id == payment_id, Payment.status == "pending")
            .values(status="failed", provider_txn_id=provider_txn_id)
        )

    def pending_references(self, older_than: datetime, limit: int) -> list[str]:
        rows = self._session.execute(
            select(Payment.provider_ref)
            .where(Payment.status == "pending", Payment.created_at < older_than)
            .order_by(Payment.created_at)
            .limit(limit)
        )
        return list(rows.scalars())


def _plan_offer(plan: PlanRow) -> Plan:
    return Plan(
        plan_id=plan.plan_id,
        name=plan.name,
        price_kobo=plan.price_kobo,
        validity_days=plan.validity_days,
        data_bytes=plan.data_bytes,
        speed_ul_mbps=plan.speed_ul_mbps,
        speed_dl_mbps=plan.speed_dl_mbps,
        channels=tuple(c for c in plan.channels.split(",") if c),
        on_exhaustion=OnExhaustion(plan.on_exhaustion),
        slow_ul_mbps=plan.slow_ul_mbps,
        slow_dl_mbps=plan.slow_dl_mbps,
    )


class SqlPurchaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lock_line(self, line_id: int) -> RatedLine | None:
        # The same lock the rating job takes: a purchase and a rating run for one line take turns.
        line = self._session.execute(
            select(Line)
            .where(Line.line_id == line_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if line is None:
            return None
        return RatedLine(
            line_id=line.line_id,
            imsi=line.imsi,
            state=LineState(line.state),
            plan=_plan_offer(line.plan),
        )

    def get_offer(self, kind: OfferKind, offer_id: int) -> Plan | BundleOffer | None:
        if kind is OfferKind.PLAN:
            plan = self._session.get(PlanRow, offer_id)
            if plan is None or plan.state != "on_sale":
                return None
            return _plan_offer(plan)
        # TODO(M-25): the bundle table has no state column yet, so every bundle is on sale.
        bundle = self._session.get(BundleRow, offer_id)
        if bundle is None:
            return None
        return BundleOffer(
            bundle_id=bundle.bundle_id,
            name=bundle.name,
            price_kobo=bundle.price_kobo,
            validity_days=bundle.validity_days,
            data_bytes=bundle.data_bytes,
            channels=tuple(c for c in bundle.channels.split(",") if c),
        )

    def buckets(self, line_id: int) -> list[Bucket]:
        return SqlRatingRepository(self._session).buckets(line_id)

    def add_bucket(self, line_id: int, bucket: Bucket) -> int:
        row = AllowanceBucket(
            line_id=line_id,
            source_kind=bucket.source_kind.value,
            source_id=bucket.source_id,
            data_bytes_total=bucket.data_bytes_total,
            data_bytes_used=bucket.data_bytes_used,
            valid_from=bucket.valid_from,
            valid_to=bucket.valid_to,
        )
        self._session.add(row)
        self._session.flush()
        return row.bucket_id
