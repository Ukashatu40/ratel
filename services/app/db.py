"""Database foundation: naming convention, UTC timestamps, engine and session helpers.

Conventions (docs/DATABASE_AND_MIGRATIONS.md): explicit constraint names so migrations are
reviewable, timestamptz everywhere, money as BIGINT kobo, no float columns for money.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from sqlalchemy import DateTime, MetaData, create_engine, func
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def make_engine(url: str) -> Engine:
    """An engine whose PostgreSQL connections are always in UTC.

    Time is UTC everywhere (docs/ENGINEERING_RULES.md). Without this a connection takes the
    server's own default timezone, and a timestamp near the end of year 9999 then reads back as
    year 10000, which the driver cannot represent.
    """
    if make_url(url).get_backend_name() == "postgresql":
        return create_engine(url, pool_pre_ping=True, connect_args={"options": "-c timezone=UTC"})
    return create_engine(url, pool_pre_ping=True)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def get_session(factory: sessionmaker[Session]) -> Iterator[Session]:
    """One transaction per request: commit on success, roll back on error."""
    with factory() as session, session.begin():
        yield session
