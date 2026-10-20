"""Data allowances: how much data a line may still use, from which plan or bundle, until when.

Structure only here. The rating job (M-17) deducts from buckets soonest-expiry-first.

`line_id` and `source_id` are plain integers for now. TODO(M-25): foreign keys to `line`, `plan`
and `bundle` once the bss_lines schema is merged.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.bss_money.models.ledger import BIGINT_PK
from app.db import Base, TimestampMixin


class AllowanceBucket(Base, TimestampMixin):
    """Data a line may still use, from one plan or bundle, until it expires."""

    __tablename__ = "allowance_bucket"
    __table_args__ = (
        CheckConstraint("source_kind IN ('plan', 'bundle')", name="source_kind_valid"),
        CheckConstraint("data_bytes_total >= 0", name="total_not_negative"),
        CheckConstraint("data_bytes_used >= 0", name="used_not_negative"),
        CheckConstraint("data_bytes_used <= data_bytes_total", name="used_within_total"),
        CheckConstraint("valid_to > valid_from", name="valid_to_after_valid_from"),
        # The rating job takes the bucket that expires soonest.
        Index("ix_allowance_bucket_line_id_valid_to", "line_id", "valid_to"),
    )

    bucket_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    line_id: Mapped[int] = mapped_column(Integer)
    source_kind: Mapped[str] = mapped_column(String(10))
    source_id: Mapped[int] = mapped_column(Integer)
    data_bytes_total: Mapped[int] = mapped_column(BigInteger)
    data_bytes_used: Mapped[int] = mapped_column(BigInteger, server_default="0")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
