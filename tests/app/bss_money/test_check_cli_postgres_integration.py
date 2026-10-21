"""The nightly check on a real PostgreSQL: it finds a corrupted balance, or says it cannot run."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.bss_money.check_cli import main as run_nightly_check
from app.bss_money.repositories.sql import SqlLedgerRepository
from app.bss_money.services.wallet_check import check_wallets
from tests.app.bss_money.postgres import Database

pytestmark = pytest.mark.integration


def test_the_nightly_check_finds_a_corrupted_balance(
    db: Database, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db.post(1, 5_000, "top_up", "pay-1")
    db.post(2, 700, "top_up", "pay-1")
    monkeypatch.setenv("DATABASE_URL", db.url)

    assert run_nightly_check([]) == 0

    with db.engine.begin() as conn:  # the wallet is a plain table: this is the corruption to catch
        conn.execute(text("UPDATE wallet SET balance_kobo = balance_kobo + 1 WHERE line_id = 2"))
    with Session(db.engine) as s:
        found = check_wallets(SqlLedgerRepository(s))
    assert [(m.line_id, m.wallet_kobo, m.ledger_kobo) for m in found] == [(2, 701, 700)]
    assert run_nightly_check([]) == 1
    assert "1 wallet(s) differ" in capsys.readouterr().err


def test_the_nightly_check_reports_that_it_could_not_run(
    db: Database, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    url = make_url(db.url).set(port=1)  # nothing listens here
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    assert run_nightly_check([]) == 2
    assert make_url(db.url).username not in capsys.readouterr().err
