"""Tests for the suspend, reinstate and terminate flows."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.bss_lines.domain.state_machine import LineState
from app.bss_lines.models.lines import Customer, Line, LineAudit, Number, Plan, Sim
from app.bss_lines.repositories.sql import SqlLinesRepository
from app.bss_lines.services.lifecycle import (
    LifecycleError,
    reinstate_line,
    suspend_line,
    terminate_line,
)
from app.db import Base
from tests.app.bss_lines.fakes import (
    FakeRatelLinkClient,
    RecordedActivate,
    RecordedData,
    RecordedDeactivate,
)


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
    state: str = "active",
    state_before_suspension: str | None = None,
    on_exhaustion: str = "slow",
) -> Line:
    customer = Customer(
        name="Alice",
        phone="2348000000001",
        email="alice@example.test",
        id_type="NIN",
        id_number="00000000000",
        address="addr",
        kyc_status="verified",
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
        on_exhaustion=on_exhaustion,
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
        state_before_suspension=state_before_suspension,
    )
    session.add(line)
    session.commit()
    session.refresh(line)
    return line


def _audits(session: Session) -> list[LineAudit]:
    return list(session.query(LineAudit).all())


# --- suspend --------------------------------------------------------------------


def test_suspend_from_active(session: Session, repo: SqlLinesRepository) -> None:
    line = _make_line(session, state=LineState.ACTIVE.value)
    client = FakeRatelLinkClient()
    result = suspend_line(
        repo, client, line.line_id, actor="alice", reason="fraud", idempotency_key="k1"
    )
    assert result.from_state is LineState.ACTIVE
    assert result.to_state is LineState.SUSPENDED
    assert line.state == LineState.SUSPENDED.value
    assert line.state_before_suspension == LineState.ACTIVE.value
    assert len(client.calls) == 1
    assert isinstance(client.calls[0], RecordedDeactivate)
    assert client.calls[0].endpoint == "/deactivate"
    audits = _audits(session)
    assert len(audits) == 1
    assert audits[0].from_state == LineState.ACTIVE.value
    assert audits[0].to_state == LineState.SUSPENDED.value
    assert audits[0].actor == "alice"
    assert audits[0].reason == "fraud"


def test_suspend_from_out_of_data_records_previous(
    session: Session, repo: SqlLinesRepository
) -> None:
    line = _make_line(session, state=LineState.OUT_OF_DATA.value)
    client = FakeRatelLinkClient()
    suspend_line(
        repo, client, line.line_id, actor="a", reason="customer_request", idempotency_key="k"
    )
    assert line.state == LineState.SUSPENDED.value
    assert line.state_before_suspension == LineState.OUT_OF_DATA.value


def test_suspend_refuses_from_awaiting_activation(
    session: Session, repo: SqlLinesRepository
) -> None:
    line = _make_line(session, state=LineState.AWAITING_ACTIVATION.value)
    client = FakeRatelLinkClient()
    with pytest.raises(LifecycleError):
        suspend_line(repo, client, line.line_id, actor="a", reason="fraud", idempotency_key="k")
    assert line.state == LineState.AWAITING_ACTIVATION.value
    assert client.calls == []


def test_suspend_reason_text_is_recorded(session: Session, repo: SqlLinesRepository) -> None:
    line = _make_line(session)
    client = FakeRatelLinkClient()
    suspend_line(
        repo,
        client,
        line.line_id,
        actor="a",
        reason="lost_sim",
        reason_text="phone stolen",
        idempotency_key="k",
    )
    assert _audits(session)[0].reason == "lost_sim: phone stolen"


# --- reinstate -----------------------------------------------------------------


def test_reinstate_from_active_suspension(session: Session, repo: SqlLinesRepository) -> None:
    line = _make_line(
        session,
        state=LineState.SUSPENDED.value,
        state_before_suspension=LineState.ACTIVE.value,
    )
    client = FakeRatelLinkClient()
    result = reinstate_line(
        repo, client, line.line_id, actor="a", reason="customer_request", idempotency_key="k"
    )
    assert result.from_state is LineState.SUSPENDED
    assert result.to_state is LineState.ACTIVE
    assert line.state == LineState.ACTIVE.value
    assert line.state_before_suspension is None
    assert len(client.calls) == 1
    assert isinstance(client.calls[0], RecordedActivate)


def test_reinstate_from_out_of_data_suspension_calls_activate_then_data(
    session: Session, repo: SqlLinesRepository
) -> None:
    line = _make_line(
        session,
        state=LineState.SUSPENDED.value,
        state_before_suspension=LineState.OUT_OF_DATA.value,
        on_exhaustion="slow",
    )
    client = FakeRatelLinkClient()
    reinstate_line(repo, client, line.line_id, actor="a", reason="fraud", idempotency_key="k")
    assert line.state == LineState.OUT_OF_DATA.value
    assert line.state_before_suspension is None
    assert len(client.calls) == 2
    assert isinstance(client.calls[0], RecordedActivate)
    assert isinstance(client.calls[1], RecordedData)
    assert client.calls[1].mode == "slow"
    assert client.calls[1].speed_ul_mbps == 1
    assert client.calls[1].speed_dl_mbps == 1


def test_reinstate_refuses_when_state_before_suspension_is_missing(
    session: Session, repo: SqlLinesRepository
) -> None:
    line = _make_line(session, state=LineState.SUSPENDED.value, state_before_suspension=None)
    client = FakeRatelLinkClient()
    with pytest.raises(LifecycleError):
        reinstate_line(repo, client, line.line_id, actor="a", reason="fraud", idempotency_key="k")
    assert client.calls == []


def test_reinstate_refuses_from_wrong_state(session: Session, repo: SqlLinesRepository) -> None:
    line = _make_line(session, state=LineState.ACTIVE.value)
    client = FakeRatelLinkClient()
    with pytest.raises(LifecycleError):
        reinstate_line(repo, client, line.line_id, actor="a", reason="fraud", idempotency_key="k")


# --- terminate -----------------------------------------------------------------


def test_terminate_from_active(session: Session, repo: SqlLinesRepository) -> None:
    line = _make_line(session, state=LineState.ACTIVE.value)
    client = FakeRatelLinkClient()
    result = terminate_line(
        repo, client, line.line_id, actor="a", reason="non_payment", idempotency_key="k"
    )
    assert result.to_state is LineState.TERMINATED
    assert line.state == LineState.TERMINATED.value
    sim = session.get(Sim, line.iccid)
    assert sim is not None and sim.state == "retired"
    number = session.get(Number, line.msisdn)
    assert number is not None and number.state == "in_use"  # quarantine is compliance's call
    assert len(client.calls) == 1
    assert isinstance(client.calls[0], RecordedDeactivate)


def test_terminate_from_suspended(session: Session, repo: SqlLinesRepository) -> None:
    line = _make_line(
        session,
        state=LineState.SUSPENDED.value,
        state_before_suspension=LineState.ACTIVE.value,
    )
    client = FakeRatelLinkClient()
    terminate_line(repo, client, line.line_id, actor="a", reason="fraud", idempotency_key="k")
    assert line.state == LineState.TERMINATED.value
    assert line.state_before_suspension is None  # cleared on the way out of suspended


def test_terminate_refuses_on_terminated(session: Session, repo: SqlLinesRepository) -> None:
    line = _make_line(session, state=LineState.TERMINATED.value)
    client = FakeRatelLinkClient()
    with pytest.raises(LifecycleError):
        terminate_line(repo, client, line.line_id, actor="a", reason="fraud", idempotency_key="k")
    assert client.calls == []


def test_terminate_writes_audit(session: Session, repo: SqlLinesRepository) -> None:
    line = _make_line(session, state=LineState.ACTIVE.value)
    client = FakeRatelLinkClient()
    terminate_line(repo, client, line.line_id, actor="bob", reason="fraud", idempotency_key="k")
    audits = _audits(session)
    assert len(audits) == 1
    assert audits[0].from_state == LineState.ACTIVE.value
    assert audits[0].to_state == LineState.TERMINATED.value
    assert audits[0].actor == "bob"
