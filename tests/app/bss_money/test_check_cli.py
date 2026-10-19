"""The nightly check's exit code is what a timer sees: 0 fine, 1 books differ, 2 could not run."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from app.bss_money.check_cli import main
from app.bss_money.domain.entries import new_posting
from app.bss_money.models.ledger import Wallet
from app.bss_money.repositories.sql import SqlLedgerRepository
from app.bss_money.services.ledger import post_entry
from app.db import Base


def _database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite+pysqlite:///{tmp_path / 'bss.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s, s.begin():
        post_entry(SqlLedgerRepository(s), new_posting(1, 1_000, "top_up", "pay-1"))
    engine.dispose()
    monkeypatch.setenv("DATABASE_URL", url)
    return url


def test_exit_0_when_the_books_balance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _database(tmp_path, monkeypatch)
    assert main([]) == 0
    assert "0 wallet(s) differ" in capsys.readouterr().err


def test_exit_1_when_a_balance_was_corrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    url = _database(tmp_path, monkeypatch)
    engine = create_engine(url)
    with Session(engine) as s, s.begin():
        s.execute(update(Wallet).values(balance_kobo=999))
    engine.dispose()
    assert main([]) == 1
    assert "1 wallet(s) differ" in capsys.readouterr().err


def test_exit_2_when_the_database_cannot_be_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'missing' / 'x.db'}")
    assert main([]) == 2
    err = capsys.readouterr().err
    assert "missing" not in err  # no path, host or user in the output
