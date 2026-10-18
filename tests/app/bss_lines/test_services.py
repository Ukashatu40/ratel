"""Tests for the activation service: exactly one call, idempotency, KYC, audit."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.bss_lines.domain import LineState
from app.bss_lines.models import Customer, Line, LineAudit, Number, Plan, Sim
from app.bss_lines.services import ActivationError, activate_line
from app.db import Base
from tests.app.bss_lines.fakes import FakeRatelLinkClient


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as s:
        yield s


def _make_line(
    session: Session,
    *,
    kyc_status: str = "verified",
    state: str = "awaiting_activation",
) -> Line:
    customer = Customer(name="Alice", phone="2348000000001", kyc_status=kyc_status)
    sim = Sim(
        iccid="8923400000000000001",
        imsi="621000000000001",
        batch="batch-1",
        state="in_use",
    )
    number = Number(msisdn="2348000000001", state="in_use")
    plan = Plan(
        name="Basic",
        speed_ul_mbps=10,
        speed_dl_mbps=20,
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


def test_activation_calls_activate_exactly_once(session: Session) -> None:
    line = _make_line(session)
    client = FakeRatelLinkClient()
    activate_line(session, client, line.line_id, actor="staff:test", idempotency_key="key-1")
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call.imsi == line.imsi
    assert call.msisdn == line.msisdn
    assert call.voice is True
    assert call.speed_ul_mbps == 10
    assert call.speed_dl_mbps == 20


def test_activation_is_refused_on_retry_after_success(session: Session) -> None:
    """After a successful activation, a second call is refused by the state machine.

    That's how idempotency is guaranteed at this layer: active -> active is not
    in the transition table. No second RatelLink call is made.
    """
    line = _make_line(session)
    client = FakeRatelLinkClient()

    # First call: activates the line.
    activate_line(session, client, line.line_id, actor="a", idempotency_key="key-1")
    assert len(client.calls) == 1

    # Second call: the state machine refuses active -> active. No second effect.
    with pytest.raises(ActivationError):
        activate_line(session, client, line.line_id, actor="a", idempotency_key="key-1")
    assert len(client.calls) == 1  # still just one


def test_fake_client_is_idempotent_on_same_key() -> None:
    """The fake client itself is idempotent: same key, one recorded call.

    This is a unit test of the fake, separate from the flow. It proves the fake
    behaves the way RatelLink promises (same body, same effect) so the flow
    tests above are exercising a realistic client.
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


def test_activation_refused_without_kyc(session: Session) -> None:
    line = _make_line(session, kyc_status="pending")
    client = FakeRatelLinkClient()
    with pytest.raises(ActivationError, match="KYC"):
        activate_line(session, client, line.line_id, actor="a", idempotency_key="k")
    assert client.calls == []


def test_activation_writes_audit_entry(session: Session) -> None:
    line = _make_line(session)
    client = FakeRatelLinkClient()
    activate_line(session, client, line.line_id, actor="alice", idempotency_key="k")
    audits = session.query(LineAudit).all()
    assert len(audits) == 1
    assert audits[0].actor == "alice"
    assert audits[0].from_state == LineState.AWAITING_ACTIVATION.value
    assert audits[0].to_state == LineState.ACTIVE.value


def test_activation_refused_from_wrong_state(session: Session) -> None:
    line = _make_line(session, state="terminated")
    client = FakeRatelLinkClient()
    with pytest.raises(ActivationError):
        activate_line(session, client, line.line_id, actor="a", idempotency_key="k")
    assert client.calls == []


def test_activation_refused_when_ratellink_errors(session: Session) -> None:
    from app.bss_lines.client import RatelLinkError

    line = _make_line(session)
    client = FakeRatelLinkClient(fail_on_activate=RatelLinkError("boom", status=503))
    with pytest.raises(RatelLinkError):
        activate_line(session, client, line.line_id, actor="a", idempotency_key="k")
    # The line's state must not have changed.
    session.refresh(line)
    assert line.state == LineState.AWAITING_ACTIVATION.value
