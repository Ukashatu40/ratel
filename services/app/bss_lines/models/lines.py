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

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customer"

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    # pending | verified | rejected
    kyc_status: Mapped[str] = mapped_column(String(20))

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

    plan_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    speed_ul_mbps: Mapped[float] = mapped_column()
    speed_dl_mbps: Mapped[float] = mapped_column()
    # slow | stop
    on_exhaustion: Mapped[str] = mapped_column(String(10))
    # on_sale | retired
    state: Mapped[str] = mapped_column(String(20))


class Line(Base, TimestampMixin):
    __tablename__ = "line"

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
