"""An in-memory SQLite database for the unit tests of RatelBSS: money.

The real guarantees (triggers, BIGINT, concurrency, the migration) are proved on PostgreSQL in
test_ledger_postgres_integration.py. SQLite here is for the service logic only.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers the tables)
from app.db import Base


def sqlite_engine() -> Engine:
    """SQLite that behaves for savepoints and foreign keys, as the SQLAlchemy docs prescribe."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None  # let SQLAlchemy emit BEGIN and SAVEPOINT
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    @event.listens_for(engine, "begin")
    def _on_begin(connection: Any) -> None:
        connection.exec_driver_sql("BEGIN")

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session() -> Iterator[Session]:
    engine = sqlite_engine()
    with Session(engine) as s:
        yield s
    engine.dispose()
