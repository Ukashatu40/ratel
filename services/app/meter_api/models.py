"""SQLAlchemy model for usage records in PostgreSQL.

Table: usage_record
Primary key: id (BigInteger)
Natural unique constraint: (imsi, period_start)
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
