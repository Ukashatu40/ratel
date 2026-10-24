"""SQLAlchemy models for RatelBSS: lines.

Five tables for the sell-to-activate flow, plus one audit table.
No ki or opc anywhere: those live only in RatelLink.
No money yet: billing is a later issue.

Primary keys use Integer, not BigInteger, because SQLite only auto-generates
row ids for `INTEGER PRIMARY KEY`; BigInteger primary keys would require the
application to supply the id. PostgreSQL treats Integer primary keys as SERIAL,
which is what we want for a surrogate key.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customer"

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    # Optional: receipts and notifications, not identity. The migration creates the column
    # nullable; see e3b80975b879.
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # TODO(PRD, decision 3): allowed id_type values. Demo value: NIN.
    id_type: Mapped[str] = mapped_column(String(20))
    id_number: Mapped[str] = mapped_column(String(20))  # NIN
    # TODO(PRD, decision 3): address format. Demo value: free text.
    address: Mapped[str] = mapped_column(String(500))
    # pending | verified | rejected
    kyc_status: Mapped[str] = mapped_column(String(20))
    blocked: Mapped[bool] = mapped_column(Boolean, server_default="false")

    lines: Mapped[list[Line]] = relationship(back_populates="customer")


class Sim(Base, TimestampMixin):
    __tablename__ = "sim"

    iccid: Mapped[str] = mapped_column(String(20), primary_key=True)
    imsi: Mapped[str] = mapped_column(String(15), unique=True)
    batch: Mapped[str] = mapped_column(String(40))
    # in_stock | in_use | retired
    state: Mapped[str] = mapped_column(String(20))


class Number(Base, TimestampMixin):
    __tablename__ = "number"

    msisdn: Mapped[str] = mapped_column(String(15), primary_key=True)
    # available | in_use | quarantined
    state: Mapped[str] = mapped_column(String(20))


class Plan(Base, TimestampMixin):
    __tablename__ = "plan"
    __table_args__ = (
        CheckConstraint("price_kobo >= 0", name="ck_plan_price_kobo_non_negative"),
        CheckConstraint("validity_days > 0", name="ck_plan_validity_days_positive"),
        CheckConstraint("data_bytes >= 0", name="ck_plan_data_bytes_non_negative"),
        CheckConstraint(
            "(on_exhaustion = 'slow' AND slow_ul_mbps IS NOT NULL AND slow_dl_mbps IS NOT NULL) "
            "OR (on_exhaustion <> 'slow' AND slow_ul_mbps IS NULL AND slow_dl_mbps IS NULL)",
            name="ck_plan_slow_speeds_present_only_for_slow",
        ),
    )

    plan_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    price_kobo: Mapped[int] = mapped_column(BigInteger)
    validity_days: Mapped[int] = mapped_column(Integer)
    data_bytes: Mapped[int] = mapped_column(BigInteger)
    speed_ul_mbps: Mapped[float] = mapped_column()
    speed_dl_mbps: Mapped[float] = mapped_column()
    # Present iff on_exhaustion = 'slow' (ck_plan_slow_speeds_present_only_for_slow).
    slow_ul_mbps: Mapped[float | None] = mapped_column(nullable=True)
    slow_dl_mbps: Mapped[float | None] = mapped_column(nullable=True)
    # TODO(PRD): how `channels` is represented (a list, a separate table, or
    # a comma-separated string). String for now, matching bundle.channels.
    channels: Mapped[str] = mapped_column(String(40))
    on_exhaustion: Mapped[str] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(20))


class Line(Base, TimestampMixin):
    __tablename__ = "line"
    __table_args__ = (
        Index("ix_line_msisdn", "msisdn"),
        Index("ix_line_iccid", "iccid"),
        Index("ix_line_imsi", "imsi"),
    )

    line_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customer.customer_id", ondelete="RESTRICT")
    )
    iccid: Mapped[str] = mapped_column(ForeignKey("sim.iccid", ondelete="RESTRICT"))
    imsi: Mapped[str] = mapped_column(String(15))
    msisdn: Mapped[str] = mapped_column(ForeignKey("number.msisdn", ondelete="RESTRICT"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan.plan_id", ondelete="RESTRICT"))
    # a LineState value from domain.py
    state: Mapped[str] = mapped_column(String(30))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state_before_suspension: Mapped[str | None] = mapped_column(String(30), nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="lines")
    plan: Mapped[Plan] = relationship()


class LineAudit(Base, TimestampMixin):
    """Every state change goes here: who did it, why, from and to."""

    __tablename__ = "line_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("line.line_id", ondelete="RESTRICT"))
    from_state: Mapped[str] = mapped_column(String(30))
    to_state: Mapped[str] = mapped_column(String(30))
    actor: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(String(200))


class Bundle(Base, TimestampMixin):
    __tablename__ = "bundle"
    __table_args__ = (
        CheckConstraint("price_kobo >= 0", name="ck_bundle_price_kobo_non_negative"),
        CheckConstraint("validity_days > 0", name="ck_bundle_validity_days_positive"),
        CheckConstraint("data_bytes >= 0", name="ck_bundle_data_bytes_non_negative"),
    )

    bundle_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    price_kobo: Mapped[int] = mapped_column(BigInteger)
    validity_days: Mapped[int] = mapped_column(Integer)
    data_bytes: Mapped[int] = mapped_column(BigInteger)
    channels: Mapped[str] = mapped_column(String(40))
