"""SQLAlchemy implementation of UsageRepository.

Supports both PostgreSQL (production) and SQLite (tests).
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from common.timeutil import from_epoch, to_epoch

from ..domain import CallRecord, UsageRecord
from ..models import CallRecordModel, UsageRecordModel


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def encode_cursor(epoch: int, imsi: str) -> str:
    payload = json.dumps([epoch, imsi], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_cursor(token: str) -> tuple[int, str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        data = json.loads(raw)
        if (
            isinstance(data, list)
            and len(data) == 2
            and isinstance(data[0], int)
            and isinstance(data[1], str)
        ):
            return data[0], data[1]
    except Exception as exc:
        raise ValueError("Invalid cursor format") from exc
    raise ValueError("Invalid cursor format")


MAX_TIMESTAMP_EPOCH = 253402300799
MAX_INT64 = 9223372036854775807


class SqlUsageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_records(self, records: Sequence[UsageRecord]) -> int:
        if not records:
            return 0

        # One row per (imsi, period_start), keyed as the database will see it (after clamping).
        # The contract says a repeated interval overwrites, so the last one in the batch wins.
        # PostgreSQL refuses an ON CONFLICT statement that would change one row twice.
        by_key: dict[tuple[str, datetime], dict[str, object]] = {}
        for r in records:
            period_start = from_epoch(min(r.period_start, MAX_TIMESTAMP_EPOCH))
            by_key[(r.imsi, period_start)] = {
                "imsi": r.imsi,
                "period_start": period_start,
                "period_end": from_epoch(
                    min(max(r.period_start, r.period_end), MAX_TIMESTAMP_EPOCH)
                ),
                "bytes_up": min(r.bytes_up, MAX_INT64),
                "bytes_down": min(r.bytes_down, MAX_INT64),
            }
        values = list(by_key.values())

        dialect_name = (
            self._session.bind.dialect.name if self._session.bind is not None else "postgresql"
        )
        if dialect_name == "sqlite":
            sqlite_stmt = sqlite_insert(UsageRecordModel).values(values)
            self._session.execute(
                sqlite_stmt.on_conflict_do_update(
                    index_elements=["imsi", "period_start"],
                    set_={
                        "period_end": sqlite_stmt.excluded.period_end,
                        "bytes_up": sqlite_stmt.excluded.bytes_up,
                        "bytes_down": sqlite_stmt.excluded.bytes_down,
                        "updated_at": func.now(),
                    },
                )
            )
        else:
            pg_stmt = pg_insert(UsageRecordModel).values(values)
            self._session.execute(
                pg_stmt.on_conflict_do_update(
                    index_elements=["imsi", "period_start"],
                    set_={
                        "period_end": pg_stmt.excluded.period_end,
                        "bytes_up": pg_stmt.excluded.bytes_up,
                        "bytes_down": pg_stmt.excluded.bytes_down,
                        "updated_at": func.now(),
                    },
                )
            )

        return len(values)

    def totals_by_imsi(self, from_time: datetime, to_time: datetime) -> dict[str, int]:
        rows = self._session.execute(
            select(
                UsageRecordModel.imsi,
                func.sum(UsageRecordModel.bytes_up + UsageRecordModel.bytes_down),
            )
            .where(
                UsageRecordModel.period_start >= from_time,
                UsageRecordModel.period_start < to_time,
            )
            .group_by(UsageRecordModel.imsi)
        )
        return {imsi: int(total) for imsi, total in rows}

    def query_usage(
        self,
        from_time: datetime,
        to_time: datetime,
        imsi: str | None = None,
        limit: int = 5000,
        cursor: str | None = None,
    ) -> tuple[list[UsageRecord], str | None]:
        stmt = select(UsageRecordModel).where(
            UsageRecordModel.period_start >= from_time,
            UsageRecordModel.period_start <= to_time,
        )

        if imsi is not None:
            stmt = stmt.where(UsageRecordModel.imsi == imsi)

        if cursor is not None:
            try:
                cursor_epoch, cursor_imsi = decode_cursor(cursor)
                cursor_dt = from_epoch(cursor_epoch)
                stmt = stmt.where(
                    or_(
                        UsageRecordModel.period_start > cursor_dt,
                        and_(
                            UsageRecordModel.period_start == cursor_dt,
                            UsageRecordModel.imsi > cursor_imsi,
                        ),
                    )
                )
            except ValueError:
                return [], None

        stmt = stmt.order_by(UsageRecordModel.period_start.asc(), UsageRecordModel.imsi.asc())
        stmt = stmt.limit(limit + 1)

        rows = list(self._session.scalars(stmt))
        has_next = len(rows) > limit
        page = rows[:limit]

        next_cursor = (
            encode_cursor(to_epoch(_ensure_utc(page[-1].period_start)), page[-1].imsi)
            if has_next and page
            else None
        )

        records = [
            UsageRecord(
                imsi=row.imsi,
                period_start=to_epoch(_ensure_utc(row.period_start)),
                period_end=to_epoch(_ensure_utc(row.period_end)),
                bytes_up=row.bytes_up,
                bytes_down=row.bytes_down,
            )
            for row in page
        ]

        return records, next_cursor


def _epoch_or_none(value: datetime | None) -> int | None:
    return None if value is None else to_epoch(_ensure_utc(value))


class SqlCallRepository:
    """Call records, keyed on `call_id`. PostgreSQL in production, SQLite in tests."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_calls(self, records: Sequence[CallRecord]) -> int:
        if not records:
            return 0
        # One row per call_id; the last one in the batch wins (PostgreSQL refuses an ON CONFLICT
        # statement that would change one row twice).
        by_id: dict[str, dict[str, object]] = {}
        for r in records:
            by_id[r.call_id] = {
                "call_id": r.call_id,
                "from_msisdn": r.from_msisdn,
                "to_msisdn": r.to_msisdn,
                "started_at": from_epoch(min(r.started_at, MAX_TIMESTAMP_EPOCH)),
                "answered_at": (
                    None
                    if r.answered_at is None
                    else from_epoch(min(r.answered_at, MAX_TIMESTAMP_EPOCH))
                ),
                "ended_at": from_epoch(min(r.ended_at, MAX_TIMESTAMP_EPOCH)),
                "end_reason": r.end_reason,
            }
        values = list(by_id.values())
        dialect_name = (
            self._session.bind.dialect.name if self._session.bind is not None else "postgresql"
        )
        insert = sqlite_insert if dialect_name == "sqlite" else pg_insert
        statement = insert(CallRecordModel).values(values)
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["call_id"],
                set_={
                    "from_msisdn": statement.excluded.from_msisdn,
                    "to_msisdn": statement.excluded.to_msisdn,
                    "started_at": statement.excluded.started_at,
                    "answered_at": statement.excluded.answered_at,
                    "ended_at": statement.excluded.ended_at,
                    "end_reason": statement.excluded.end_reason,
                    "updated_at": func.now(),
                },
            )
        )
        return len(values)

    def query_calls(
        self,
        from_time: datetime,
        to_time: datetime,
        msisdn: str | None = None,
        limit: int = 5000,
        cursor: str | None = None,
    ) -> tuple[list[CallRecord], str | None]:
        statement = select(CallRecordModel).where(
            CallRecordModel.started_at >= from_time, CallRecordModel.started_at <= to_time
        )
        if msisdn is not None:
            statement = statement.where(
                or_(CallRecordModel.from_msisdn == msisdn, CallRecordModel.to_msisdn == msisdn)
            )
        if cursor is not None:
            try:
                cursor_epoch, cursor_id = decode_cursor(cursor)
            except ValueError:
                return [], None
            cursor_time = from_epoch(cursor_epoch)
            statement = statement.where(
                or_(
                    CallRecordModel.started_at > cursor_time,
                    and_(
                        CallRecordModel.started_at == cursor_time,
                        CallRecordModel.call_id > cursor_id,
                    ),
                )
            )
        statement = statement.order_by(
            CallRecordModel.started_at.asc(), CallRecordModel.call_id.asc()
        ).limit(limit + 1)
        rows = list(self._session.scalars(statement))
        page = rows[:limit]
        next_cursor = (
            encode_cursor(to_epoch(_ensure_utc(page[-1].started_at)), page[-1].call_id)
            if len(rows) > limit and page
            else None
        )
        return [
            CallRecord(
                call_id=row.call_id,
                from_msisdn=row.from_msisdn,
                to_msisdn=row.to_msisdn,
                started_at=to_epoch(_ensure_utc(row.started_at)),
                answered_at=_epoch_or_none(row.answered_at),
                ended_at=to_epoch(_ensure_utc(row.ended_at)),
                end_reason=row.end_reason,
            )
            for row in page
        ], next_cursor
