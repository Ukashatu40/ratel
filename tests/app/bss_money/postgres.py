"""A real PostgreSQL for the integration tests of RatelBSS: money.

Set RATEL_TEST_POSTGRES_URI to a connection string that may create and drop databases. Each test
gets its own database, built by the real migrations and dropped afterwards, so nothing here touches
an existing database. Without the variable the tests are skipped.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.bss_money.domain.entries import new_posting
from app.bss_money.repositories.sql import SqlLedgerRepository
from app.bss_money.services.ledger import PostingResult, post_entry

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "services/app/alembic.ini"
ADMIN_URL = os.environ.get("RATEL_TEST_POSTGRES_URI")


class Database:
    """A fresh database built by the real migration."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.engine: Engine = create_engine(url, pool_size=20, max_overflow=0)

    def alembic(self, direction: str, revision: str) -> None:
        previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = self.url
        try:
            cfg = Config(str(ALEMBIC_INI))
            (command.upgrade if direction == "upgrade" else command.downgrade)(cfg, revision)
        finally:
            if previous is None:
                del os.environ["DATABASE_URL"]
            else:
                os.environ["DATABASE_URL"] = previous

    def post(self, line: int, amount: int, kind: str, reference: str) -> PostingResult:
        """Post one entry in its own committed transaction, through the service."""
        with Session(self.engine) as session, session.begin():
            return post_entry(
                SqlLedgerRepository(session), new_posting(line, amount, kind, reference)
            )

    def run(self, sql: str, **params: object) -> None:
        """Run one statement in its own committed transaction (values go in `params`)."""
        with self.engine.begin() as conn:
            conn.execute(text(sql), params)

    def rows(self, sql: str) -> list[tuple[object, ...]]:
        with self.engine.connect() as conn:
            return [tuple(r) for r in conn.execute(text(sql))]

    def scalar(self, sql: str) -> object:
        with self.engine.connect() as conn:
            return conn.execute(text(sql)).scalar()


@pytest.fixture
def db() -> Iterator[Database]:
    if not ADMIN_URL:
        pytest.skip("RATEL_TEST_POSTGRES_URI is not set")
    name = f"ratel_money_{secrets.token_hex(4)}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    database = Database(url)
    database.alembic("upgrade", "head")
    try:
        yield database
    finally:
        database.engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
