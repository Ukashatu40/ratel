"""Purchases on a real PostgreSQL: no overdrawn wallet, and a retry is not charged twice."""

from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest
from sqlalchemy.orm import Session

from app.bss_money.domain.entries import new_posting
from app.bss_money.domain.purchase import OfferKind
from app.bss_money.repositories.ports import PurchaseRepositories
from app.bss_money.repositories.sql import SqlLedgerRepository, SqlPurchaseRepository
from app.bss_money.services.ledger import post_entry
from app.bss_money.services.purchase import InsufficientFunds, buy_offer
from tests.app.bss_money.postgres import Database
from tests.app.bss_money.rating_data import T0, SeededLine, seed_line

pytestmark = pytest.mark.integration


class SlowBalance(SqlLedgerRepository):
    """Reads the balance, then waits, so two purchases that are not made to take turns overlap.

    Without the line lock every purchase would read the balance before any of them paid.
    """

    def balance(self, line_id: int) -> int | None:
        value = super().balance(line_id)
        time.sleep(0.15)
        return value


def _scope(db: Database, ledger: type[SqlLedgerRepository] = SqlLedgerRepository):  # type: ignore[no-untyped-def]
    @contextmanager
    def scope() -> Iterator[PurchaseRepositories]:
        with Session(db.engine) as session, session.begin():
            yield PurchaseRepositories(SqlPurchaseRepository(session), ledger(session))

    return scope


def _line_with_wallet(db: Database, kobo: int) -> SeededLine:
    with Session(db.engine) as session, session.begin():
        line = seed_line(session)
        post_entry(SqlLedgerRepository(session), new_posting(line.line_id, kobo, "top_up", "fund"))
        return line


def _buy(
    db: Database,
    line: SeededLine,
    reference: str,
    ledger: type[SqlLedgerRepository] = SqlLedgerRepository,
) -> str:
    try:
        buy_offer(
            _scope(db, ledger),
            line_id=line.line_id,
            kind=OfferKind.PLAN,
            offer_id=line.plan_id,
            reference=reference,
            now=T0,
            vat_rate_bps=750,
        )
    except InsufficientFunds:
        return "refused"
    return "bought"


def test_a_wallet_that_covers_one_purchase_buys_exactly_one_however_many_race(db: Database) -> None:
    line = _line_with_wallet(db, 150_000)  # one plan costs 100_000

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda i: _buy(db, line, f"race-{i}", SlowBalance), range(8)))

    assert outcomes.count("bought") == 1
    assert outcomes.count("refused") == 7
    assert db.scalar("SELECT balance_kobo FROM wallet") == 50_000
    assert db.scalar("SELECT count(*) FROM allowance_bucket") == 1
    assert (
        db.scalar("SELECT COALESCE(SUM(amount_kobo), 0) FROM ledger_entry") == 50_000
    )  # never below zero


def test_the_same_reference_at_the_same_moment_is_charged_once(db: Database) -> None:
    line = _line_with_wallet(db, 500_000)

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: _buy(db, line, "one-purchase"), range(8)))

    assert outcomes == ["bought"] * 8  # every caller gets the answer; only one paid
    assert db.scalar("SELECT balance_kobo FROM wallet") == 400_000
    assert db.scalar("SELECT count(*) FROM allowance_bucket") == 1
    assert db.scalar("SELECT count(*) FROM ledger_entry WHERE kind = 'purchase'") == 1
    assert db.scalar("SELECT count(*) FROM ledger_entry WHERE kind = 'vat'") == 1
