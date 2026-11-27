"""The catalogue's settings and audit trail, and the record of each charged call.

`catalogue_setting` holds one row (id 1): airtime limits and call rates an admin sets in RatelDesk.
`catalogue_audit` is append-only: every catalogue change, who made it and why.
`call_charge` has one row per call record the charging job has handled, keyed on the record, so a
call is charged once; it is written in the same transaction as the ledger entries.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.bss_money.models.ledger import BIGINT_PK
from app.db import Base, TimestampMixin


class CatalogueSetting(Base, TimestampMixin):
    __tablename__ = "catalogue_setting"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("airtime_min_kobo >= 1", name="airtime_min_positive"),
        CheckConstraint("card_min_kobo >= airtime_min_kobo", name="card_min_not_below_airtime"),
        CheckConstraint("card_max_kobo >= card_min_kobo", name="card_max_not_below_min"),
        CheckConstraint("voice_onnet_kobo_per_min >= 0", name="onnet_not_negative"),
        CheckConstraint("voice_offnet_kobo_per_min >= 0", name="offnet_not_negative"),
        CheckConstraint("sms_onnet_kobo >= 0", name="sms_onnet_not_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    airtime_min_kobo: Mapped[int] = mapped_column(BigInteger)
    card_min_kobo: Mapped[int] = mapped_column(BigInteger)
    card_max_kobo: Mapped[int] = mapped_column(BigInteger)
    # Comma-separated whole kobo, smallest first (domain.catalogue checks them).
    airtime_presets: Mapped[str] = mapped_column(String(120))
    voice_onnet_kobo_per_min: Mapped[int] = mapped_column(BigInteger)
    voice_offnet_kobo_per_min: Mapped[int] = mapped_column(BigInteger)
    sms_onnet_kobo: Mapped[int] = mapped_column(BigInteger, server_default="200")
    # Comma-separated whole kobo, smallest first: the face values a voucher batch may have.
    voucher_values: Mapped[str] = mapped_column(
        String(120), server_default="10000,20000,50000,100000,200000"
    )


class CatalogueAudit(Base, TimestampMixin):
    __tablename__ = "catalogue_audit"
    __table_args__ = (Index("ix_catalogue_audit_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(30))  # a CatalogueAction value
    offer_kind: Mapped[str | None] = mapped_column(String(10), nullable=True)
    offer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The Idempotency-Key of a create, so a repeat finds the first one. Unique when present.
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    reason: Mapped[str] = mapped_column(String(200))
    # What changed, in words (for example "price 600.00 naira, 3 GB, 7 days, desk,sms"). No
    # personal data: catalogue values only.
    detail: Mapped[str] = mapped_column(String(500))


class CallCharge(Base, TimestampMixin):
    __tablename__ = "call_charge"
    __table_args__ = (
        CheckConstraint("seconds >= 0", name="seconds_not_negative"),
        CheckConstraint("charged_kobo >= 0", name="charged_not_negative"),
        CheckConstraint("uncovered_kobo >= 0", name="uncovered_not_negative"),
        Index("ix_call_charge_line_id", "line_id"),
    )

    call_record_id: Mapped[int] = mapped_column(
        BIGINT_PK,
        ForeignKey("call_record.id", ondelete="RESTRICT"),
        primary_key=True,
        autoincrement=False,
    )
    # The caller's line, or None when the caller is not a Ratelplus line (nothing to charge).
    line_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("line.line_id", ondelete="RESTRICT"), nullable=True
    )
    seconds: Mapped[int] = mapped_column(Integer)
    on_net: Mapped[bool] = mapped_column(Boolean)
    rate_kobo_per_min: Mapped[int] = mapped_column(BigInteger)
    charged_kobo: Mapped[int] = mapped_column(BigInteger)
    # What the wallet could not cover. Recorded so the shortfall can be reported, not lost.
    uncovered_kobo: Mapped[int] = mapped_column(BigInteger)
