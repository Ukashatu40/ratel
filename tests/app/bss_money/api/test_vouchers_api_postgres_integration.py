"""The public redeem route on a real PostgreSQL, under a burst: the limit holds through HTTP."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from tests.app.bss_money.postgres import Database
from tests.app.bss_money.rating_data import seed_line
from tests.app.bss_money.vouchers_data import FACE, issue, wrong_pin

pytestmark = pytest.mark.integration

URL = "/v1/pay/vouchers/redeem"
MSISDN = "234800000" + "0001"
KEY = "test-pay-key-not-a-real-key"


def _post(client: TestClient, msisdn: str, card: str, pin: str) -> int:
    return client.post(
        URL,
        json={"msisdn": msisdn, "card_number": card, "pin": pin},
        headers={"Authorization": f"Bearer {KEY}"},
    ).status_code


def test_a_burst_of_wrong_guesses_over_http_is_stopped_at_five(db: Database) -> None:
    with Session(db.engine) as session, session.begin():
        seed_line(session, 1)
        [card] = issue(session)
    client = TestClient(
        create_app(Settings(database_url=db.url, pay_api_key=KEY))  # type: ignore[arg-type]
    )
    guess = wrong_pin(card.pin)

    with ThreadPoolExecutor(max_workers=12) as pool:
        codes = list(pool.map(lambda _: _post(client, MSISDN, card.card_number, guess), range(30)))

    assert (codes.count(400), codes.count(429)) == (5, 25)
    assert _post(client, MSISDN, card.card_number, card.pin) == 429  # even the right PIN now
    assert db.scalar("SELECT count(*) FROM ledger_entry") == 0


def test_the_same_card_posted_at_once_for_two_lines_credits_exactly_one(db: Database) -> None:
    with Session(db.engine) as session, session.begin():
        seed_line(session, 1)
        seed_line(session, 2)
        [card] = issue(session)
    client = TestClient(
        create_app(Settings(database_url=db.url, pay_api_key=KEY))  # type: ignore[arg-type]
    )
    numbers = ["234800000" + "0001", "234800000" + "0002"] * 4

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda n: _post(client, n, card.card_number, card.pin), numbers))

    assert codes.count(200) >= 1
    assert db.scalar("SELECT count(*) FROM ledger_entry") == 1  # one credit, whoever won
    assert db.scalar("SELECT COALESCE(SUM(amount_kobo), 0) FROM ledger_entry") == FACE
