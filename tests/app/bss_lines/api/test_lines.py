"""End-to-end test through POST /v1/lines/activate with the fake client."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker

from app.bss_lines.api.lines import get_client
from app.bss_lines.models.lines import Customer, Line, LineAudit, Number, Plan, Sim
from app.db import Base
from tests.app.bss_lines.desk_helpers import add_staff, make_app, signed_in
from tests.app.bss_lines.fakes import FakeRatelLinkClient


@pytest.fixture
def fake_client() -> FakeRatelLinkClient:
    return FakeRatelLinkClient()


@pytest.fixture
def client_with_seeded_line(tmp_path, fake_client: FakeRatelLinkClient) -> Iterator[TestClient]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    with factory() as s:
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

    app = make_app(factory)
    app.dependency_overrides[get_client] = lambda: fake_client
    email = add_staff(factory, "agent")

    with signed_in(app, email) as client:
        client.seeded_line_id = line_id  # type: ignore[attr-defined]
        client.staff_email = email  # type: ignore[attr-defined]
        yield client


def test_activate_endpoint_returns_active(client_with_seeded_line) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    response = client_with_seeded_line.post(
        "/v1/lines/activate",
        json={"line_id": line_id, "idempotency_key": "key-1"},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "active"
    assert response.json()["line_id"] == line_id


def test_the_audit_actor_is_the_signed_in_member_whatever_the_body_says(
    client_with_seeded_line,
) -> None:
    from sqlalchemy import select

    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    client_with_seeded_line.post(
        "/v1/lines/activate",
        json={"line_id": line_id, "actor": "staff:999", "idempotency_key": "key-actor"},
    )
    factory = client_with_seeded_line.app.state.session_factory
    with factory() as session:
        actors = session.scalars(select(LineAudit.actor).where(LineAudit.line_id == line_id)).all()
    assert actors == ["staff:1"]  # the signed-in member, not the 999 the body claimed


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/v1/lines/activate"),
        ("post", "/v1/lines/suspend"),
        ("post", "/v1/lines/reinstate"),
        ("post", "/v1/lines/terminate"),
        ("get", "/v1/lines/lookup?msisdn=2348000000001"),
        ("get", "/v1/lines/lookup/1"),
    ],
)
def test_the_line_routes_refuse_a_caller_who_is_not_signed_in(
    client_with_seeded_line, fake_client: FakeRatelLinkClient, method: str, path: str
) -> None:
    anonymous = TestClient(client_with_seeded_line.app)
    body = {"line_id": 1, "idempotency_key": "k", "reason": "fraud"}
    response = getattr(anonymous, method)(path, **({"json": body} if method == "post" else {}))
    assert response.status_code == 401
    assert fake_client.calls == []  # RatelLink was not called


def test_care_may_not_terminate_a_line_but_an_admin_may(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    body = {"line_id": line_id, "idempotency_key": "k-t", "reason": "fraud"}
    refused = client_with_seeded_line.post("/v1/lines/terminate", json=body)
    assert refused.status_code == 403
    assert fake_client.calls == []

    app = client_with_seeded_line.app
    admin = signed_in(app, add_staff(app.state.session_factory, "admin"))
    assert admin.post("/v1/lines/terminate", json=body).status_code == 200


def test_activate_endpoint_calls_ratellink_once(
    client_with_seeded_line, fake_client: FakeRatelLinkClient
) -> None:
    line_id = client_with_seeded_line.seeded_line_id  # type: ignore[attr-defined]
    client_with_seeded_line.post(
        "/v1/lines/activate",
        json={"line_id": line_id, "idempotency_key": "key-1"},
    )
    assert len(fake_client.calls) == 1


# --- M-26 line lookup ------------------------------------------------------------
#
# The 100,000-row database is seeded once per module (scope="module"), with bulk
# inserts rather than per-row ORM adds.


@pytest.fixture(scope="module")
def client_with_100k_lines(tmp_path_factory) -> Iterator[TestClient]:
    """100,000 lines in the table, so a lookup is a real index probe."""
    tmp = tmp_path_factory.mktemp("100k")
    engine = create_engine(f"sqlite:///{tmp / 'big.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    with factory() as s:
        customer = Customer(
            name="Alice",
            phone="2348000000001",
            email="alice@example.test",
            id_type="NIN",
            id_number="00000000000",
            address="addr",
            kyc_status="verified",
        )
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
        s.add_all([customer, plan])
        s.flush()

        s.execute(
            insert(Sim),
            [
                {
                    "iccid": f"89{n:018d}",
                    "imsi": f"621{n:012d}",
                    "batch": "bulk",
                    "state": "in_use",
                }
                for n in range(100_000)
            ],
        )
        s.execute(
            insert(Number),
            [{"msisdn": f"234{n:010d}", "state": "in_use"} for n in range(100_000)],
        )
        s.execute(
            insert(Line),
            [
                {
                    "customer_id": customer.customer_id,
                    "iccid": f"89{n:018d}",
                    "imsi": f"621{n:012d}",
                    "msisdn": f"234{n:010d}",
                    "plan_id": plan.plan_id,
                    "state": "active",
                }
                for n in range(100_000)
            ],
        )
        s.commit()

    app = make_app(factory)
    email = add_staff(factory, "agent")

    with signed_in(app, email) as client:
        yield client


SEEDED_LINE_ID = 50001
SEEDED_MSISDN = "2340000050000"
SEEDED_ICCID = "89000000000000050000"
SEEDED_IMSI = "621000000050000"


def _timed_get(client: TestClient, url: str) -> tuple[int, float]:
    started = time.monotonic()
    response = client.get(url)
    elapsed = time.monotonic() - started
    return response.status_code, elapsed


def test_lookup_by_line_id_under_a_second(client_with_100k_lines) -> None:
    status, elapsed = _timed_get(client_with_100k_lines, f"/v1/lines/lookup/{SEEDED_LINE_ID}")
    assert status == 200
    assert elapsed < 1.0, f"line_id lookup took {elapsed:.3f}s"


def test_lookup_by_msisdn_under_a_second(client_with_100k_lines) -> None:
    status, elapsed = _timed_get(client_with_100k_lines, f"/v1/lines/lookup?msisdn={SEEDED_MSISDN}")
    assert status == 200
    assert elapsed < 1.0, f"msisdn lookup took {elapsed:.3f}s"
    body = client_with_100k_lines.get(f"/v1/lines/lookup?msisdn={SEEDED_MSISDN}").json()
    assert body["line_id"] == SEEDED_LINE_ID


def test_lookup_by_iccid_under_a_second(client_with_100k_lines) -> None:
    status, elapsed = _timed_get(client_with_100k_lines, f"/v1/lines/lookup?iccid={SEEDED_ICCID}")
    assert status == 200
    assert elapsed < 1.0, f"iccid lookup took {elapsed:.3f}s"


def test_lookup_by_imsi_under_a_second(client_with_100k_lines) -> None:
    status, elapsed = _timed_get(client_with_100k_lines, f"/v1/lines/lookup?imsi={SEEDED_IMSI}")
    assert status == 200
    assert elapsed < 1.0, f"imsi lookup took {elapsed:.3f}s"


def test_lookup_with_no_identifier_is_422(client_with_100k_lines) -> None:
    assert client_with_100k_lines.get("/v1/lines/lookup").status_code == 422


def test_lookup_with_two_identifiers_is_422(client_with_100k_lines) -> None:
    response = client_with_100k_lines.get(
        f"/v1/lines/lookup?msisdn={SEEDED_MSISDN}&imsi={SEEDED_IMSI}"
    )
    assert response.status_code == 422


def test_lookup_of_unknown_line_is_404(client_with_100k_lines) -> None:
    assert client_with_100k_lines.get("/v1/lines/lookup/99999999").status_code == 404
    assert client_with_100k_lines.get("/v1/lines/lookup?msisdn=2349999999999").status_code == 404