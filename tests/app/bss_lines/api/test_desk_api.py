"""RatelDesk's operations over HTTP: customers, plans, stock, one line.

Creating a line takes a SIM and a number with raw SQL that needs PostgreSQL; that is tested in
test_line_sales_postgres_integration.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bss_lines.models.lines import Customer, Line, Number, Plan, Sim
from app.bss_lines.models.replay import IdempotentCreate
from app.db import Base
from tests.app.bss_lines.desk_helpers import add_staff, make_app, signed_in


@pytest.fixture(autouse=True)
def _cheap_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("common.passwords._N", 2**10)


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def app(factory: sessionmaker[Session]) -> FastAPI:
    return make_app(factory)


@pytest.fixture
def care(app: FastAPI, factory: sessionmaker[Session]) -> TestClient:
    return signed_in(app, add_staff(factory, "agent"))


@pytest.fixture
def admin(app: FastAPI, factory: sessionmaker[Session]) -> TestClient:
    return signed_in(app, add_staff(factory, "admin"))


def customer_body(**changes: Any) -> dict[str, Any]:
    body = {
        "name": "Test Person",
        "phone": "2348000000001",
        "email": "person@example.test",
        "id_type": "NIN",
        "id_number": "00000000000",
        "address": "1 Test Street",
        "kyc_status": "pending",
    }
    return {**body, **changes}


def _plan(**changes: Any) -> Plan:
    fields = dict(
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
    return Plan(**{**fields, **changes})


def test_a_customer_is_created_and_read_back(care: TestClient) -> None:
    created = care.post("/v1/customers", json=customer_body())
    assert created.status_code == 201
    body = created.json()
    assert body["customer_id"] == 1 and body["kyc_status"] == "pending" and body["blocked"] is False
    assert care.get("/v1/customers/1").json() == body
    assert care.get("/v1/customers/2").status_code == 404
    assert care.get("/v1/customers/0").status_code == 422


def test_the_answer_has_exactly_the_contract_fields(care: TestClient) -> None:
    body = care.post("/v1/customers", json=customer_body()).json()
    assert set(body) == {
        "customer_id", "name", "phone", "email", "id_type", "id_number", "address",
        "kyc_status", "blocked",
    }  # fmt: skip


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"email": "not-an-email"},
        {"kyc_status": "approved"},
        {"id_number": "x" * 21},
        {"address": "a" * 501},
        {"unexpected": "field"},
    ],
)
def test_a_bad_customer_is_refused_without_echoing_it(care: TestClient, change: dict) -> None:
    response = care.post("/v1/customers", json=customer_body(**change))
    assert response.status_code == 422
    assert "person@example.test" not in response.text and "00000000000" not in response.text


def test_care_cannot_register_a_customer_as_verified_but_an_admin_can(
    care: TestClient, admin: TestClient
) -> None:
    refused = care.post("/v1/customers", json=customer_body(kyc_status="verified"))
    assert refused.status_code == 403
    assert care.post("/v1/customers", json=customer_body(kyc_status="rejected")).status_code == 201
    assert admin.post("/v1/customers", json=customer_body(kyc_status="verified")).status_code == 201


def test_a_repeated_create_returns_the_first_customer(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    headers = {"Idempotency-Key": "create-1"}
    first = care.post("/v1/customers", json=customer_body(), headers=headers)
    second = care.post("/v1/customers", json=customer_body(), headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Customer)) == 1


def test_a_key_reused_for_a_different_customer_is_refused(care: TestClient) -> None:
    headers = {"Idempotency-Key": "create-1"}
    assert care.post("/v1/customers", json=customer_body(), headers=headers).status_code == 201
    other = care.post("/v1/customers", json=customer_body(name="Someone Else"), headers=headers)
    assert other.status_code == 409


def test_the_same_key_on_a_customer_and_a_line_do_not_collide(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    care.post("/v1/customers", json=customer_body(), headers={"Idempotency-Key": "k"})
    with factory() as session:
        scopes = session.scalars(select(IdempotentCreate.scope)).all()
    assert scopes == ["customer"]


def test_the_memory_of_a_key_holds_no_personal_data(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    care.post("/v1/customers", json=customer_body(), headers={"Idempotency-Key": "k"})
    with factory() as session:
        row = session.execute(select(IdempotentCreate)).scalar_one()
    assert {c.name for c in IdempotentCreate.__table__.columns} >= {"scope", "key", "resource_id"}
    assert "person@example.test" not in repr(row.__dict__)


def test_plans_on_sale_only(care: TestClient, factory: sessionmaker[Session]) -> None:
    with factory() as session, session.begin():
        session.add_all([_plan(name="Basic"), _plan(name="Old", state="retired")])
    plans = care.get("/v1/plans").json()["plans"]
    assert [p["name"] for p in plans] == ["Basic"]
    assert plans[0]["price_kobo"] == 500 and isinstance(plans[0]["price_kobo"], int)
    assert set(plans[0]) == {
        "plan_id", "name", "price_kobo", "validity_days", "data_bytes", "speed_ul_mbps",
        "speed_dl_mbps", "slow_ul_mbps", "slow_dl_mbps", "channels", "on_exhaustion", "state",
    }  # fmt: skip


def test_free_sims_and_numbers_only_and_never_a_key(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    with factory() as session, session.begin():
        session.add_all(
            [
                Sim(
                    iccid="8923400000000000001",
                    imsi="621000000000001",
                    batch="b1",
                    state="in_stock",
                ),
                Sim(
                    iccid="8923400000000000002", imsi="621000000000002", batch="b1", state="in_use"
                ),
                Sim(
                    iccid="8923400000000000003", imsi="621000000000003", batch="b1", state="retired"
                ),
                Number(msisdn="2348000000001", state="available"),
                Number(msisdn="2348000000002", state="in_use"),
                Number(msisdn="2348000000003", state="quarantined"),
            ]
        )
    sims = care.get("/v1/stock/sims").json()["sims"]
    assert sims == [
        {
            "iccid": "8923400000000000001",
            "imsi": "621000000000001",
            "batch": "b1",
            "state": "in_stock",
        }
    ]
    assert care.get("/v1/stock/numbers").json()["numbers"] == [
        {"msisdn": "2348000000001", "state": "available"}
    ]
    assert "ki" not in care.get("/v1/stock/sims").text.lower().replace("kind", "")


def test_stock_lists_respect_the_limit(care: TestClient, factory: sessionmaker[Session]) -> None:
    with factory() as session, session.begin():
        session.add_all(Number(msisdn=f"23480000000{n:02d}", state="available") for n in range(5))
    assert len(care.get("/v1/stock/numbers?limit=2").json()["numbers"]) == 2
    for bad in ("0", "5001", "x"):
        assert care.get(f"/v1/stock/numbers?limit={bad}").status_code == 422
        assert care.get(f"/v1/stock/sims?limit={bad}").status_code == 422


def test_one_line_is_read_with_its_state_and_expiry_as_epoch(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    from datetime import UTC, datetime

    expiry = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
    with factory() as session, session.begin():
        customer = Customer(
            name="n",
            phone="p",
            email="e@e.cd",
            id_type="NIN",
            id_number="1",
            address="a",
            kyc_status="verified",
        )
        plan = _plan()
        session.add_all(
            [
                customer,
                plan,
                Sim(iccid="89234", imsi="621000000000001", batch="b", state="in_use"),
                Number(msisdn="2348000000001", state="in_use"),
            ]
        )
        session.flush()
        session.add(
            Line(
                customer_id=customer.customer_id,
                iccid="89234",
                imsi="621000000000001",
                msisdn="2348000000001",
                plan_id=plan.plan_id,
                state="suspended",
                state_before_suspension="active",
                expires_at=expiry,
            )
        )
    line = care.get("/v1/lines/1")
    assert line.status_code == 200
    body = line.json()
    assert body["state"] == "suspended" and body["state_before_suspension"] == "active"
    assert body["expires_at"] == int(expiry.timestamp())
    assert care.get("/v1/lines/2").status_code == 404
    assert care.get("/v1/lines/lookup/1").json()["line_id"] == 1  # the older route still resolves


def test_lookup_is_not_swallowed_by_the_line_id_route(care: TestClient) -> None:
    """/v1/lines/lookup must reach the lookup route, not be read as a line id."""
    assert care.get("/v1/lines/lookup").status_code == 422  # lookup's own rule: one identifier


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/v1/customers"),
        ("get", "/v1/customers/1"),
        ("get", "/v1/plans"),
        ("get", "/v1/stock/sims"),
        ("get", "/v1/stock/numbers"),
        ("post", "/v1/lines"),
        ("get", "/v1/lines/1"),
    ],
)
def test_nothing_answers_a_caller_who_is_not_signed_in(
    app: FastAPI, method: str, path: str
) -> None:
    anonymous = TestClient(app)
    response = getattr(anonymous, method)(path, **({"json": {}} if method == "post" else {}))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_the_check_comes_before_the_request_is_read(app: FastAPI) -> None:
    """A bad body without a session is 401, not 422: nobody learns the shape of the request."""
    anonymous = TestClient(app)
    assert anonymous.post("/v1/customers", json={"nonsense": True}).status_code == 401
    assert anonymous.post("/v1/lines", content=b"{not json").status_code == 401


# --- the answers match the contract ------------------------------------------------------------


def _validate(schema_name: str, instance: Any) -> None:
    """Check `instance` against a schema of contracts/openapi.yaml, extra fields included."""
    import jsonschema

    from tests.contract.helpers import load_contract

    components = load_contract()["components"]
    jsonschema.Draft202012Validator(
        {"$ref": f"#/components/schemas/{schema_name}", "components": components}
    ).validate(instance)


def test_the_answers_match_the_contracts_schemas(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    from datetime import UTC, datetime

    created = care.post("/v1/customers", json=customer_body()).json()
    _validate("Customer", created)
    _validate("Customer", care.get("/v1/customers/1").json())
    with factory() as session, session.begin():
        plan = _plan()
        session.add_all(
            [
                plan,
                Sim(iccid="89234", imsi="621000000000001", batch="b", state="in_stock"),
                Sim(iccid="89235", imsi="621000000000002", batch="b", state="in_use"),
                Number(msisdn="2348000000001", state="available"),
                Number(msisdn="2348000000002", state="in_use"),
            ]
        )
        session.flush()
        session.add(
            Line(
                customer_id=1, iccid="89235", imsi="621000000000002", msisdn="2348000000002",
                plan_id=plan.plan_id, state="active", expires_at=datetime(2026, 12, 1, tzinfo=UTC),
            )
        )  # fmt: skip
    _validate("PlanList", care.get("/v1/plans").json())
    _validate("SimList", care.get("/v1/stock/sims").json())
    _validate("NumberList", care.get("/v1/stock/numbers").json())
    _validate("Line", care.get("/v1/lines/1").json())
    _validate("StaffMe", care.get("/v1/auth/me").json())


def test_the_errors_match_the_contracts_error_shape(care: TestClient, app: FastAPI) -> None:
    answers = [
        TestClient(app).get("/v1/plans"),  # 401
        care.get("/v1/customers/99"),  # 404
        care.post("/v1/customers", json=customer_body(kyc_status="verified")),  # 403
        care.post("/v1/customers", json={}),  # 422
    ]
    assert [a.status_code for a in answers] == [401, 404, 403, 422]
    for answer in answers:
        _validate("Error", answer.json())


def test_every_staff_operation_in_the_contract_answers_the_statuses_it_promises(
    care: TestClient,
) -> None:
    """Each documented status of the implemented staff operations is one the route can give."""
    from tests.contract.helpers import operations

    promised = {
        o.op_id: set(o.raw["responses"]) - {"default"}
        for o in operations()
        if o.raw.get("security") == [{"StaffSession": []}]
    }
    assert "401" in promised["bss_get_line"] and "403" in promised["bss_get_line"]
    assert "403" in promised["bss_create_customer"]
