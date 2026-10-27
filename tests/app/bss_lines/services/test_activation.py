"""Tests for the activation service: exactly one call, retry, KYC, audit."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.bss_lines.domain.state_machine import LineState
from app.bss_lines.models.lines import Customer, Line, Number, Plan, Sim
from app.bss_lines.repositories.idempotency import InMemoryIdempotencyStore
from app.bss_lines.repositories.sql import SqlLinesRepository
from app.bss_lines.services.activation import activate_line
from app.db import Base
from tests.app.bss_lines.fakes import FakeRatelLinkClient


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as s:
        yield s


@pytest.fixture
def repo(session: Session) -> SqlLinesRepository:
    return SqlLinesRepository(session)


@pytest.fixture
def store() -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore()


def _make_line(
    session: Session,
    *,
    kyc_status: str = "verified",
    state: str = "awaiting_activation",
) -> Line:
    customer = Customer(
        name="Alice",
        phone="2348000000001",
        email="alice@example.test",
        id_type="NIN",
        id_number="00000000000",
        address="addr",
        kyc_status=kyc_status,
    )
    sim = Sim(
        iccid="8923400000000000001",
        imsi="621000000000001",
        batch="batch-1",
        state="in_use",
    )
    number = Number(msisdn="2348000000001", state="in_use")
    plan = Plan(
        name="Basic",
        price_kobo=500,
        validity_days=30,
        data_bytes=1_000_000,
        speed_ul_mbps=10,
        speed_dl_mbps=20,
        slow_ul_mbps=1,
        slow_dl_mbps=1,
        channels="data",
        on_exhaustion="slow",
        state="on_sale",
    )
    session.add_all([customer, sim, number, plan])
    session.flush()
    line = Line(
        customer_id=customer.customer_id,
        iccid=sim.iccid,
        imsi=sim.imsi,
        msisdn=number.msisdn,
        plan_id=plan.plan_id,
        state=state,
    )
    session.add(line)
    session.commit()
    session.refresh(line)
    return line


def test_activation_calls_activate_exactly_once(
    session: Session, repo: SqlLinesRepository, store: InMemoryIdempotencyStore
) -> None:
    line = _make_line(session)
    client = FakeRatelLinkClient()
    activate_line(repo, client, store, line.line_id, actor="staff:test", idempotency_key="key-1")
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call.imsi == line.imsi
    assert call.msisdn == line.msisdn
    assert call.voice is True
    assert call.speed_ul_mbps == 10
    assert call.speed_dl_mbps == 20


def test_activation_repeat_with_same_key_returns_the_first_result(
    session: Session, repo: SqlLinesRepository, store: InMemoryIdempotencyStore
) -> None:
    """A repeat with the same Idempotency-Key returns the first result and changes nothing."""
    line = _make_line(session)
    client = FakeRatelLinkClient()

    first = activate_line(repo, client, store, line.line_id, actor="a", idempotency_key="key-1")
    assert first.to_state is LineState.ACTIVE
