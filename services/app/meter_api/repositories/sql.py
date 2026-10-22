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

from ..domain import UsageRecord
from ..models import UsageRecordModel


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
