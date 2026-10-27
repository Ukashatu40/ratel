"""Tests for the activation service: exactly one call, retry, KYC, audit."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.bss_lines.domain.state_machine import LineState
from app.bss_lines.models.lines import Customer, Line, LineAudit, Number, Plan, Sim
from app.bss_lines.repositories.sql import SqlLinesRepository
from app.bss_lines.services.activation import ActivationError, activate_line
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


def test_activation_calls_activate_exactly_once(session: Session, repo: SqlLinesRepository) -> None:
    line = _make_line(session)
    client = FakeRatelLinkClient()
    activate_line(repo, client, line.line_id, actor="staff:test", idempotency_key="key-1")
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call.imsi == line.imsi
    assert call.msisdn == line.msisdn
    assert call.voice is True
    assert call.speed_ul_mbps == 10
    assert call.speed_dl_mbps == 20


def test_activation_is_refused_on_retry_after_success(
    session: Session, repo: SqlLinesRepository
) -> None:
    """A repeat call is refused by the state machine (active -> active).

    No second effect: no second RatelLink call. A repeat currently returns 400.
    TODO(idempotency, M-26): returning the *original response* for a repeated
    Idempotency-Key needs a key store, planned for M-26.
    """
    line = _make_line(session)
    client = FakeRatelLinkClient()

    activate_line(repo, client, line.line_id, actor="a", idempotency_key="key-1")
    assert len(client.calls) == 1

    with pytest.raises(ActivationError):
        activate_line(repo, client, line.line_id, actor="a", idempotency_key="key-1")
    assert len(client.calls) == 1


def test_fake_client_does_not_double_record_on_same_key() -> None:
    """A repeat call with the same key records no second call.

    TODO(idempotency, M-26): the real HTTP API currently returns 400 on a
    repeat. Returning the *original response* for a repeat comes when M-26
    adds a key store.
    """
    client = FakeRatelLinkClient()
    client.activate(
        "621000000000001",
        msisdn="2348000000001",
        speed_ul_mbps=10,
        speed_dl_mbps=20,
        voice=True,
        idempotency_key="key-1",
    )
    client.activate(
        "621000000000001",
        msisdn="2348000000001",
        speed_ul_mbps=10,
        speed_dl_mbps=20,
        voice=True,
        idempotency_key="key-1",
    )
    assert len(client.calls) == 1


def test_activation_refused_without_kyc(session: Session, repo: SqlLinesRepository) -> None:
    line = _make_line(session, kyc_status="pending")
    client = FakeRatelLinkClient()
    with pytest.raises(ActivationError, match="KYC"):
        activate_line(repo, client, line.line_id, actor="a", idempotency_key="k")
    assert client.calls == []


def test_activation_writes_audit_entry(session: Session, repo: SqlLinesRepository) -> None:
    line = _make_line(session)
    client = FakeRatelLinkClient()
    activate_line(repo, client, line.line_id, actor="alice", idempotency_key="k")
    audits = session.query(LineAudit).all()
    assert len(audits) == 1
    assert audits[0].actor == "alice"
    assert audits[0].from_state == LineState.AWAITING_ACTIVATION.value
    assert audits[0].to_state == LineState.ACTIVE.value


def test_activation_refused_from_wrong_state(session: Session, repo: SqlLinesRepository) -> None:
    line = _make_line(session, state="terminated")
    client = FakeRatelLinkClient()
    with pytest.raises(ActivationError):
        activate_line(repo, client, line.line_id, actor="a", idempotency_key="k")
    assert client.calls == []


def test_activation_refused_when_ratellink_errors(
    session: Session, repo: SqlLinesRepository
) -> None:
    from app.bss_lines.services.ratel_link_client import RatelLinkError

    line = _make_line(session)
    client = FakeRatelLinkClient(fail_on_activate=RatelLinkError("boom", status=503))
    with pytest.raises(RatelLinkError):
        activate_line(repo, client, line.line_id, actor="a", idempotency_key="k")
    session.refresh(line)
    assert line.state == LineState.AWAITING_ACTIVATION.value
