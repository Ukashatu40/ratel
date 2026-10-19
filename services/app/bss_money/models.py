"""SQLAlchemy tables for RatelBSS: money. Used only by the repositories and by Alembic.

Three tables from the Build Plan: `wallet`, `ledger_entry` and `allowance_bucket`. Money is BIGINT
kobo. `ledger_entry` is append-only; the database refuses UPDATE, DELETE and TRUNCATE on it
(triggers in the migration, docs/adr/0009-ledger-append-only-in-the-database.md).

`line_id` is a plain integer for now. TODO(M-25): add a foreign key to `line.line_id` and to the
plan and bundle tables once the bss_lines schema is merged (bss_money may depend on bss_lines).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin

# BIGINT on PostgreSQL. SQLite only auto-numbers an INTEGER primary key, so unit tests get INTEGER.
BIGINT_PK = BigInteger().with_variant(Integer(), "sqlite")


class Wallet(Base, TimestampMixin):
    """The running balance of one line. Always equal to the sum of its ledger entries."""

    __tablename__ = "wallet"

    line_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    balance_kobo: Mapped[int] = mapped_column(BigInteger, server_default="0")
    # TODO(PRD): may a wallet go negative? Nothing here forbids it; the purchase flow decides.


class LedgerEntry(Base):
    """One movement of money. Never updated, never deleted: a correction is a new entry."""

    __tablename__ = "ledger_entry"
    __table_args__ = (
        CheckConstraint("amount_kobo <> 0", name="amount_not_zero"),
        # The same business event posted twice is one entry: a replayed payment cannot credit twice.
        UniqueConstraint("line_id", "kind", "reference"),
        Index("ix_ledger_entry_line_id", "line_id"),
    )

    entry_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    # RESTRICT: records the business must keep are never removed with their wallet.
    line_id: Mapped[int] = mapped_column(ForeignKey("wallet.line_id", ondelete="RESTRICT"))
    # Positive money in, negative money out.
    amount_kobo: Mapped[int] = mapped_column(BigInteger)
    # An EntryKind value. Not a CHECK: the list is TODO(PRD) and the domain validates it.
    kind: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AllowanceBucket(Base, TimestampMixin):
    """Data a line may still use, from one plan or bundle, until it expires.

    Structure only here. The rating job (M-17) deducts from buckets soonest-expiry-first.
    """

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
