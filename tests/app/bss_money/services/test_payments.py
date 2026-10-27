"""Gateway payments: start, believe the provider, credit once (fake gateway, real storage)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.bss_money.domain.payments import Outcome
from app.bss_money.models.ledger import LedgerEntry
from app.bss_money.models.payments import Payment
from app.bss_money.repositories.ports import PaymentRepositories
from app.bss_money.repositories.sql import (
    SqlLedgerRepository,
    SqlLineLookup,
    SqlPaymentRepository,
)
from app.bss_money.services.payments import (
    GatewayUnavailable,
    InvalidSignature,
    PaymentRefused,
    SettleStatus,
    get_payment,
    handle_webhook,
    settle_payment,
    settle_pending,
    start_payment,
)
from tests.app.bss_money.payments_fakes import FakeGateway
from tests.app.bss_money.rating_data import T0, seed_line
from tests.app.bss_money.sqlite_database import sqlite_engine

MSISDN = "2348000000001"
MIN, MAX = 10_000, 100_000_000


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = sqlite_engine()
    with Session(engine) as session, session.begin():
        seed_line(session)  # line 1, number 2348000000001
    yield engine
    engine.dispose()


class Pay:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.gateway = FakeGateway()

    @contextmanager
    def scope(self) -> Iterator[PaymentRepositories]:
        with Session(self.engine) as session, session.begin():
            yield PaymentRepositories(
                SqlPaymentRepository(session), SqlLedgerRepository(session), SqlLineLookup(session)
            )

    def start(self, *, key: str = "key-1", msisdn: str = MSISDN, amount: int = 150_000):  # type: ignore[no-untyped-def]
        return start_payment(
            self.scope,
            self.gateway,
            msisdn=msisdn,
            amount_kobo=amount,
            idempotency_key=key,
            callback_url="https://pay.example.invalid/",
            payer_email="pay@example.invalid",
            minimum=MIN,
            maximum=MAX,
        )

    def row(self) -> Payment:
        with Session(self.engine) as session:
            return session.scalars(select(Payment)).one()

    def soon(self, seconds: int = 10) -> datetime:
        """A moment shortly after the payment was started, by the clock the database used."""
        return self.row().created_at.replace(tzinfo=T0.tzinfo) + timedelta(seconds=seconds)

    def reference(self) -> str:
        return self.row().provider_ref

    def balance(self) -> int | None:
        with Session(self.engine) as session:
            return SqlLedgerRepository(session).balance(1)

    def entries(self) -> list[tuple[str, int, str]]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(LedgerEntry.kind, LedgerEntry.amount_kobo, LedgerEntry.reference)
            )
            return [tuple(r) for r in rows]  # type: ignore[misc]


@pytest.fixture
def pay(engine: Engine) -> Pay:
    return Pay(engine)


# --- starting -------------------------------------------------------------------------------------


def test_starting_a_payment_stores_it_pending_and_returns_the_checkout_page(pay: Pay) -> None:
    view = pay.start()

    assert (view.status.value, view.amount_kobo) == ("pending", 150_000)
    row = pay.row()
    assert view.public_id == row.public_id and len(row.public_id) >= 24
    assert view.checkout_url == f"https://checkout.example.invalid/{row.provider_ref}"
    assert (row.line_id, row.provider, row.status, row.credited_at) == (1, "fake", "pending", None)
    assert pay.gateway.initialized == [
        {"amount_kobo": 150_000, "reference": row.provider_ref, "email": "pay@example.invalid"}
    ]
    assert pay.balance() is None  # nothing is credited by starting


def test_the_provider_reference_uses_only_letters_and_digits_and_is_not_the_public_id(
    pay: Pay,
) -> None:
    pay.start()
    row = pay.row()
    assert row.provider_ref.isalnum() and len(row.provider_ref) <= 64
    assert row.provider_ref != row.public_id and row.public_id not in row.provider_ref


def test_the_same_key_again_is_the_same_payment_and_the_provider_is_called_once(pay: Pay) -> None:
    first = pay.start(key="retry-1")
    again = pay.start(key="retry-1", amount=999_999)  # even if this request disagrees

    assert again == first
    assert len(pay.gateway.initialized) == 1
    assert pay.row().amount_kobo == 150_000


def test_a_new_key_is_a_new_payment(pay: Pay, engine: Engine) -> None:
    pay.start(key="a")
    pay.start(key="b")
    with Session(engine) as session:
        assert session.scalar(select(func.count(Payment.payment_id))) == 2


@pytest.mark.parametrize("amount", [0, -5, MIN - 1, MAX + 1, 1.5, "150000", True, None])
def test_an_amount_outside_the_range_or_not_whole_kobo_is_refused_and_nothing_is_stored(
    pay: Pay, engine: Engine, amount: object
) -> None:
    with pytest.raises(PaymentRefused):
        pay.start(amount=amount)  # type: ignore[arg-type]
    with Session(engine) as session:
        assert session.scalar(select(func.count(Payment.payment_id))) == 0
    assert pay.gateway.initialized == []


@pytest.mark.parametrize("msisdn", ["2348099999999", "", "abc", "234"])
def test_a_number_that_cannot_be_topped_up_is_refused_the_same_way(pay: Pay, msisdn: str) -> None:
    with pytest.raises(PaymentRefused):
        pay.start(msisdn=msisdn)
    assert pay.gateway.initialized == []


def test_a_blank_key_is_refused(pay: Pay) -> None:
    with pytest.raises(PaymentRefused):
        pay.start(key="  ")


def test_a_terminated_line_cannot_be_topped_up(pay: Pay, engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        from app.bss_lines.models.lines import Line

        session.get(Line, 1).state = "terminated"  # type: ignore[union-attr]
    with pytest.raises(PaymentRefused):
        pay.start()


def test_if_the_provider_is_down_the_payment_is_marked_failed_and_the_customer_can_try_again(
    pay: Pay,
) -> None:
    pay.gateway.fail_initialize = True
    with pytest.raises(GatewayUnavailable):
        pay.start(key="down")
    assert pay.row().status == "failed"

    pay.gateway.fail_initialize = False
    view = pay.start(key="up")  # a new attempt, a new key
    assert view.status.value == "pending" and view.checkout_url


# --- settling -------------------------------------------------------------------------------------


def test_a_verified_success_credits_the_wallet_exactly_once(pay: Pay) -> None:
    pay.start()
    reference = pay.reference()

    first = settle_payment(pay.scope, pay.gateway, reference, T0)
    second = settle_payment(pay.scope, pay.gateway, reference, T0)

    assert (first, second) == (SettleStatus.CREDITED, SettleStatus.ALREADY)
    assert pay.balance() == 150_000
    row = pay.row()
    assert (row.status, row.provider_txn_id) == ("succeeded", "txn-1")
    assert row.credited_at is not None
    assert pay.entries() == [
        ("top_up", 150_000, f"payment-{row.payment_id}")
    ]  # never the reference
    assert pay.gateway.verified == [reference]  # the second call did not even ask


def test_the_provider_is_asked_before_anything_is_credited(pay: Pay) -> None:
    pay.start()
    pay.gateway.outcome = Outcome.PENDING
    assert (
        settle_payment(pay.scope, pay.gateway, pay.reference(), pay.soon()) is SettleStatus.PENDING
    )
    assert pay.balance() is None
    assert pay.row().status == "pending"

    pay.gateway.outcome = Outcome.SUCCESS
    assert (
        settle_payment(pay.scope, pay.gateway, pay.reference(), pay.soon()) is SettleStatus.CREDITED
    )
    assert pay.balance() == 150_000


def test_a_failed_payment_is_marked_failed_and_credits_nothing(pay: Pay) -> None:
    pay.start()
    pay.gateway.outcome = Outcome.FAILED
    assert settle_payment(pay.scope, pay.gateway, pay.reference(), T0) is SettleStatus.FAILED
    assert (pay.row().status, pay.balance()) == ("failed", None)
    pay.gateway.outcome = Outcome.SUCCESS  # even if the provider later changes its mind
    assert settle_payment(pay.scope, pay.gateway, pay.reference(), T0) is SettleStatus.FAILED
    assert pay.balance() is None


@pytest.mark.parametrize(
    ("amount", "currency"),
    [(149_999, "NGN"), (150_001, "NGN"), (0, "NGN"), (150_000, "USD"), (150_000, "")],
)
def test_a_success_for_another_amount_or_currency_is_not_credited(
    pay: Pay, amount: int, currency: str
) -> None:
    pay.start()
    pay.gateway.amount_kobo, pay.gateway.currency = amount, currency

    assert settle_payment(pay.scope, pay.gateway, pay.reference(), T0) is SettleStatus.MISMATCH
    assert (pay.row().status, pay.balance()) == ("failed", None)


def test_an_unknown_reference_is_acknowledged_and_changes_nothing(pay: Pay) -> None:
    assert settle_payment(pay.scope, pay.gateway, "rp-nobody", T0) is SettleStatus.UNKNOWN
    assert pay.gateway.verified == []


def test_if_the_provider_cannot_be_asked_nothing_changes_and_the_caller_is_told(pay: Pay) -> None:
    pay.start()
    pay.gateway.fail_verify = True
    with pytest.raises(GatewayUnavailable):
        settle_payment(pay.scope, pay.gateway, pay.reference(), T0)
    assert (pay.row().status, pay.balance()) == ("pending", None)


def test_a_payment_still_pending_after_a_day_is_given_up(pay: Pay) -> None:
    pay.start()
    pay.gateway.outcome = Outcome.PENDING
    created = pay.row().created_at.replace(tzinfo=T0.tzinfo)

    assert (
        settle_payment(pay.scope, pay.gateway, pay.reference(), created + timedelta(hours=23))
        is SettleStatus.PENDING
    )
    assert (
        settle_payment(pay.scope, pay.gateway, pay.reference(), created + timedelta(hours=25))
        is SettleStatus.FAILED
    )
    assert pay.row().status == "failed"


# --- the webhook ----------------------------------------------------------------------------------


def test_an_unsigned_or_wrongly_signed_notification_is_refused_before_anything_is_read(
    pay: Pay,
) -> None:
    pay.start()
    body = f"charge:{pay.reference()}".encode()
    for signature in ("", "bad", "good-signature "):
        with pytest.raises(InvalidSignature):
            handle_webhook(pay.scope, pay.gateway, raw_body=body, signature=signature, now=T0)
    assert pay.gateway.verified == []  # not even the provider was asked
    assert pay.balance() is None


def test_a_signed_notification_makes_us_ask_the_provider_and_credits_once_however_often_it_comes(
    pay: Pay,
) -> None:
    pay.start()
    body = f"charge:{pay.reference()}".encode()

    results = [
        handle_webhook(pay.scope, pay.gateway, raw_body=body, signature="good-signature", now=T0)
        for _ in range(3)
    ]

    assert results == [SettleStatus.CREDITED, SettleStatus.ALREADY, SettleStatus.ALREADY]
    assert pay.balance() == 150_000
    assert len(pay.entries()) == 1


def test_a_notification_that_lies_is_not_believed_because_the_provider_is_asked(pay: Pay) -> None:
    pay.start()
    pay.gateway.outcome = Outcome.FAILED  # the notification says charge, the provider says no
    body = f"charge:{pay.reference()}".encode()
    assert (
        handle_webhook(pay.scope, pay.gateway, raw_body=body, signature="good-signature", now=T0)
        is SettleStatus.FAILED
    )
    assert pay.balance() is None


def test_other_events_are_acknowledged_and_ignored(pay: Pay) -> None:
    pay.start()
    assert (
        handle_webhook(
            pay.scope, pay.gateway, raw_body=b"transfer:x", signature="good-signature", now=T0
        )
        is None
    )
    assert pay.gateway.verified == []


# --- without a webhook ----------------------------------------------------------------------------


def test_pending_payments_a_minute_old_are_settled_by_the_run_and_younger_ones_are_left(
    pay: Pay, engine: Engine
) -> None:
    pay.start(key="old")
    pay.start(key="young", amount=20_000)
    with Session(engine) as session, session.begin():
        old = session.scalars(select(Payment).where(Payment.idempotency_key == "old")).one()
        old.created_at = old.created_at - timedelta(minutes=5)

    with Session(engine) as session:
        young_created = session.scalars(
            select(Payment.created_at).where(Payment.idempotency_key == "young")
        ).one()
    now = young_created.replace(tzinfo=T0.tzinfo) + timedelta(seconds=30)

    credited = settle_pending(pay.scope, pay.gateway, now)

    assert credited == 1
    assert pay.balance() == 150_000


def test_one_payment_failing_to_settle_does_not_stop_the_run(pay: Pay, engine: Engine) -> None:
    pay.start(key="a")
    pay.start(key="b", amount=20_000)
    with Session(engine) as session, session.begin():
        for row in session.scalars(select(Payment)):
            row.created_at = row.created_at - timedelta(minutes=5)
    pay.gateway.fail_verify = True
    assert (
        settle_pending(pay.scope, pay.gateway, T0) == 0
    )  # the provider is down: stops, retries next run
    pay.gateway.fail_verify = False
    assert settle_pending(pay.scope, pay.gateway, T0) == 2


def test_the_customers_status_check_settles_a_payment_that_is_old_enough_and_never_exposes_the_line(
    pay: Pay,
) -> None:
    view = pay.start()
    created = pay.row().created_at.replace(tzinfo=T0.tzinfo)

    young = get_payment(pay.scope, pay.gateway, view.public_id, created + timedelta(seconds=5))
    assert young is not None and young.status.value == "pending"
    assert pay.gateway.verified == []  # too soon to ask the provider

    later = get_payment(pay.scope, pay.gateway, view.public_id, created + timedelta(seconds=30))
    assert later is not None and later.status.value == "succeeded"
    assert pay.balance() == 150_000
    assert set(vars(later)) == {
        "public_id",
        "status",
        "amount_kobo",
        "checkout_url",
    }  # nothing about the line


def test_asking_for_a_payment_that_does_not_exist_gives_nothing(pay: Pay) -> None:
    assert get_payment(pay.scope, pay.gateway, "no-such-payment-id-at-all", T0) is None


def test_a_key_that_raced_the_first_call_gets_the_payment_without_a_second_call_to_the_provider(
    pay: Pay, engine: Engine
) -> None:
    """A pending payment with no checkout page yet: the first request is still with the provider."""
    from app.bss_money.domain.payments import new_provider_ref, new_public_id

    with pay.scope() as repositories:
        repositories.payments.add(
            public_id=new_public_id(),
            line_id=1,
            provider="fake",
            provider_ref=new_provider_ref(),
            idempotency_key="raced",
            amount_kobo=150_000,
        )

    view = pay.start(key="raced")

    assert (view.status.value, view.checkout_url) == ("pending", None)
    assert pay.gateway.initialized == []  # not called again
    assert pay.row().status == "pending"  # and never marked failed by the retry
