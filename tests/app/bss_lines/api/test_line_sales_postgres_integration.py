"""Selling a SIM on a real PostgreSQL: a SIM and a number are each taken once, even by
simultaneous requests; a failure part-way takes nothing; a repeated create returns the first line.

Run with RATEL_TEST_POSTGRES_URI set (see tests/app/bss_money/postgres.py).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from tests.app.bss_lines.desk_helpers import add_staff, make_app, signed_in
from tests.app.bss_money.postgres import Database

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _cheap_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("common.passwords._N", 2**10)


@pytest.fixture
def desk(db: Database) -> Iterator[TestClient]:
    factory = sessionmaker(db.engine, expire_on_commit=False)
    with factory() as session, session.begin():
        for sql in (
            "INSERT INTO customer (name, phone, email, id_type, id_number, address, kyc_status) "
            "VALUES ('n', '2348000000001', 'e@example.test', 'NIN', '00000000000', 'a', 'pending')",
            "INSERT INTO plan (name, speed_ul_mbps, speed_dl_mbps, state, price_kobo, "
            "validity_days, data_bytes, slow_ul_mbps, slow_dl_mbps, channels, on_exhaustion) "
            "VALUES "
            "('Basic', 10, 20, 'on_sale', 500, 30, 1000000, 1, 1, 'data', 'slow'), "
            "('Old', 10, 20, 'retired', 500, 30, 1000000, 1, 1, 'data', 'slow')",
            "INSERT INTO sim (iccid, imsi, batch, state) VALUES "
            "('8923400000000000001', '621000000000001', 'b', 'in_stock'), "
            "('8923400000000000002', '621000000000002', 'b', 'in_stock')",
            "INSERT INTO number (msisdn, state) VALUES "
            "('2348000000001', 'available'), ('2348000000002', 'available')",
        ):
            session.execute(text(sql))
    app = make_app(factory)
    email = add_staff(factory, "agent")
    client = signed_in(app, email)
    client.factory = factory  # type: ignore[attr-defined]
    yield client


def sale(**changes: Any) -> dict[str, Any]:
    body = {
        "customer_id": 1,
        "iccid": "8923400000000000001",
        "msisdn": "2348000000001",
        "plan_id": 1,
    }
    return {**body, **changes}


def states(db: Database) -> dict[str, list[str]]:
    with db.engine.connect() as conn:
        return {
            "sims": list(conn.execute(text("SELECT state FROM sim ORDER BY iccid")).scalars()),
            "numbers": list(
                conn.execute(text("SELECT state FROM number ORDER BY msisdn")).scalars()
            ),
            "lines": list(conn.execute(text("SELECT state FROM line")).scalars()),
        }


def test_a_sale_takes_the_sim_and_the_number_and_waits_for_activation(
    desk: TestClient, db: Database
) -> None:
    response = desk.post("/v1/lines", json=sale())
    assert response.status_code == 201
    assert response.json() == {
        "line_id": 1, "customer_id": 1, "iccid": "8923400000000000001", "imsi": "621000000000001",
        "msisdn": "2348000000001", "plan_id": 1, "state": "awaiting_activation",
        "state_before_suspension": None, "expires_at": None,
    }  # fmt: skip
    assert states(db) == {
        "sims": ["in_use", "in_stock"], "numbers": ["in_use", "available"],
        "lines": ["awaiting_activation"],
    }  # fmt: skip
    assert desk.get("/v1/lines/1").json()["imsi"] == "621000000000001"


def test_the_imsi_comes_from_the_sim_never_from_the_caller(desk: TestClient) -> None:
    refused = desk.post("/v1/lines", json={**sale(), "imsi": "621999999999999"})
    assert refused.status_code == 422  # unknown fields are refused, not ignored


def test_a_taken_sim_or_number_is_refused_and_nothing_else_is_taken(
    desk: TestClient, db: Database
) -> None:
    assert desk.post("/v1/lines", json=sale()).status_code == 201
    # the SIM is taken, the number is free: the number must stay free
    refused = desk.post("/v1/lines", json=sale(msisdn="2348000000002"))
    assert refused.status_code == 409
    assert states(db)["numbers"] == ["in_use", "available"]
    # the number is taken, the SIM is free: the SIM must stay free
    refused = desk.post("/v1/lines", json=sale(iccid="8923400000000000002"))
    assert refused.status_code == 409
    assert states(db)["sims"] == ["in_use", "in_stock"]
    assert len(states(db)["lines"]) == 1


def test_an_unknown_sim_or_number_is_refused_and_the_other_stays_free(
    desk: TestClient, db: Database
) -> None:
    assert desk.post("/v1/lines", json=sale(iccid="89999")).status_code == 409
    assert desk.post("/v1/lines", json=sale(msisdn="2349999999999")).status_code == 409
    assert states(db) == {
        "sims": ["in_stock", "in_stock"], "numbers": ["available", "available"], "lines": [],
    }  # fmt: skip


def test_an_unknown_customer_or_plan_is_404_and_a_retired_plan_is_409(
    desk: TestClient, db: Database
) -> None:
    assert desk.post("/v1/lines", json=sale(customer_id=99)).status_code == 404
    assert desk.post("/v1/lines", json=sale(plan_id=99)).status_code == 404
    assert desk.post("/v1/lines", json=sale(plan_id=2)).status_code == 409
    assert states(db)["sims"] == ["in_stock", "in_stock"]


@pytest.mark.parametrize("msisdn", ["08000000001", "2348", "234800000000a", "+2348000000001"])
def test_a_badly_formed_number_is_422(desk: TestClient, msisdn: str) -> None:
    assert desk.post("/v1/lines", json=sale(msisdn=msisdn)).status_code == 422


def test_a_repeated_sale_returns_the_first_line_and_takes_nothing_more(
    desk: TestClient, db: Database
) -> None:
    headers = {"Idempotency-Key": "sale-1"}
    first = desk.post("/v1/lines", json=sale(), headers=headers)
    second = desk.post("/v1/lines", json=sale(), headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert states(db)["lines"] == ["awaiting_activation"]
    assert states(db)["sims"] == ["in_use", "in_stock"]


def test_a_key_reused_for_another_sale_is_refused(desk: TestClient, db: Database) -> None:
    headers = {"Idempotency-Key": "sale-1"}
    assert desk.post("/v1/lines", json=sale(), headers=headers).status_code == 201
    other = desk.post(
        "/v1/lines",
        json=sale(iccid="8923400000000000002", msisdn="2348000000002"),
        headers=headers,
    )
    assert other.status_code == 409
    assert states(db)["sims"] == ["in_use", "in_stock"]  # the second SIM was not taken


def test_simultaneous_sales_of_the_same_sim_make_exactly_one_line(
    desk: TestClient, db: Database
) -> None:
    app = desk.app
    results: list[int] = []
    barrier = threading.Barrier(8)

    def go(n: int) -> None:
        client = signed_in(app, "agent@example.test")
        barrier.wait()
        # each caller tries a different number, so only the SIM is contested
        number = "2348000000001" if n % 2 == 0 else "2348000000002"
        results.append(client.post("/v1/lines", json=sale(msisdn=number)).status_code)

    threads = [threading.Thread(target=go, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [201] + [409] * 7
    assert states(db)["lines"] == ["awaiting_activation"]
    assert states(db)["numbers"].count("in_use") == 1  # the losers gave their number back


def test_simultaneous_repeats_of_one_sale_make_one_line(desk: TestClient, db: Database) -> None:
    app = desk.app
    results: list[tuple[int, Any]] = []
    barrier = threading.Barrier(6)

    def go() -> None:
        client = signed_in(app, "agent@example.test")
        barrier.wait()
        response = client.post("/v1/lines", json=sale(), headers={"Idempotency-Key": "race"})
        results.append((response.status_code, response.json().get("line_id")))

    threads = [threading.Thread(target=go) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert states(db)["lines"] == ["awaiting_activation"]  # one line, whatever the answers
    created = [r for r in results if r[0] == 201]
    assert created and {line for _, line in created} == {1}
    assert all(status in (201, 409) for status, _ in results)  # a loser may be told to retry
    retry = desk.post("/v1/lines", json=sale(), headers={"Idempotency-Key": "race"})
    assert retry.status_code == 201 and retry.json()["line_id"] == 1


def test_a_line_row_in_a_session_matches_the_contract(desk: TestClient) -> None:
    desk.post("/v1/lines", json=sale())
    session: Session = desk.factory()  # type: ignore[attr-defined]
    with session:
        assert session.execute(text("SELECT count(*) FROM line")).scalar() == 1
