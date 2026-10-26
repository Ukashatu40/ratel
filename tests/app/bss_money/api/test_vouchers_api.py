"""POST /v1/pay/vouchers/redeem, end to end on SQLite: public, strict and quiet."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bss_lines.models.lines import Line
from app.bss_money.domain.vouchers import VoucherState
from app.bss_money.models.ledger import LedgerEntry
from app.bss_money.models.vouchers import VoucherAttempt
from app.bss_money.repositories.sql import SqlVoucherRepository
from app.bss_money.services.vouchers import IssuedCard, set_card_state
from app.config import Settings
from app.db import Base
from app.main import create_app
from tests.app.bss_money.rating_data import seed_line
from tests.app.bss_money.vouchers_data import FACE, issue, wrong_pin

URL = "/v1/pay/vouchers/redeem"


class Shop:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.factory = client.app.state.session_factory  # type: ignore[attr-defined]
        with self.factory() as session, session.begin():
            self.line_one = seed_line(session, 1)
            self.line_two = seed_line(session, 2)
            self.cards = issue(session, count=3)
        self.msisdn_one = "23480000" + "00001"
        self.msisdn_two = "23480000" + "00002"

    def redeem(self, msisdn: str, card: str, pin: str) -> tuple[int, dict, dict]:  # type: ignore[type-arg]
        response = self.client.post(URL, json={"msisdn": msisdn, "card_number": card, "pin": pin})
        return response.status_code, response.json(), dict(response.headers)

    def scalar(self, statement):  # type: ignore[no-untyped-def]
        with self.factory() as session:
            return session.scalar(statement)


@pytest.fixture
def shop(tmp_path: Path) -> Iterator[Shop]:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'bss.db'}")  # type: ignore[arg-type]
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        yield Shop(client)


def _card(shop: Shop, n: int = 0) -> IssuedCard:
    return shop.cards[n]


def test_a_card_is_redeemed_with_no_api_key_and_credits_the_wallet(shop: Shop) -> None:
    card = _card(shop)

    status, body, headers = shop.redeem(shop.msisdn_one, card.card_number, card.pin)

    assert (status, body) == (200, {"amount_kobo": FACE, "balance_kobo": FACE})
    assert headers["cache-control"] == "no-store"
    assert shop.scalar(select(func.sum(LedgerEntry.amount_kobo))) == FACE


def test_a_retry_gets_the_same_answer_and_credits_nothing_more(shop: Shop) -> None:
    card = _card(shop)
    first = shop.redeem(shop.msisdn_one, card.card_number, card.pin)
    second = shop.redeem(shop.msisdn_one, card.card_number, card.pin)

    assert first[:2] == second[:2] == (200, {"amount_kobo": FACE, "balance_kobo": FACE})
    assert shop.scalar(select(func.count(LedgerEntry.entry_id))) == 1


def test_every_way_of_being_refused_gets_the_identical_answer(shop: Shop) -> None:
    used, locked, fresh = shop.cards
    shop.redeem(shop.msisdn_one, used.card_number, used.pin)
    with shop.factory() as session, session.begin():
        set_card_state(SqlVoucherRepository(session), 2, VoucherState.LOCKED)

    answers = [
        shop.redeem(shop.msisdn_one, "9" * 20, fresh.pin),  # no such card
        shop.redeem(shop.msisdn_one, fresh.card_number, wrong_pin(fresh.pin)),  # wrong PIN
        shop.redeem(shop.msisdn_two, used.card_number, used.pin),  # used by another line
        shop.redeem(shop.msisdn_one, locked.card_number, locked.pin),  # lost or stolen
        shop.redeem("2348099999999", fresh.card_number, fresh.pin),  # no such phone number
    ]

    assert {(s, str(b)) for s, b, _ in answers} == {
        (400, str({"error": {"code": "voucher_refused", "message": "This card cannot be used."}}))
    }
    assert {h["cache-control"] for _, _, h in answers} == {"no-store"}
    assert shop.scalar(select(func.count(LedgerEntry.entry_id))) == 1  # only the first redemption


def test_a_terminated_line_cannot_be_topped_up_and_the_card_stays_good(shop: Shop) -> None:
    card = _card(shop)
    with shop.factory() as session, session.begin():
        session.execute(
            Line.__table__.update()
            .where(Line.line_id == shop.line_one.line_id)
            .values(state="terminated")
        )

    assert shop.redeem(shop.msisdn_one, card.card_number, card.pin)[0] == 400
    assert shop.redeem(shop.msisdn_two, card.card_number, card.pin)[0] == 200


def test_the_sixth_attempt_is_stopped_with_a_429_and_the_failures_were_kept(shop: Shop) -> None:
    card = _card(shop)
    for _ in range(5):
        assert shop.redeem(shop.msisdn_one, card.card_number, wrong_pin(card.pin))[0] == 400

    status, body, headers = shop.redeem(shop.msisdn_one, card.card_number, card.pin)

    assert status == 429
    assert body["error"]["code"] == "rate_limited"
    assert headers["retry-after"] == "3600"
    assert shop.scalar(select(func.count(VoucherAttempt.attempt_id))) == 5
    assert shop.scalar(select(func.count(LedgerEntry.entry_id))) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"msisdn": "2348000000001", "card_number": "1" * 19, "pin": "12345678901231"},
        {"msisdn": "2348000000001", "card_number": "1" * 20, "pin": "123"},
        {"msisdn": "abc", "card_number": "1" * 20, "pin": "12345678901231"},
        {"msisdn": "2348000000001", "card_number": "1" * 20},
        {"msisdn": "2348000000001", "card_number": "1" * 20, "pin": "12345678901231", "x": 1},
        {},
    ],
)
def test_badly_formed_requests_are_a_422_and_not_counted(
    shop: Shop, payload: dict[str, object]
) -> None:
    response = shop.client.post(URL, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert shop.scalar(select(func.count(VoucherAttempt.attempt_id))) == 0


def test_a_pin_with_a_wrong_check_digit_is_a_422_and_not_counted(shop: Shop) -> None:
    card = _card(shop)
    typo = card.pin[:-1] + str((int(card.pin[-1]) + 1) % 10)

    status, _, _ = shop.redeem(shop.msisdn_one, card.card_number, typo)

    assert status == 422
    assert shop.scalar(select(func.count(VoucherAttempt.attempt_id))) == 0
    assert shop.redeem(shop.msisdn_one, card.card_number, card.pin)[0] == 200


def test_a_rejected_request_never_echoes_what_was_sent(shop: Shop) -> None:
    card = _card(shop)
    response = shop.client.post(
        URL, json={"msisdn": "2348000000001", "card_number": card.card_number, "pin": card.pin[:-1]}
    )

    assert response.status_code == 422
    assert card.pin[:-1] not in response.text
    assert card.card_number not in response.text


def test_neither_the_answers_nor_the_logs_hold_a_card_number_or_pin(
    shop: Shop, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    good, other, _ = shop.cards
    texts = []
    for card, pin in ((good, good.pin), (good, good.pin), (other, wrong_pin(other.pin))):
        _, body, headers = shop.redeem(shop.msisdn_one, card.card_number, pin)
        texts.append(f"{body} {headers}")
    for _ in range(5):
        texts.append(str(shop.redeem(shop.msisdn_one, other.card_number, wrong_pin(other.pin))))

    everything = " ".join(texts) + " ".join(
        f"{r.getMessage()} {r.__dict__}" for r in caplog.records
    )
    for secret in (good.card_number, good.pin, other.card_number, other.pin):
        assert secret not in everything


def test_only_post_is_allowed(shop: Shop) -> None:
    assert shop.client.get(URL).status_code == 405


def test_the_route_is_described_in_the_contract_as_public() -> None:
    from tests.contract.helpers import operations

    [op] = [o for o in operations() if o.op_id == "bss_redeem_voucher"]
    assert (op.method, op.path) == ("POST", "/v1/pay/vouchers/redeem")
    assert op.raw["security"] == []
