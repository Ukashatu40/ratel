"""Schema rules enforced on every table in app.models.Base.metadata.

The checker runs against real metadata (empty today) and against a deliberately bad table to
prove it would catch violations once tables exist.
"""

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, MetaData, Numeric, Table
from sqlalchemy.orm import Mapped, mapped_column

import app.models  # noqa: F401  (registers all models)
from app.db import NAMING_CONVENTION, Base, TimestampMixin


def schema_violations(metadata: MetaData) -> list[str]:
    problems: list[str] = []
    for table in metadata.tables.values():
        for col in table.columns:
            if col.name.endswith("_kobo") and not isinstance(col.type, BigInteger):
                problems.append(f"{table.name}.{col.name}: money must be BIGINT kobo")
            if isinstance(col.type, Float | Numeric) and "kobo" in col.name:
                problems.append(f"{table.name}.{col.name}: no float/decimal money")
            if isinstance(col.type, DateTime) and not col.type.timezone:
                problems.append(f"{table.name}.{col.name}: timestamps must be timezone-aware")
        if table.primary_key is None or not table.primary_key.columns:
            problems.append(f"{table.name}: missing primary key")
    return problems


def test_naming_convention_is_installed() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def test_real_metadata_follows_rules() -> None:
    assert schema_violations(Base.metadata) == []


def test_checker_catches_violations() -> None:
    md = MetaData()
    Table(
        "bad",
        md,
        Column("id", Integer, primary_key=True),
        Column("amount_kobo", Float),
        Column("price_kobo", Numeric(10, 2)),
        Column("created", DateTime()),
    )
    problems = schema_violations(md)
    assert len(problems) >= 4


def test_timestamp_mixin_uses_timestamptz() -> None:
    class _Probe(Base, TimestampMixin):
        __tablename__ = "_probe_timestamp_mixin"
        id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    try:
        for name in ("created_at", "updated_at"):
            col = _Probe.__table__.columns[name]
            assert isinstance(col.type, DateTime)
            assert col.type.timezone
            assert not col.nullable
    finally:
        Base.metadata.remove(_Probe.__table__)
