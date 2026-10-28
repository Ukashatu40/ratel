"""Tests for the activation service: exactly one call, retry, KYC, audit."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.bss_lines.domain.state_machine import LineState
from app.bss_lines.models.lines import Customer, Line, LineAudit, Number, Plan, Sim
from app.bss_lines.repositories.idempotency import (
    IdempotencyConflictError,
    InMemoryIdempotencyStore,
)
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


@pytest.fixture
def store() -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore()


def _make_line(
    session: Session,
    *,
    kyc_status: str = "verified",
    state: str = "awaiting_activation",
    tag: int = 1,
) -> Line:
    customer = Customer(
        name=f"Alice {tag}",
        phone=f"2348000{tag:05d}",
        email=f"alice{tag}@example.test",
        id_type="NIN",
        id_number=f"{tag:011d}",
        address="addr",
        kyc_status=kyc_status,
    )
    sim = Sim(
        iccid=f"892340000000000{tag:04d}",
        imsi=f"62100000000{tag:04d}",
        batch="batch-1",
        state="in_use",
    )
    number = Number(msisdn=f"234800000{tag:04d}", state="in_use")
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
    assert len(client.calls) == 1

    second = activate_line(repo, client, store, line.line_id, actor="a", idempotency_key="key-1")
    assert second.line_id == first.line_id
    assert second.from_state is first.from_state
    assert second.to_state is first.to_state
    assert len(client.calls) == 1  # no second RatelLink call


def test_a_different_key_on_an_activated_line_is_refused(
    session: Session, repo: SqlLinesRepository, store: InMemoryIdempotencyStore
) -> None:
    line = _make_line(session)
    client = FakeRatelLinkClient()
    activate_line(repo, client, store, line.line_id, actor="a", idempotency_key="k1")
    with pytest.raises(ActivationError):
        activate_line(repo, client, store, line.line_id, actor="a", idempotency_key="k2")
    assert len(client.calls) == 1


def test_the_same_key_for_a_different_line_is_409(
    session: Session, repo: SqlLinesRepository, store: InMemoryIdempotencyStore
) -> None:
    """The reviewer's reproduction: line 2 with line 1's key must not return line 1's result."""
    first = _make_line(session, tag=1)
    second = _make_line(session, tag=2)
    client = FakeRatelLinkClient()

    activate_line(repo, client, store, first.line_id, actor="a", idempotency_key="k")
    assert len(client.calls) == 1

    with pytest.raises(IdempotencyConflictError):
        activate_line(repo, client, store, second.line_id, actor="a", idempotency_key="k")
    assert len(client.calls) == 1  # no second RatelLink call
    session.refresh(second)
    assert second.state == LineState.AWAITING_ACTIVATION.value  # untouched


def test_keys_are_scoped_per_endpoint(store: InMemoryIdempotencyStore) -> None:
    from app.bss_lines.repositories.idempotency import StoredResult

    store.put("/activate", "shared", StoredResult(1, "awaiting_activation", "active"))
    assert store.get("/activate", "shared") is not None
    assert store.get("/data", "shared") is None


def test_fake_client_does_not_double_record_on_same_key() -> None:
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


def test_activation_refused_without_kyc(
    session: Session, repo: SqlLinesRepository, store: InMemoryIdempotencyStore
) -> None:
    line = _make_line(session, kyc_status="pending")
    client = FakeRatelLinkClient()
    with pytest.raises(ActivationError, match="KYC"):
        activate_line(repo, client, store, line.line_id, actor="a", idempotency_key="k")
    assert client.calls == []


def test_activation_writes_audit_entry(
    session: Session, repo: SqlLinesRepository, store: InMemoryIdempotencyStore
) -> None:
    line = _make_line(session)
    client = FakeRatelLinkClient()
    activate_line(repo, client, store, line.line_id, actor="alice", idempotency_key="k")
    audits = session.query(LineAudit).all()
    assert len(audits) == 1
    assert audits[0].actor == "alice"
    assert audits[0].from_state == LineState.AWAITING_ACTIVATION.value
    assert audits[0].to_state == LineState.ACTIVE.value


def test_activation_refused_from_wrong_state(
    session: Session, repo: SqlLinesRepository, store: InMemoryIdempotencyStore
) -> None:
    line = _make_line(session, state="terminated")
    client = FakeRatelLinkClient()
    with pytest.raises(ActivationError):
        activate_line(repo, client, store, line.line_id, actor="a", idempotency_key="k")
    assert client.calls == []


def test_activation_refused_when_ratellink_errors(
    session: Session, repo: SqlLinesRepository, store: InMemoryIdempotencyStore
) -> None:
    from app.bss_lines.services.ratel_link_client import RatelLinkError

    line = _make_line(session)
    client = FakeRatelLinkClient(fail_on_activate=RatelLinkError("boom", status=503))
    with pytest.raises(RatelLinkError):
        activate_line(repo, client, store, line.line_id, actor="a", idempotency_key="k")
    session.refresh(line)
    assert line.state == LineState.AWAITING_ACTIVATION.value
