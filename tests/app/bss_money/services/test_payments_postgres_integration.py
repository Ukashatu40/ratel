"""Gateway payments on a real PostgreSQL: delivered twice at once, credited once."""

from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss_money.models.payments import Payment
from app.bss_money.repositories.ports import PaymentRepositories
from app.bss_money.repositories.sql import (
    SqlLedgerRepository,
    SqlLineLookup,
    SqlPaymentRepository,
)
from app.bss_money.services.payments import (
    SettleStatus,
    handle_webhook,
    settle_payment,
    settle_pending,
    start_payment,
)
from tests.app.bss_money.payments_fakes import FakeGateway
from tests.app.bss_money.postgres import Database
from tests.app.bss_money.rating_data import T0, seed_line

pytestmark = pytest.mark.integration


class SlowProvider(FakeGateway):
    """Answers a moment late, so every caller has seen the payment pending before any has paid."""

    def verify(self, reference: str):  # type: ignore[no-untyped-def]
        time.sleep(0.2)
        return super().verify(reference)


MSISDN = "2348000000001"


def _scope(db: Database):  # type: ignore[no-untyped-def]
    @contextmanager
    def scope() -> Iterator[PaymentRepositories]:
        with Session(db.engine) as session, session.begin():
            yield PaymentRepositories(
                SqlPaymentRepository(session), SqlLedgerRepository(session), SqlLineLookup(session)
            )

    return scope


def _start(db: Database, gateway: FakeGateway, key: str = "k"):  # type: ignore[no-untyped-def]
    return start_payment(
        _scope(db),
        gateway,
        msisdn=MSISDN,
        amount_kobo=150_000,
        idempotency_key=key,
        callback_url="https://pay.example.invalid/",
        payer_email="pay@example.invalid",
        minimum=10_000,
        maximum=100_000_000,
    )


@pytest.fixture
def started(db: Database) -> tuple[FakeGateway, str]:
    with Session(db.engine) as session, session.begin():
        seed_line(session)
    gateway = FakeGateway()
    _start(db, gateway)
    return gateway, str(db.scalar("SELECT provider_ref FROM payment"))


def test_the_same_notification_delivered_eight_times_at_once_credits_once(
    db: Database, started: tuple[FakeGateway, str]
) -> None:
    _, reference = started
    gateway = SlowProvider()
    gateway.asked[reference] = 150_000
    body = f"charge:{reference}".encode()
    now = datetime.now(T0.tzinfo)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: handle_webhook(
                    _scope(db), gateway, raw_body=body, signature="good-signature", now=now
                ),
                range(8),
            )
        )

    assert results.count(SettleStatus.CREDITED) == 1
    assert set(results) <= {SettleStatus.CREDITED, SettleStatus.ALREADY}
    assert db.scalar("SELECT balance_kobo FROM wallet") == 150_000
    assert db.scalar("SELECT count(*) FROM ledger_entry") == 1
    assert db.scalar("SELECT status FROM payment") == "succeeded"


def test_a_notification_and_the_runs_own_settling_at_the_same_moment_credit_once(
    db: Database, started: tuple[FakeGateway, str]
) -> None:
    gateway, reference = started
    with Session(db.engine) as session, session.begin():
        session.execute(
            update(Payment).values(created_at=datetime.now(T0.tzinfo) - timedelta(minutes=10))
        )
    now = datetime.now(T0.tzinfo)

    def hook() -> object:
        return settle_payment(_scope(db), gateway, reference, now)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(hook),
            pool.submit(lambda: settle_pending(_scope(db), gateway, now)),
            pool.submit(hook),
        ]
        [f.result() for f in futures]

    assert db.scalar("SELECT count(*) FROM ledger_entry") == 1
    assert db.scalar("SELECT balance_kobo FROM wallet") == 150_000


def test_the_same_key_started_eight_times_at_once_is_one_payment_and_one_call_to_the_provider(
    db: Database,
) -> None:
    with Session(db.engine) as session, session.begin():
        seed_line(session)
    gateway = FakeGateway()

    with ThreadPoolExecutor(max_workers=8) as pool:
        views = list(pool.map(lambda _: _start(db, gateway, "same-key"), range(8)))

    assert db.scalar("SELECT count(*) FROM payment") == 1
    assert len(gateway.initialized) == 1
    assert len({v.public_id for v in views}) == 1
    assert (
        db.scalar("SELECT status FROM payment") == "pending"
    )  # never marked failed by a racing retry


def test_the_database_refuses_a_succeeded_payment_that_was_never_credited(
    db: Database, started: tuple[FakeGateway, str]
) -> None:
    with Session(db.engine) as session, pytest.raises(IntegrityError), session.begin():
        session.execute(update(Payment).values(status="succeeded"))  # no credited_at


@pytest.mark.parametrize("values", [{"amount_kobo": 0}, {"status": "paid"}, {"currency": "USD"}])
def test_the_database_refuses_nonsense(
    db: Database, started: tuple[FakeGateway, str], values: dict[str, object]
) -> None:
    with Session(db.engine) as session, pytest.raises(IntegrityError), session.begin():
        session.execute(update(Payment).values(**values))


def test_downgrade_refuses_while_payments_exist_and_works_when_empty(
    db: Database, started: tuple[FakeGateway, str]
) -> None:
    with pytest.raises(RuntimeError, match="refusing to drop payment"):
        db.alembic("downgrade", "e75e719550b6")
    assert db.scalar("SELECT count(*) FROM payment") == 1

    with Session(db.engine) as session, session.begin():
        session.query(Payment).delete()
    db.alembic("downgrade", "e75e719550b6")
    assert db.scalar("SELECT to_regclass('payment')") is None
    db.alembic("upgrade", "head")
    assert db.scalar("SELECT to_regclass('payment')") is not None
