"""Act 5 with a card: a Paystack payment is settled, the plan is bought again, the line returns.

All in one run of the rating job, in the order the job runs its passes: settle, renew, judge.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.bss_money.models.payments import Payment
from app.bss_money.services.line_control import LifecycleLineControl
from app.bss_money.services.payments import settle_pending, start_payment
from app.bss_money.services.purchase import renew_plan_if_covered
from app.bss_money.services.rating_job import RatingRun, run_rating
from tests.app.bss_money.payments_fakes import FakeGateway
from tests.app.bss_money.rating_data import T0
from tests.app.bss_money.services.test_top_up_journey import Journey
from tests.app.bss_money.sqlite_database import sqlite_engine

VAT = 750
MSISDN = "2348000000001"


class CardJourney(Journey):
    def __init__(self, engine: Engine) -> None:
        super().__init__(engine)
        self.gateway = FakeGateway()

    def pay(self, amount: int) -> None:
        start_payment(
            self.payment_scope,
            self.gateway,
            msisdn=MSISDN,
            amount_kobo=amount,
            idempotency_key="k",
            callback_url="https://pay.example.invalid/",
            payer_email="pay@example.invalid",
            minimum=10_000,
            maximum=100_000_000,
        )
        with Session(self.engine) as session, session.begin():  # a minute passes
            for row in session.scalars(select(Payment)):
                row.created_at = row.created_at - timedelta(minutes=5)

    def payment_scope(self):  # type: ignore[no-untyped-def]
        from contextlib import contextmanager

        from app.bss_money.repositories.ports import PaymentRepositories
        from app.bss_money.repositories.sql import (
            SqlLedgerRepository,
            SqlLineLookup,
            SqlPaymentRepository,
        )

        @contextmanager
        def scope():  # type: ignore[no-untyped-def]
            with Session(self.engine) as session, session.begin():
                yield PaymentRepositories(
                    SqlPaymentRepository(session),
                    SqlLedgerRepository(session),
                    SqlLineLookup(session),
                )

        return scope()

    def run_all(self) -> RatingRun:
        now = datetime.now(T0.tzinfo)

        def renew(line_id: int) -> bool:
            bought = renew_plan_if_covered(
                self.purchase_scope, line_id=line_id, now=now, vat_rate_bps=VAT
            )
            return bought is not None

        return run_rating(
            self.scope,
            LifecycleLineControl(self.lines_scope, self.client),
            now=now,
            settle=lambda: settle_pending(self.payment_scope, self.gateway, now),
            renew=renew,
        )


@pytest.fixture
def card() -> Iterator[CardJourney]:
    engine = sqlite_engine()
    yield CardJourney(engine)
    engine.dispose()


def test_a_card_payment_settled_and_renewed_brings_the_line_back_in_one_run(
    card: CardJourney,
) -> None:
    line, _, _ = card.spent_line(face=1_000)
    card.pay(120_000)

    run = card.run_all()

    assert (run.payments_credited, run.lines_renewed, run.lines_restored, run.failures) == (
        1,
        1,
        1,
        0,
    )
    assert card.state(line) == "active"
    assert [c.endpoint for c in card.client.calls] == ["/data"]
    assert [k for k, _ in card.entries()] == ["top_up", "purchase", "vat"]
    assert card.balance(line) == 20_000
    assert card.run_all() == RatingRun()  # and the next run changes nothing
