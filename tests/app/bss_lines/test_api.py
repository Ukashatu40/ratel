"""End-to-end test through POST /v1/lines/activate with the fake client."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.bss_lines.api import get_client
from app.bss_lines.models import Customer, Line, Number, Plan, Sim
from app.config import Settings
from app.db import Base
from app.main import create_app
from tests.app.bss_lines.fakes import FakeRatelLinkClient


@pytest.fixture
def fake_client() -> FakeRatelLinkClient:
    return FakeRatelLinkClient()


@pytest.fixture
def client_with_seeded_line(tmp_path, fake_client: FakeRatelLinkClient) -> Iterator[TestClient]:
    # File-backed SQLite so the app's session factory and the test's seeding
    # share the same database.
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    # Seed a customer, SIM, number, plan, and an awaiting_activation line.
    with factory() as s:
        customer = Customer(name="Alice", phone="2348000000001", kyc_status="verified")
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
        s.add_all([customer, sim, number, plan])
        s.flush()
        line = Line(
            customer_id=customer.customer_id,
            iccid=sim.iccid,
            imsi=sim.imsi,
            msisdn=number.msisdn,
            plan_id=plan.plan_id,
            state="awaiting_activation",
        )
        s.add(line)
        s.commit()
        line_id = line.line_id

    app = create_app(Settings())
    app.state.session_factory = factory
    app.dependency_overrides[get_client] = lambda: fake_client

    with TestClient(app) as client:
        client.seeded_line_id = line_id  # type: ignore[attr-defined]
        yield client


def test_activate_endpoint_returns_active(client_with_seeded_line) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    response = client_with_seeded_line.post(
        "/v1/lines/activate",
        json={"line_id": line_id, "actor": "staff:test", "idempotency_key": "key-1"},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "active"
    assert response.json()["line_id"] == line_id


def test_activate_endpoint_calls_ratellink_once(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    client_with_seeded_line.post(
        "/v1/lines/activate",
        json={"line_id": line_id, "actor": "staff:test", "idempotency_key": "key-1"},
    )
    assert len(fake_client.calls) == 1
