"""POST and GET /v1/calls: the key, the rules, replay, filters, pages, and what logs never hold."""

from __future__ import annotations

import logging
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.db import Base
from app.main import create_app

KEY = "unit-test-key-0000000000000000"
AUTH = {"Authorization": f"Bearer {KEY}"}
T = 1_794_700_000
A, B, C = "2340000000001", "2340000000002", "2340000000003"


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    settings = Settings(
        ratel_env="test", database_url=SecretStr("sqlite:///:memory:"), meter_api_key=SecretStr(KEY)
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as c:
        yield c


def wire(n: int, *, frm: str = A, to: str = B, **changes: object) -> dict[str, object]:
    start = T + n * 100
    body: dict[str, object] = {
        "call_id": f"call-{n:03d}",
        "from_msisdn": frm,
        "to_msisdn": to,
        "started_at": start,
        "answered_at": start + 5,
        "ended_at": start + 60,
        "end_reason": "completed",
    }
    return {**body, **changes}


def post(client: TestClient, *records: dict[str, object]):
    return client.post("/v1/calls", json={"records": list(records)}, headers=AUTH)


def get(client: TestClient, **params: object):
    query = {"from": T - 10, "to": T + 10_000, **params}
    return client.get("/v1/calls", params=query, headers=AUTH)


def test_both_operations_need_the_key(client: TestClient) -> None:
    assert client.post("/v1/calls", json={"records": [wire(1)]}).status_code == 401
    assert client.get("/v1/calls", params={"from": 0, "to": 1}).status_code == 401
    wrong = {"Authorization": "Bearer nope"}
    assert client.post("/v1/calls", json={"records": [wire(1)]}, headers=wrong).status_code == 401


def test_a_posted_call_is_read_back_exactly(client: TestClient) -> None:
    assert (
        post(client, wire(1), wire(2, answered_at=None, end_reason="declined")).status_code == 200
    )
    body = get(client).json()
    assert body["next_cursor"] is None
    assert body["records"] == [wire(1), wire(2, answered_at=None, end_reason="declined")]


def test_posting_a_call_again_overwrites_it(client: TestClient) -> None:
    post(client, wire(1, answered_at=None, end_reason="not_answered"))
    post(client, wire(1))
    records = get(client).json()["records"]
    assert records == [wire(1)]


def test_one_bad_record_rejects_the_whole_batch(client: TestClient) -> None:
    res = post(client, wire(1), wire(2, end_reason="completed", answered_at=None))
    assert res.status_code == 422 and res.json()["error"]["code"] == "validation_error"
    assert get(client).json()["records"] == []  # the good one was not stored either


@pytest.mark.parametrize(
    "body",
    [
        {"records": []},
        {},
        {"records": [wire(1, end_reason="busy")]},
        {"records": [{**wire(1), "imsi": "621000000000001"}]},  # a field the contract does not have
        {
            "records": [{k: v for k, v in wire(1).items() if k != "answered_at"}]
        },  # null must be explicit
        {"records": [wire(1, started_at=-5)]},
        {"records": [wire(1, from_msisdn="has space")]},
        {"records": [wire(1, to_msisdn="")]},
        {"records": [wire(1, call_id="caf\u00e9")]},
        {"records": [wire(1, answered_at=None)]},  # completed, but never answered
        {"records": [wire(1, started_at="1794700000")]},
    ],
)
def test_malformed_bodies_are_422(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/v1/calls", json=body, headers=AUTH).status_code == 422


def test_an_empty_idempotency_key_is_refused(client: TestClient) -> None:
    res = client.post(
        "/v1/calls", json={"records": [wire(1)]}, headers={**AUTH, "Idempotency-Key": " "}
    )
    assert res.status_code == 422


def test_the_window_the_number_and_the_cursor(client: TestClient) -> None:
    post(client, *[wire(n, frm=A if n % 2 else C, to=B if n % 2 else A) for n in range(1, 8)])
    assert len(get(client).json()["records"]) == 7
    assert len(get(client, **{"from": T + 300, "to": T + 500}).json()["records"]) == 3
    mine = get(client, msisdn=C).json()["records"]  # C made calls 2, 4, 6 and received none
    assert [r["call_id"] for r in mine] == ["call-002", "call-004", "call-006"]
    assert (
        len(get(client, msisdn=A).json()["records"]) == 7
    )  # A is in every call, on one side or the other
    assert get(client, **{"from": T + 5000, "to": T}).json() == {"records": [], "next_cursor": None}


def test_a_window_the_wrong_way_round_or_a_blank_number_is_refused_or_empty(
    client: TestClient,
) -> None:
    assert client.get("/v1/calls", params={"from": 0}, headers=AUTH).status_code == 422
    assert get(client, msisdn="").status_code == 422


def test_no_number_and_no_call_id_reaches_the_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    post(client, wire(1, frm="2340000000777", to="2340000000888"))
    get(client, msisdn="2340000000777")
    # The app's own loggers (ratel.*). The test client's httpx line prints the URL it was asked for.
    ours = [r for r in caplog.records if r.name.startswith("ratel")]
    assert ours, "the app logged nothing, so this check would prove nothing"
    text = " ".join(record.getMessage() + str(record.__dict__) for record in ours)
    for secret in ("2340000000777", "2340000000888", "call-001"):
        assert secret not in text


def test_times_out_of_order_are_stored_in_order_and_the_rest_of_the_batch_is_kept(
    client: TestClient,
) -> None:
    backwards = wire(2, answered_at=None, end_reason="failed", ended_at=T + 100 * 2 - 30)
    assert post(client, wire(1), backwards).status_code == 200
    records = get(client).json()["records"]
    assert [r["call_id"] for r in records] == ["call-001", "call-002"]
    assert records[1]["ended_at"] == records[1]["started_at"]  # raised to the start
