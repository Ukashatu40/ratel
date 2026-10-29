"""An admin's KYC decision and a customer's history over HTTP, on SQLite."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bss_lines.models.lines import Customer, CustomerAudit
from app.db import Base
from tests.app.bss_lines.desk_helpers import add_staff, make_app, signed_in, utc

T0 = utc(2026, 10, 28, 12, 0)


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
def app_clients(factory: sessionmaker[Session]) -> tuple[TestClient, TestClient]:
    app = make_app(factory, clock=lambda: T0)
    return signed_in(app, add_staff(factory, "agent")), signed_in(app, add_staff(factory, "admin"))


@pytest.fixture
def care(app_clients: tuple[TestClient, TestClient]) -> TestClient:
    return app_clients[0]


@pytest.fixture
def admin(app_clients: tuple[TestClient, TestClient]) -> TestClient:
    return app_clients[1]


def customer(**changes: Any) -> dict[str, Any]:
    body = {
        "name": "Test Person",
        "phone": "2348000000001",
        "email": "person@example.test",
        "id_type": "NIN",
        "id_number": "00000000000",
        "address": "1 Test Street",
        "kyc_status": "pending",
    }
    return body | changes


def register(client: TestClient, **changes: Any) -> int:
    response = client.post("/v1/customers", json=customer(**changes))
    assert response.status_code == 201, response.text
    return int(response.json()["customer_id"])


def decide(client: TestClient, customer_id: int, status: str = "verified", reason: str = "seen"):  # type: ignore[no-untyped-def]
    return client.post(
        f"/v1/customers/{customer_id}/kyc", json={"status": status, "reason": reason}
    )


def audit_rows(factory: sessionmaker[Session]) -> list[tuple[str, str, str]]:
    with factory() as s:
        return [
            (r.action, r.actor, r.reason)
            for r in s.scalars(select(CustomerAudit).order_by(CustomerAudit.id))
        ]


def test_an_admin_verifies_a_pending_customer(
    care: TestClient, admin: TestClient, factory: sessionmaker[Session]
) -> None:
    customer_id = register(care)
    response = decide(admin, customer_id, "verified", "documents checked")
    assert response.status_code == 200
    assert response.json()["kyc_status"] == "verified"
    assert response.json()["customer_id"] == customer_id
    with factory() as s:
        assert s.get(Customer, customer_id).kyc_status == "verified"  # type: ignore[union-attr]
    assert [(a, r) for a, _, r in audit_rows(factory)] == [
        ("registered", "registered with KYC pending"),
        ("kyc_verified", "documents checked"),
    ]
    assert audit_rows(factory)[1][1].startswith("staff:")


def test_an_admin_rejects_a_pending_customer_and_may_verify_them_later(
    care: TestClient, admin: TestClient
) -> None:
    customer_id = register(care)
    assert decide(admin, customer_id, "rejected", "blurred scan").json()["kyc_status"] == "rejected"
    assert decide(admin, customer_id, "verified", "new scan").json()["kyc_status"] == "verified"


def test_a_verified_customer_cannot_be_taken_back_to_rejected(
    care: TestClient, admin: TestClient, factory: sessionmaker[Session]
) -> None:
    customer_id = register(care)
    decide(admin, customer_id)
    refused = decide(admin, customer_id, "rejected", "changed our mind")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "conflict"
    assert admin.get(f"/v1/customers/{customer_id}").json()["kyc_status"] == "verified"
    assert len(audit_rows(factory)) == 2  # registered, verified; the refusal wrote nothing


def test_deciding_what_the_customer_already_is_changes_nothing(
    care: TestClient, admin: TestClient, factory: sessionmaker[Session]
) -> None:
    customer_id = register(care)
    decide(admin, customer_id)
    again = decide(admin, customer_id, "verified", "a second look")
    assert again.status_code == 200
    assert len(audit_rows(factory)) == 2


def test_only_an_admin_may_decide(
    care: TestClient, admin: TestClient, factory: sessionmaker[Session]
) -> None:
    customer_id = register(care)
    refused = decide(care, customer_id)
    assert refused.status_code == 403
    assert admin.get(f"/v1/customers/{customer_id}").json()["kyc_status"] == "pending"
    assert len(audit_rows(factory)) == 1


def test_an_unknown_customer_is_404(admin: TestClient) -> None:
    assert decide(admin, 999).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"status": "pending", "reason": "x"},
        {"status": "verified"},
        {"status": "verified", "reason": ""},
        {"status": "verified", "reason": "x" * 201},
        {"status": "verified", "reason": "x", "actor": "someone-else"},
    ],
)
def test_a_bad_decision_is_422_and_changes_nothing(
    care: TestClient, admin: TestClient, body: dict[str, Any]
) -> None:
    customer_id = register(care)
    assert admin.post(f"/v1/customers/{customer_id}/kyc", json=body).status_code == 422
    assert admin.get(f"/v1/customers/{customer_id}").json()["kyc_status"] == "pending"


def test_a_caller_who_is_not_signed_in_is_refused_before_the_body_is_read(
    factory: sessionmaker[Session],
) -> None:
    anonymous = TestClient(make_app(factory))
    assert anonymous.post("/v1/customers/1/kyc", json={"nonsense": 1}).status_code == 401
    assert anonymous.get("/v1/customers/1/history").status_code == 401


def test_the_history_lists_the_registration_and_each_decision_newest_first(
    care: TestClient, admin: TestClient
) -> None:
    customer_id = register(care)
    decide(admin, customer_id, "rejected", "blurred scan")
    decide(admin, customer_id, "verified", "new scan")
    body = care.get(f"/v1/customers/{customer_id}/history").json()
    assert body["total"] == 3
    assert [e["action"] for e in body["entries"]] == ["kyc_verified", "kyc_rejected", "registered"]
    assert body["entries"][0]["reason"] == "new scan"
    assert body["entries"][0]["actor"].startswith("staff:")
    assert body["entries"][0]["at"] >= body["entries"][2]["at"]
    assert set(body["entries"][0]) == {"at", "action", "actor", "reason"}


def test_the_history_is_paged_and_404_for_an_unknown_customer(
    care: TestClient, admin: TestClient
) -> None:
    customer_id = register(care)
    decide(admin, customer_id)
    page = care.get(f"/v1/customers/{customer_id}/history", params={"page": 2, "page_size": 1})
    assert [e["action"] for e in page.json()["entries"]] == ["registered"]
    assert care.get("/v1/customers/999/history").status_code == 404
    assert care.get(f"/v1/customers/{customer_id}/history", params={"page": 0}).status_code == 422


def test_a_registration_repeated_with_its_key_writes_one_history_entry(
    care: TestClient, factory: sessionmaker[Session]
) -> None:
    for _ in range(2):
        response = care.post("/v1/customers", json=customer(), headers={"Idempotency-Key": "same"})
        assert response.status_code == 201
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(CustomerAudit)) == 1


def test_what_a_reason_says_never_reaches_a_log_line(
    care: TestClient, admin: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    customer_id = register(care)
    with caplog.at_level("DEBUG"):
        decide(admin, customer_id, "rejected", "typed-by-staff-marker-123")
    logged = [
        r.getMessage() + str(r.__dict__) for r in caplog.records if r.name.startswith("ratel")
    ]
    assert logged
    assert not any("typed-by-staff-marker-123" in line for line in logged)
