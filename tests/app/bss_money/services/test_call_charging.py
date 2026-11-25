"""Charging voice calls to airtime after they end, on SQLite (docs/catalogue.md)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.bss_lines.models.lines import Customer, Line, Number, Plan, Sim
from app.bss_money.domain.catalogue import DEFAULT_SETTINGS
from app.bss_money.domain.entries import EntryKind, new_posting
from app.bss_money.models.catalogue import CallCharge
from app.bss_money.models.ledger import LedgerEntry
from app.bss_money.repositories.ports import CallChargeRepositories
from app.bss_money.repositories.sql import (
    SqlCallChargeRepository,
    SqlCatalogueRepository,
    SqlLedgerRepository,
)
from app.bss_money.services.call_charging import charge_calls
from app.db import Base
from app.meter_api.models import CallRecordModel
from tests.app.bss_money.sqlite_database import sqlite_engine

T0 = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
CALLER = "2348000010010"
FRIEND = "2348000010011"  # also a Ratelplus line: on-net
OUTSIDE = "2348031234567"  # another network: off-net
VAT_BPS = 750


@pytest.fixture
def factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = sqlite_engine(str(tmp_path / "calls.db"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
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
        for n, msisdn in enumerate((CALLER, FRIEND), start=1):
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
        for n, msisdn in enumerate((CALLER, FRIEND), start=1):
            s.add(
                Line(
                    customer_id=customer.customer_id,
                    iccid=f"892340000000000000{n}",
                    imsi=f"62100000000000{n}",
                    msisdn=msisdn,
                    plan_id=plan.plan_id,
                    state="active",
                )
            )
    yield factory
    engine.dispose()


def _scope(factory: sessionmaker[Session]):  # type: ignore[no-untyped-def]
    @contextmanager
    def scope() -> Iterator[CallChargeRepositories]:
        with factory() as session, session.begin():
            yield CallChargeRepositories(
                calls=SqlCallChargeRepository(session),
                ledger=SqlLedgerRepository(session),
                catalogue=SqlCatalogueRepository(session),
            )

    return scope


def _top_up(factory: sessionmaker[Session], kobo: int) -> None:
    with factory() as s, s.begin():
        SqlLedgerRepository(s).append(new_posting(1, kobo, EntryKind.TOP_UP, f"test:{kobo}"))


def _call(
    factory: sessionmaker[Session], call_id: str, to: str, seconds: int | None, caller: str = CALLER
) -> None:
    answered = None if seconds is None else T0
    with factory() as s, s.begin():
        s.add(
            CallRecordModel(
                call_id=call_id,
                from_msisdn=caller,
                to_msisdn=to,
                started_at=T0,
                answered_at=answered,
                ended_at=T0 + timedelta(seconds=seconds or 5),
                end_reason="completed" if seconds is not None else "not_answered",
            )
        )


def _entries(factory: sessionmaker[Session]) -> list[tuple[str, int, str]]:
    with factory() as s:
        rows = s.scalars(
            select(LedgerEntry).where(LedgerEntry.kind != "top_up").order_by(LedgerEntry.entry_id)
        )
        return [(r.kind, r.amount_kobo, r.reference) for r in rows]


def _balance(factory: sessionmaker[Session]) -> int:
    with factory() as s:
        return SqlLedgerRepository(s).balance(1) or 0


def test_on_net_and_off_net_calls_are_charged_per_second_with_vat_as_its_own_entry(
    factory: sessionmaker[Session],
) -> None:
    _top_up(factory, 100_000)
    _call(factory, "a", FRIEND, 60)  # on-net minute: 10 naira
    _call(factory, "b", OUTSIDE, 30)  # off-net half minute: 10 naira
    run = charge_calls(_scope(factory), vat_rate_bps=VAT_BPS)

    assert (run.handled, run.charged, run.kobo, run.failed) == (2, 2, 2_000, 0)
    assert _balance(factory) == 98_000
    entries = _entries(factory)
    assert {k for k, _, _ in entries} == {"call", "vat"}
    assert sum(a for _, a, _ in entries) == -2_000
    assert {ref for _, _, ref in entries} == {"call:1", "call:2"}
    with factory() as s:
        charges = {c.call_record_id: c for c in s.scalars(select(CallCharge))}
    assert (
        charges[1].on_net is True
        and charges[1].rate_kobo_per_min == DEFAULT_SETTINGS.voice_onnet_kobo_per_min
    )
    assert charges[2].on_net is False and charges[2].seconds == 30


def test_a_call_is_charged_once_however_often_the_job_runs(factory: sessionmaker[Session]) -> None:
    _top_up(factory, 100_000)
    _call(factory, "a", OUTSIDE, 60)
    charge_calls(_scope(factory), vat_rate_bps=VAT_BPS)
    again = charge_calls(_scope(factory), vat_rate_bps=VAT_BPS)
    assert again.handled == 0
    assert _balance(factory) == 98_000


def test_the_wallet_stops_at_zero_and_the_rest_is_recorded_as_uncovered(
    factory: sessionmaker[Session],
) -> None:
    _top_up(factory, 500)
    _call(factory, "a", OUTSIDE, 60)  # 20 naira, only 5 in the wallet
    run = charge_calls(_scope(factory), vat_rate_bps=VAT_BPS)
    assert (run.kobo, run.uncovered_kobo) == (500, 1_500)
    assert _balance(factory) == 0
    with factory() as s:
        charge = s.scalars(select(CallCharge)).one()
    assert (charge.charged_kobo, charge.uncovered_kobo) == (500, 1_500)


def test_unanswered_calls_and_calls_from_other_networks_cost_nothing_and_are_marked_done(
    factory: sessionmaker[Session],
) -> None:
    _top_up(factory, 100_000)
    _call(factory, "a", FRIEND, None)  # nobody answered
    _call(factory, "b", CALLER, 120, caller=OUTSIDE)  # someone else's customer called us
    run = charge_calls(_scope(factory), vat_rate_bps=VAT_BPS)
    assert (run.handled, run.charged, run.kobo) == (2, 0, 0)
    assert _balance(factory) == 100_000
    with factory() as s:
        lines = {c.call_record_id: c.line_id for c in s.scalars(select(CallCharge))}
    assert lines == {1: 1, 2: None}
