"""Prepaid control of calls and SMS (ADR 0013).

`call_reservation`: money set aside for a call while it runs, one row per SIP Call-ID. The call's
length is limited to what the reservation buys. At hang-up it shrinks to the call's cost; when the
call record is charged it is settled. Open and ended reservations that have not expired count
against the line's available balance.
`sms_charge`: one row per text the SMSC asked about, keyed on the SMSC's message id, so a retry is
answered the same way and charged once. The ledger entries carry `sms:<message id>`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.bss_money.models.ledger import BIGINT_PK
from app.db import Base, TimestampMixin


class CallReservation(Base, TimestampMixin):
    __tablename__ = "call_reservation"
    __table_args__ = (
        CheckConstraint("max_seconds > 0", name="max_seconds_positive"),
        CheckConstraint("reserved_kobo >= 0", name="reserved_not_negative"),
        CheckConstraint("rate_kobo_per_min >= 0", name="rate_not_negative"),
        CheckConstraint("state IN ('open', 'ended', 'settled')", name="known_state"),
        Index("ix_call_reservation_line_state", "line_id", "state"),
    )

    reservation_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(128), unique=True)  # the SIP Call-ID
    line_id: Mapped[int] = mapped_column(Integer, ForeignKey("line.line_id", ondelete="RESTRICT"))
    rate_kobo_per_min: Mapped[int] = mapped_column(BigInteger)
    max_seconds: Mapped[int] = mapped_column(Integer)
    reserved_kobo: Mapped[int] = mapped_column(BigInteger)
    used_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String(10))  # open, ended (hung up), settled (charged)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SmsCharge(Base, TimestampMixin):
    __tablename__ = "sms_charge"
    __table_args__ = (
        CheckConstraint("charged_kobo >= 0", name="charged_not_negative"),
        Index("ix_sms_charge_line_id", "line_id"),
    )

    sms_charge_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(128), unique=True)
    # The sender's line, or None when the sender is not a Ratelplus line in RatelBSS.
    line_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("line.line_id", ondelete="RESTRICT"), nullable=True
    )
    outcome: Mapped[str] = mapped_column(String(30))  # an SmsOutcome value
    charged_kobo: Mapped[int] = mapped_column(BigInteger)
