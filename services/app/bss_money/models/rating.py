"""Which usage records the rating job has taken from a line's allowance.

One row per usage record, with the record's id as the key: a record can be rated once, and the
database refuses a second row for it. The row is written in the same transaction that deducts the
bytes from the buckets (services/rating_job.py), so the two always agree.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.bss_money.models.ledger import BIGINT_PK
from app.db import Base, TimestampMixin


class UsageRating(Base, TimestampMixin):
    """A usage record that has been rated, and what came of it."""

    __tablename__ = "usage_rating"
    __table_args__ = (
        CheckConstraint("deducted_bytes >= 0", name="deducted_not_negative"),
        CheckConstraint("uncovered_bytes >= 0", name="uncovered_not_negative"),
        Index("ix_usage_rating_line_id", "line_id"),
    )

    usage_record_id: Mapped[int] = mapped_column(
        BIGINT_PK,
        ForeignKey("usage_record.id", ondelete="RESTRICT"),
        primary_key=True,
        autoincrement=False,
    )
    line_id: Mapped[int] = mapped_column(Integer, ForeignKey("line.line_id", ondelete="RESTRICT"))
    # Taken from the line's allowance.
    deducted_bytes: Mapped[int] = mapped_column(BigInteger)
    # Used with no allowance left to cover it. Kept so the shortfall can be reported, not lost.
    uncovered_bytes: Mapped[int] = mapped_column(BigInteger)
