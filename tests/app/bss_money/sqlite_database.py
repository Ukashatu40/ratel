"""An in-memory SQLite database for the unit tests of RatelBSS: money.

The real guarantees (triggers, BIGINT, concurrency, the migration) are proved on PostgreSQL in the
`*_postgres_integration.py` tests. SQLite is for the repository's SQL and the service logic only.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine, event
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
