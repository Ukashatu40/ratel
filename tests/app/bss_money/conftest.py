"""Shared fixtures for the tests of RatelBSS: money."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from tests.app.bss_money.postgres import db  # noqa: F401  (the PostgreSQL fixture)
from tests.app.bss_money.sqlite_database import sqlite_engine


@pytest.fixture
def session() -> Iterator[Session]:
    engine = sqlite_engine()
    with Session(engine) as s:
        yield s
    engine.dispose()
