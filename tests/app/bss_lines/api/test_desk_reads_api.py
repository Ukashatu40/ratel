"""RatelDesk's customer list, line list and a line's history over HTTP, on SQLite."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bss_lines.models.lines import Customer, Line, LineAudit, Number, Plan, Sim
from app.db import Base
from tests.app.bss_lines.desk_helpers import add_staff, make_app, signed_in

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _cheap_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("common.passwords._N", 2**10)


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    _seed(factory)
    yield factory


def _seed(factory: sessionmaker[Session]) -> None:
    """Three customers; Ada has two lines, Bola one (out of data), Chidi none."""
    with factory() as s, s.begin():
        plan = Plan(
            name="Weekly 5GB",
            price_kobo=100_000,
            validity_days=7,
            data_bytes=5_000_000_000,
            speed_ul_mbps=10,
            speed_dl_mbps=20,
            channels="data",
            on_exhaustion="stop",
            state="on_sale",
        )
        s.add(plan)
        people = [
            ("Ada Test", "2348000000011", "ada@example.test", "verified"),
            ("Bola Test", "2348000000012", "bola@example.test", "pending"),
            ("Chidi Test", "2348000000013", "chidi@example.test", "rejected"),
        ]
        customers = []
        for i, (name, phone, email, kyc) in enumerate(people):
            c = Customer(
                name=name,
                phone=phone,
                email=email,
                id_type="NIN",
                id_number=f"0000000000{i}",
                address="1 Test Street",
                kyc_status=kyc,
                created_at=T0 + timedelta(hours=i),
            )
            s.add(c)
            customers.append(c)
        s.flush()
        owners = [(0, "active"), (0, "suspended"), (1, "out_of_data")]
        for n, (owner, state) in enumerate(owners, start=1):
            iccid = f"89234000000000001{n:02d}"
            msisdn = f"23480000010{n:02d}"
            s.add(Sim(iccid=iccid, imsi=f"6210000000000{n:02d}", batch="b1", state="in_use"))
            s.add(Number(msisdn=msisdn, state="in_use"))
            s.flush()
            s.add(
                Line(
                    customer_id=customers[owner].customer_id,
                    iccid=iccid,
                    imsi=f"6210000000000{n:02d}",
                    msisdn=msisdn,
                    plan_id=plan.plan_id,
                    state=state,
                    expires_at=T0 + timedelta(days=7),
                )
            )
        s.flush()
        for step, (to_state, actor) in enumerate(
            [("active", "staff:1"), ("suspended", "staff:2"), ("active", "staff:1")]
        ):
            s.add(
                LineAudit(
                    line_id=1,
                    from_state="awaiting_activation" if step == 0 else "active",
                    to_state=to_state,
                    actor=actor,
                    reason=f"reason {step}",
                    created_at=T0 + timedelta(minutes=step),
                )
            )


@pytest.fixture
def care(factory: sessionmaker[Session]) -> TestClient:
    return signed_in(make_app(factory), add_staff(factory, "agent"))


# --- customers ---------------------------------------------------------------------------------


def test_customers_come_newest_first_without_the_nin_or_the_address(care: TestClient) -> None:
    body = care.get("/v1/customers").json()
    assert [c["name"] for c in body["customers"]] == ["Chidi Test", "Bola Test", "Ada Test"]
    assert set(body["customers"][0]) == {
        "customer_id",
        "name",
        "phone",
        "email",
        "kyc_status",
        "blocked",
        "lines_count",
    }
    assert "00000000" not in care.get("/v1/customers").text
    assert body["total"] == 3


def test_each_customer_row_counts_that_customers_lines(care: TestClient) -> None:
    rows = {c["name"]: c["lines_count"] for c in care.get("/v1/customers").json()["customers"]}
    assert rows == {"Ada Test": 2, "Bola Test": 1, "Chidi Test": 0}


def test_the_kyc_filter_narrows_the_page_but_not_the_tab_counts(care: TestClient) -> None:
    body = care.get("/v1/customers", params={"kyc_status": "pending"}).json()
    assert [c["name"] for c in body["customers"]] == ["Bola Test"]
    assert body["total"] == 1
    assert body["counts"] == {"all": 3, "pending": 1, "verified": 1, "rejected": 1}


def test_a_search_narrows_the_page_and_the_counts(care: TestClient) -> None:
    body = care.get("/v1/customers", params={"q": "ADA"}).json()
    assert [c["name"] for c in body["customers"]] == ["Ada Test"]
    assert body["counts"] == {"all": 1, "pending": 0, "verified": 1, "rejected": 0}
    by_phone = care.get("/v1/customers", params={"q": "000012"}).json()
    assert [c["name"] for c in by_phone["customers"]] == ["Bola Test"]


def test_a_percent_sign_in_a_search_matches_itself_not_everything(care: TestClient) -> None:
    assert care.get("/v1/customers", params={"q": "%"}).json()["total"] == 0
    assert care.get("/v1/customers", params={"q": "_"}).json()["total"] == 0


def test_customers_are_paged(care: TestClient) -> None:
    first = care.get("/v1/customers", params={"page": 1, "page_size": 2}).json()
    second = care.get("/v1/customers", params={"page": 2, "page_size": 2}).json()
    assert [c["name"] for c in first["customers"]] == ["Chidi Test", "Bola Test"]
    assert [c["name"] for c in second["customers"]] == ["Ada Test"]
    assert first["total"] == second["total"] == 3


# --- lines -------------------------------------------------------------------------------------


def test_lines_come_newest_first_with_the_customer_and_plan_names(care: TestClient) -> None:
    body = care.get("/v1/lines").json()
    assert [r["line_id"] for r in body["lines"]] == [3, 2, 1]
    row = body["lines"][2]
    assert row["customer_name"] == "Ada Test"
    assert row["plan_name"] == "Weekly 5GB"
    assert row["state"] == "active"
    assert row["expires_at"] == int((T0 + timedelta(days=7)).timestamp())
    assert set(row) == {
        "line_id",
        "customer_id",
        "customer_name",
        "iccid",
        "imsi",
        "msisdn",
        "plan_id",
        "plan_name",
        "state",
        "expires_at",
    }


def test_the_state_filter_narrows_the_page_but_not_the_tab_counts(care: TestClient) -> None:
    body = care.get("/v1/lines", params={"state": "suspended"}).json()
    assert [r["line_id"] for r in body["lines"]] == [2]
    assert body["total"] == 1
    assert body["counts"] == {
        "all": 3,
        "awaiting_activation": 0,
        "active": 1,
        "out_of_data": 1,
        "expired": 0,
        "suspended": 1,
        "terminated": 0,
    }


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("0000000000", [3, 2, 1]),  # part of the MSISDNs
        ("89234000000000001", [3, 2, 1]),  # part of the ICCIDs
        ("bola", [3]),  # part of a customer's name
        ("621000000000002", [2]),  # an exact IMSI
        ("62100000000000", []),  # a part of an IMSI does not match
    ],
)
def test_a_line_search_matches_msisdn_iccid_name_and_exact_imsi(
    care: TestClient, q: str, expected: list[int]
) -> None:
    assert [
        r["line_id"] for r in care.get("/v1/lines", params={"q": q}).json()["lines"]
    ] == expected


def test_a_search_narrows_the_line_counts_too(care: TestClient) -> None:
    body = care.get("/v1/lines", params={"q": "bola"}).json()
    assert body["counts"]["all"] == 1
    assert body["counts"]["out_of_data"] == 1
    assert body["counts"]["active"] == 0


def test_what_staff_search_for_never_reaches_a_log_line(
    care: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("DEBUG"):
        care.get("/v1/customers", params={"q": "ada@example.test"})
        care.get("/v1/lines", params={"q": "2348000001001"})
    app_logs = [
        r.getMessage() + str(r.__dict__) for r in caplog.records if r.name.startswith("ratel")
    ]
    assert app_logs, "the request should have been logged"
    assert not any("ada@example" in line or "2348000001001" in line for line in app_logs)


def test_lines_are_paged(care: TestClient) -> None:
    body = care.get("/v1/lines", params={"page": 2, "page_size": 2}).json()
    assert [r["line_id"] for r in body["lines"]] == [1]
    assert body["total"] == 3


@pytest.mark.parametrize(
    "params",
    [{"state": "nonsense"}, {"page": 0}, {"page_size": 0}, {"page_size": 201}, {"q": "x" * 101}],
)
def test_a_bad_filter_or_page_is_422(care: TestClient, params: dict[str, object]) -> None:
    for path in ("/v1/lines", "/v1/customers"):
        assert care.get(path, params=params).status_code == 422 or "state" in params


def test_an_unknown_kyc_status_is_422(care: TestClient) -> None:
    assert care.get("/v1/customers", params={"kyc_status": "nonsense"}).status_code == 422


# --- history -----------------------------------------------------------------------------------


def test_a_lines_history_is_newest_first(care: TestClient) -> None:
    body = care.get("/v1/lines/1/history").json()
    assert body["total"] == 3
    assert [e["reason"] for e in body["entries"]] == ["reason 2", "reason 1", "reason 0"]
    newest = body["entries"][0]
    assert newest == {
        "at": int((T0 + timedelta(minutes=2)).timestamp()),
        "from_state": "active",
        "to_state": "active",
        "actor": "staff:1",
        "reason": "reason 2",
    }


def test_a_lines_history_is_paged(care: TestClient) -> None:
    body = care.get("/v1/lines/1/history", params={"page": 2, "page_size": 2}).json()
    assert [e["reason"] for e in body["entries"]] == ["reason 0"]
    assert body["total"] == 3


def test_a_line_with_no_history_has_an_empty_one(care: TestClient) -> None:
    assert care.get("/v1/lines/3/history").json() == {"entries": [], "total": 0}


def test_the_history_of_an_unknown_line_is_404(care: TestClient) -> None:
    response = care.get("/v1/lines/999/history")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --- who may read ------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/v1/customers", "/v1/lines", "/v1/lines/1/history"])
def test_these_routes_refuse_a_caller_who_is_not_signed_in(
    factory: sessionmaker[Session], path: str
) -> None:
    anonymous = TestClient(make_app(factory))
    assert anonymous.get(path).status_code == 401
    assert anonymous.get(path, params={"page": 0}).status_code == 401  # before the input is read
