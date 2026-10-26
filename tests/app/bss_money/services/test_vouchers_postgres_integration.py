"""Redeeming on a real PostgreSQL: the same card at the same moment, and guessing in parallel.

Build Plan acceptance: "a voucher redeemed twice credits exactly once", and at most five failed
attempts per number per hour, however fast they arrive.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss_money.models.vouchers import Voucher, VoucherAttempt
from app.bss_money.repositories.sql import SqlLedgerRepository, SqlVoucherRepository
from app.bss_money.services.vouchers import RedeemStatus, redeem_voucher
from tests.app.bss_money.postgres import Database
from tests.app.bss_money.vouchers_data import FACE, T0, issue, wrong_pin

pytestmark = pytest.mark.integration


def _issue(db: Database, count: int = 1):  # type: ignore[no-untyped-def]
    with Session(db.engine) as session, session.begin():
        return issue(session, count=count)


def _redeem(db: Database, card_number: str, pin: str, line: int) -> RedeemStatus:
    """One redemption in its own committed transaction, as a request would be."""
    with Session(db.engine) as session, session.begin():
        return redeem_voucher(
            SqlVoucherRepository(session),
            SqlLedgerRepository(session),
            line_id=line,
            card_number=card_number,
            pin=pin,
            now=T0,
        ).status


def _credited(db: Database) -> int:
    return int(db.scalar("SELECT COALESCE(SUM(amount_kobo), 0) FROM ledger_entry") or 0)


def test_the_same_card_redeemed_at_the_same_moment_by_different_lines_credits_once(
    db: Database,
) -> None:
    [card] = _issue(db)

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(
            pool.map(lambda line: _redeem(db, card.card_number, card.pin, line), range(1, 9))
        )

    assert outcomes.count(RedeemStatus.REDEEMED) == 1
    assert set(outcomes) <= {
        RedeemStatus.REDEEMED,
        RedeemStatus.REFUSED,
        RedeemStatus.TOO_MANY_ATTEMPTS,
    }
    assert _credited(db) == FACE
    assert db.scalar("SELECT count(*) FROM ledger_entry") == 1


def test_the_same_card_redeemed_twice_at_once_by_one_line_credits_once(db: Database) -> None:
    [card] = _issue(db)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: _redeem(db, card.card_number, card.pin, 1), range(2)))

    assert outcomes == [RedeemStatus.REDEEMED, RedeemStatus.REDEEMED]  # the second is a replay
    assert _credited(db) == FACE
    assert db.scalar("SELECT count(*) FROM ledger_entry") == 1


def test_a_fast_burst_of_wrong_guesses_is_stopped_at_five(db: Database) -> None:
    [card] = _issue(db)
    guess = wrong_pin(card.pin)

    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = list(pool.map(lambda _: _redeem(db, card.card_number, guess, 1), range(40)))

    assert outcomes.count(RedeemStatus.REFUSED) == 5  # five looked, thirty-five were stopped
    assert outcomes.count(RedeemStatus.TOO_MANY_ATTEMPTS) == 35
    assert db.scalar("SELECT count(*) FROM voucher_attempt") == 5
    assert _redeem(db, card.card_number, card.pin, 1) is RedeemStatus.TOO_MANY_ATTEMPTS
    assert _credited(db) == 0


def test_a_burst_against_a_number_that_does_not_exist_is_stopped_at_five_too(
    db: Database,
) -> None:
    [card] = _issue(db)

    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = list(pool.map(lambda _: _redeem(db, "7" * 20, card.pin, 1), range(40)))

    assert outcomes.count(RedeemStatus.REFUSED) == 5
    assert db.scalar("SELECT count(*) FROM voucher_attempt") == 5


def test_many_cards_redeemed_at_once_each_credit_their_own_value(db: Database) -> None:
    cards = _issue(db, count=12)

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(
            pool.map(lambda i: _redeem(db, cards[i].card_number, cards[i].pin, i + 1), range(12))
        )

    assert outcomes == [RedeemStatus.REDEEMED] * 12
    assert _credited(db) == 12 * FACE
    assert db.scalar("SELECT count(*) FROM ledger_entry WHERE amount_kobo = 50000") == 12


def test_the_database_itself_refuses_a_card_that_is_used_but_has_no_user(db: Database) -> None:
    _issue(db)
    with Session(db.engine) as session, pytest.raises(IntegrityError), session.begin():
        session.execute(
            Voucher.__table__.update().values(state="used")  # no used_by_line_id, no used_at
        )


def test_the_database_refuses_a_state_that_is_not_in_the_list(db: Database) -> None:
    _issue(db)
    with Session(db.engine) as session, pytest.raises(IntegrityError), session.begin():
        session.execute(Voucher.__table__.update().values(state="stolen"))


def test_downgrade_refuses_while_cards_exist_and_works_when_empty(db: Database) -> None:
    _issue(db)

    with pytest.raises(RuntimeError, match="refusing to drop voucher"):
        db.alembic("downgrade", "e3b80975b879")
    assert db.scalar("SELECT count(*) FROM voucher") == 1  # nothing was lost

    with Session(db.engine) as session, session.begin():
        session.execute(VoucherAttempt.__table__.delete())
        session.execute(Voucher.__table__.delete())
    db.alembic("downgrade", "e3b80975b879")
    assert db.scalar("SELECT to_regclass('voucher')") is None
    db.alembic("upgrade", "head")
    assert db.scalar("SELECT to_regclass('voucher')") is not None
