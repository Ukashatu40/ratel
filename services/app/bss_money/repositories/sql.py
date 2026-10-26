"""The ledger on PostgreSQL (and SQLite in unit tests), through SQLAlchemy.

Only this module talks to the database for RatelBSS: money. It works inside the transaction the
caller owns and never commits, so a purchase can post a debit and its VAT entry together or not
at all. No rules here: those are in the domain and the services.

The rating job's storage (`SqlRatingRepository`) also reads the RatelMeter API's `usage_record`
table and the lines of bss_lines, which BSS: money is allowed to do (docs/DEPENDENCIES.md), and
writes only BSS: money's own tables.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.bss_lines.domain.state_machine import LineState
from app.bss_lines.models.lines import Line
from app.bss_money.domain.allowance import Bucket
from app.bss_money.domain.entries import Posting
from app.bss_money.domain.plans import OnExhaustion, Plan
from app.bss_money.domain.rating import RatingResult, UsageRecord
from app.bss_money.domain.wallets import WalletMismatch
from app.bss_money.models.allowance import AllowanceBucket
from app.bss_money.models.ledger import LedgerEntry, Wallet
from app.bss_money.models.rating import UsageRating
from app.bss_money.repositories.ports import (
    BalanceOutOfRange,
    DuplicateEntry,
    RatedLine,
    StoredEntry,
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


_IN_SERVICE = (LineState.ACTIVE.value, LineState.OUT_OF_DATA.value)


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
        plan = line.plan
        return RatedLine(
            line_id=line.line_id,
            imsi=line.imsi,
            state=LineState(line.state),
            plan=Plan(
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
            ),
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
