"""Prepaid control of calls and texts, on SQLite (ADR 0013)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.bss_lines.models.lines import Customer, Line, Number, Plan, Sim
from app.bss_money.domain.catalogue import DEFAULT_SETTINGS
from app.bss_money.domain.entries import EntryKind, new_posting
from app.bss_money.domain.prepaid import (
    MAX_CALL_SECONDS,
    RESERVATION_GRACE_SECONDS,
    CallReason,
    SmsOutcome,
)
from app.bss_money.models.ledger import LedgerEntry
from app.bss_money.models.prepaid import CallReservation, SmsCharge
from app.bss_money.repositories.ports import PrepaidRepositories
from app.bss_money.repositories.sql import (
    SqlCatalogueRepository,
    SqlLedgerRepository,
    SqlPrepaidRepository,
)
from app.bss_money.services.prepaid import authorize_call, charge_sms, end_call
from app.db import Base
from tests.app.bss_money.sqlite_database import sqlite_engine

T0 = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
LAUNCH = T0 - timedelta(hours=1)
CALLER = "2348000010010"  # line 1
FRIEND = "2348000010011"  # line 2: on-net
BARRED = "2348000010012"  # line 3: suspended
OUTSIDE = "2348031234567"  # another network
FREE = frozenset({"112", "199"})
VAT_BPS = 750
ONNET = DEFAULT_SETTINGS.voice_onnet_kobo_per_min
OFFNET = DEFAULT_SETTINGS.voice_offnet_kobo_per_min
SMS_PRICE = DEFAULT_SETTINGS.sms_onnet_kobo

Scope = Callable[[], AbstractContextManager[PrepaidRepositories]]


@pytest.fixture
def factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = sqlite_engine(str(tmp_path / "prepaid.db"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    lines = ((CALLER, "active"), (FRIEND, "active"), (BARRED, "suspended"))
    with factory() as s, s.begin():
        customer = Customer(
            name="Ada Test",
            phone="2348000000011",
            email="ada@example.test",
            id_type="NIN",
            id_number="00000000000",
            address="1 Test Street",
            kyc_status="verified",
        )
        plan = Plan(
            name="Weekly",
            price_kobo=60_000,
            validity_days=7,
            data_bytes=3_000_000_000,
            speed_ul_mbps=5,
            speed_dl_mbps=10,
            channels="desk",
            on_exhaustion="stop",
            state="on_sale",
        )
        s.add_all([customer, plan])
        for n, (msisdn, _) in enumerate(lines, start=1):
            s.add_all(
                [
                    Sim(
                        iccid=f"892340000000000000{n}",
                        imsi=f"62100000000000{n}",
                        batch="b",
                        state="in_use",
                    ),
                    Number(msisdn=msisdn, state="in_use"),
                ]
            )
        s.flush()
        for n, (msisdn, state) in enumerate(lines, start=1):
            s.add(
                Line(
                    customer_id=customer.customer_id,
                    iccid=f"892340000000000000{n}",
                    imsi=f"62100000000000{n}",
                    msisdn=msisdn,
                    plan_id=plan.plan_id,
                    state=state,
                )
            )
    yield factory
    engine.dispose()


@pytest.fixture
def scope(factory: sessionmaker[Session]) -> Scope:
    @contextmanager
    def scope() -> Iterator[PrepaidRepositories]:
        with factory() as session, session.begin():
            yield PrepaidRepositories(
                prepaid=SqlPrepaidRepository(session),
                ledger=SqlLedgerRepository(session),
                catalogue=SqlCatalogueRepository(session),
            )

    return scope


def _top_up(factory: sessionmaker[Session], kobo: int, line_id: int = 1) -> None:
    with factory() as s, s.begin():
        SqlLedgerRepository(s).append(
            new_posting(line_id, kobo, EntryKind.TOP_UP, f"test:{line_id}:{kobo}")
        )


def _balance(factory: sessionmaker[Session], line_id: int = 1) -> int:
    with factory() as s:
        return SqlLedgerRepository(s).balance(line_id) or 0


def _authorize(
    scope: Scope,
    call_id: str = "c1",
    *,
    dialled: str = FRIEND,
    caller: str = CALLER,
    now: datetime = T0,
    charge_from: datetime | None = LAUNCH,
):  # type: ignore[no-untyped-def]
    return authorize_call(
        scope,
        call_id=call_id,
        caller=f"sip:+{caller}@ims.example",
        dialled=f"tel:+{dialled}",
        free_numbers=FREE,
        charge_from=charge_from,
        now=now,
    )


def _sms(
    scope: Scope,
    message_id: str = "m1",
    *,
    to: str = FRIEND,
    sender: str = CALLER,
    charge_from: datetime | None = LAUNCH,
) -> tuple[SmsOutcome, int]:
    return charge_sms(
        scope,
        message_id=message_id,
        sender=sender,
        recipient=to,
        vat_rate_bps=VAT_BPS,
        charge_from=charge_from,
        now=T0,
    )


# --- calls --------------------------------------------------------------------------------------


def test_a_call_is_limited_to_what_the_airtime_buys_and_that_money_is_held(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    _top_up(factory, 3 * ONNET)  # three minutes on-net
    decision = _authorize(scope)
    assert decision.allowed
    assert decision.reason is CallReason.LIMITED
    assert decision.max_seconds == 180
    with factory() as s:
        held = s.scalar(select(CallReservation))
        assert held is not None
        assert (held.state, held.reserved_kobo, held.rate_kobo_per_min) == (
            "open",
            3 * ONNET,
            ONNET,
        )
    assert _balance(factory) == 3 * ONNET  # held, not taken: the call record is charged later


def test_an_off_net_call_is_limited_at_the_off_net_rate(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    _top_up(factory, 2 * OFFNET)
    assert _authorize(scope, dialled=OUTSIDE).max_seconds == 120


def test_a_second_call_only_gets_what_the_first_one_does_not_hold(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    _top_up(factory, 3 * ONNET)
    assert _authorize(scope, "c1").max_seconds == 180
    second = _authorize(scope, "c2")
    assert not second.allowed
    assert second.reason is CallReason.INSUFFICIENT_BALANCE


def test_no_airtime_refuses_the_call(scope: Scope) -> None:
    decision = _authorize(scope)
    assert (decision.allowed, decision.reason) == (False, CallReason.INSUFFICIENT_BALANCE)


def test_the_same_call_asked_again_gets_the_same_limit_and_holds_nothing_more(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    _top_up(factory, 3 * ONNET)
    first = _authorize(scope)
    again = _authorize(scope)
    assert again == first
    with factory() as s:
        assert len(s.scalars(select(CallReservation)).all()) == 1


def test_emergency_and_free_numbers_are_never_refused(scope: Scope) -> None:
    decision = _authorize(scope, dialled="112")
    assert (decision.allowed, decision.max_seconds, decision.reason) == (
        True,
        0,
        CallReason.FREE_NUMBER,
    )
    assert _authorize(scope, dialled="112", caller=BARRED).allowed


def test_calls_are_unlimited_until_charging_starts(scope: Scope) -> None:
    for start in (None, T0 + timedelta(minutes=1)):
        decision = _authorize(scope, charge_from=start)
        assert (decision.allowed, decision.max_seconds, decision.reason) == (
            True,
            0,
            CallReason.CHARGING_OFF,
        )


def test_a_caller_that_is_not_a_line_is_not_billed(scope: Scope) -> None:
    decision = _authorize(scope, caller="2348099999999")
    assert (decision.allowed, decision.max_seconds, decision.reason) == (
        True,
        0,
        CallReason.NOT_BILLED,
    )


def test_a_suspended_line_cannot_call(factory: sessionmaker[Session], scope: Scope) -> None:
    _top_up(factory, 10_000, line_id=3)
    decision = _authorize(scope, caller=BARRED)
    assert (decision.allowed, decision.reason) == (False, CallReason.LINE_NOT_IN_SERVICE)


def test_a_huge_balance_is_still_capped(factory: sessionmaker[Session], scope: Scope) -> None:
    _top_up(factory, 100_000_000)
    assert _authorize(scope).max_seconds == MAX_CALL_SECONDS


def test_hanging_up_shrinks_the_hold_to_the_cost_and_frees_the_rest(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    _top_up(factory, 3 * ONNET)
    _authorize(scope, "c1")
    assert end_call(scope, call_id="c1", seconds=60)
    with factory() as s:
        held = s.scalar(select(CallReservation))
        assert held is not None
        assert (held.state, held.used_seconds, held.reserved_kobo) == ("ended", 60, ONNET)
    # Two minutes are free again for the next call, while the first is not charged yet.
    assert _authorize(scope, "c2").max_seconds == 120


def test_hanging_up_twice_or_without_a_hold_changes_nothing(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    _top_up(factory, 3 * ONNET)
    _authorize(scope, "c1")
    assert end_call(scope, call_id="c1", seconds=30)
    assert not end_call(scope, call_id="c1", seconds=170)
    assert not end_call(scope, call_id="unknown", seconds=10)
    with factory() as s:
        held = s.scalar(select(CallReservation))
        assert held is not None
        assert held.reserved_kobo == ONNET // 2


def test_reported_seconds_beyond_the_limit_are_not_held(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    _top_up(factory, ONNET)
    _authorize(scope)
    end_call(scope, call_id="c1", seconds=600)
    with factory() as s:
        held = s.scalar(select(CallReservation))
        assert held is not None
        assert (held.used_seconds, held.reserved_kobo) == (60, ONNET)


def test_a_hold_nobody_settled_stops_counting_after_it_expires(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    _top_up(factory, ONNET)
    assert _authorize(scope, "c1").max_seconds == 60
    assert not _authorize(scope, "c2").allowed
    later = T0 + timedelta(seconds=60 + RESERVATION_GRACE_SECONDS + 1)
    assert _authorize(scope, "c3", now=later).max_seconds == 60


# --- texts --------------------------------------------------------------------------------------


def test_a_text_to_another_ratelplus_line_is_charged_with_its_vat(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    _top_up(factory, 1_000)
    assert _sms(scope) == (SmsOutcome.CHARGED, SMS_PRICE)
    assert _balance(factory) == 1_000 - SMS_PRICE
    with factory() as s:
        entries = s.scalars(select(LedgerEntry).where(LedgerEntry.reference == "sms:m1")).all()
        assert sorted(e.kind for e in entries) == ["sms", "vat"]
        assert sum(e.amount_kobo for e in entries) == -SMS_PRICE


def test_the_same_text_asked_again_is_charged_once(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    _top_up(factory, 1_000)
    assert _sms(scope) == (SmsOutcome.CHARGED, SMS_PRICE)
    assert _sms(scope) == (SmsOutcome.CHARGED, SMS_PRICE)
    assert _balance(factory) == 1_000 - SMS_PRICE


def test_a_text_the_airtime_does_not_cover_is_refused_and_not_charged(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    _top_up(factory, SMS_PRICE - 1)
    assert _sms(scope) == (SmsOutcome.REFUSED_BALANCE, 0)
    assert _balance(factory) == SMS_PRICE - 1


def test_money_held_for_a_running_call_cannot_pay_for_a_text(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    _top_up(factory, ONNET)
    _authorize(scope)  # holds the whole N10
    assert _sms(scope) == (SmsOutcome.REFUSED_BALANCE, 0)


@pytest.mark.parametrize(
    ("to", "outcome"),
    [
        ("555", SmsOutcome.FREE_SELF_CARE),
        ("+555", SmsOutcome.FREE_SELF_CARE),
        (OUTSIDE, SmsOutcome.REFUSED_OFF_NET),
        ("+" + OUTSIDE, SmsOutcome.REFUSED_OFF_NET),
        ("32665", SmsOutcome.REFUSED_OFF_NET),  # another short code
    ],
)
def test_texts_to_555_are_free_and_texts_off_net_are_refused(
    factory: sessionmaker[Session], scope: Scope, to: str, outcome: SmsOutcome
) -> None:
    _top_up(factory, 1_000)
    assert _sms(scope, to=to) == (outcome, 0)
    assert _balance(factory) == 1_000


def test_texts_are_free_until_charging_starts_but_off_net_is_still_refused(
    factory: sessionmaker[Session], scope: Scope
) -> None:
    assert _sms(scope, "m1", charge_from=None) == (SmsOutcome.FREE_CHARGING_OFF, 0)
    assert _sms(scope, "m2", to=OUTSIDE, charge_from=None) == (SmsOutcome.REFUSED_OFF_NET, 0)


def test_a_sender_that_is_not_a_line_is_not_billed(scope: Scope) -> None:
    assert _sms(scope, sender="2348099999999") == (SmsOutcome.NOT_BILLED, 0)


def test_a_suspended_line_cannot_text(factory: sessionmaker[Session], scope: Scope) -> None:
    _top_up(factory, 1_000, line_id=3)
    assert _sms(scope, sender=BARRED) == (SmsOutcome.REFUSED_NOT_IN_SERVICE, 0)


def test_every_answer_is_recorded_once(factory: sessionmaker[Session], scope: Scope) -> None:
    _sms(scope, "m1", to=OUTSIDE)
    _sms(scope, "m1", to=OUTSIDE)
    with factory() as s:
        rows = s.scalars(select(SmsCharge)).all()
        assert [(r.message_id, r.outcome, r.line_id) for r in rows] == [
            ("m1", "refused_off_net", 1)
        ]
