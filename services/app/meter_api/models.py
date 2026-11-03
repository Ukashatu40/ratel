"""SQLAlchemy models for the meter API in PostgreSQL.

Table usage_record: primary key id; natural unique constraint (imsi, period_start).
Table call_record: primary key id; natural unique constraint call_id (the SIP Call-ID).

Call records are personal data (who called whom, and when): never logged, never in fixtures.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class UsageRecordModel(Base, TimestampMixin):
    __tablename__ = "usage_record"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    imsi: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bytes_up: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bytes_down: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("imsi", "period_start", name="uq_usage_record_imsi_period_start"),
        CheckConstraint("bytes_up >= 0", name="ck_usage_record_bytes_up_non_negative"),
        CheckConstraint("bytes_down >= 0", name="ck_usage_record_bytes_down_non_negative"),
        CheckConstraint("period_end >= period_start", name="ck_usage_record_period_valid"),
    )


# Constraint names are short: the naming convention in app/db.py adds the `ck_call_record_` prefix.
class CallRecordModel(Base, TimestampMixin):
    __tablename__ = "call_record"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    from_msisdn: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    to_msisdn: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_reason: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        UniqueConstraint("call_id", name="uq_call_record_call_id"),
        CheckConstraint(
            "end_reason IN ('completed', 'cancelled', 'declined', 'not_answered', "
            "'unavailable', 'failed')",
            name="end_reason_valid",
        ),
        CheckConstraint("ended_at >= started_at", name="period_valid"),
        CheckConstraint(
            "answered_at IS NULL OR (answered_at >= started_at AND answered_at <= ended_at)",
            name="answered_within_call",
        ),
        CheckConstraint(
            "(end_reason = 'completed') = (answered_at IS NOT NULL)",
            name="completed_means_answered",
        ),
    )
