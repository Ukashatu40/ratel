"""Payments made through a gateway (Paystack first), and what became of each.

One row per provider transaction. `provider_ref` is the reference we gave the provider and is
unique, so a notification delivered twice finds the same row. `public_id` is what RatelPay is
given: it cannot be guessed, because anyone who has it can read the payment's status.

`line_id` is a plain integer, like the other money tables. TODO(M-25): a foreign key to `line`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.bss_money.models.ledger import BIGINT_PK
from app.db import Base, TimestampMixin


class Payment(Base, TimestampMixin):
    __tablename__ = "payment"
    __table_args__ = (
        CheckConstraint("amount_kobo > 0", name="amount_positive"),
        CheckConstraint("currency = 'NGN'", name="currency_naira"),
        CheckConstraint("status IN ('pending', 'succeeded', 'failed')", name="status_valid"),
        # A payment is credited exactly when it succeeded.
        CheckConstraint(
            "(status = 'succeeded') = (credited_at IS NOT NULL)", name="credited_iff_succeeded"
        ),
        Index("ix_payment_status_created_at", "status", "created_at"),
    )

    payment_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True)
    line_id: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(20))
    provider_ref: Mapped[str] = mapped_column(String(64), unique=True)
    # The caller's Idempotency-Key: starting twice with the same key is one payment.
    idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    amount_kobo: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), server_default="NGN")
    status: Mapped[str] = mapped_column(String(20))
    checkout_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_txn_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
