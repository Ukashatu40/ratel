"""Prepaid cards and the failed attempts to redeem them.

`voucher` holds the card number (printed on the card, needed to find it) and only a hash of the PIN.
`voucher_attempt` holds the failures that count against the limit of five per card number per hour.
Neither table is ever logged. `used_by_line_id` is a foreign key to `line` (RESTRICT).
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.bss_money.models.ledger import BIGINT_PK
from app.db import Base, TimestampMixin


class Voucher(Base, TimestampMixin):
    """One prepaid card."""

    __tablename__ = "voucher"
    __table_args__ = (
        CheckConstraint(
            "state IN ('requested', 'approved', 'sent_to_printer', 'in_stock', 'on_sale', "
            "'used', 'expired', 'locked')",
            name="state_valid",
        ),
        CheckConstraint("face_value_kobo > 0", name="face_value_positive"),
        CheckConstraint("length(card_number) = 20", name="card_number_length"),
        # A used card says who used it and when; a card that is not used says neither.
        CheckConstraint(
            "(state = 'used') = (used_by_line_id IS NOT NULL AND used_at IS NOT NULL)",
            name="used_has_user",
        ),
        Index("ix_voucher_batch_state", "batch", "state"),
    )

    voucher_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    card_number: Mapped[str] = mapped_column(String(20), unique=True)
    pin_hash: Mapped[str] = mapped_column(String(200))
    face_value_kobo: Mapped[int] = mapped_column(BigInteger)
    state: Mapped[str] = mapped_column(String(20))
    batch: Mapped[str] = mapped_column(String(40))
    # TODO(PRD): whether cards expire and when. Null means they do not.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_line_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("line.line_id", ondelete="RESTRICT"), nullable=True
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoucherAttempt(Base, TimestampMixin):
    """A failed redemption attempt, for the number it was made against."""

    __tablename__ = "voucher_attempt"
    __table_args__ = (
        CheckConstraint("length(card_number) = 20", name="card_number_length"),
        Index("ix_voucher_attempt_card_number_attempted_at", "card_number", "attempted_at"),
    )

    attempt_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    # As typed, a well formed 20 digit number: it may belong to no card. Never the PIN.
    card_number: Mapped[str] = mapped_column(String(20))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
