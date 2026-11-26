"""Calls and texts asked about by the voice VM, over HTTP on SQLite (ADR 0013)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bss_lines.models.lines import Customer, Line, Number, Plan, Sim
from app.bss_money.domain.catalogue import DEFAULT_SETTINGS
from app.bss_money.domain.entries import EntryKind, new_posting
from app.bss_money.repositories.sql import SqlLedgerRepository
from app.config import Settings
from app.db import Base
from app.main import create_app

PAY_KEY = "test-pay-key-not-a-real-key"
AUTH = {"Authorization": f"Bearer {PAY_KEY}"}
CALLER = "2348000010010"
FRIEND = "2348000010011"
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
ONNET = DEFAULT_SETTINGS.voice_onnet_kobo_per_min


def _client(tmp_path: Path, charging_from: str | None) -> TestClient:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'prepaid.db'}",  # type: ignore[arg-type]
            pay_api_key=PAY_KEY,  # type: ignore[arg-type]
            call_charging_from=charging_from,  # type: ignore[arg-type]
            free_call_numbers="112,199",
        )
    )
    app.state.clock = lambda: NOW
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as s, s.begin():
        customer = Customer(
            name="Ada Test",
            phone="2348000000011",
            email="ada@example.test",
            id_type="NIN",
            id_number="00000000000",
            address="1 Test Street",
            kyc_status="verified",
        )
        plan = Plan(
            name="Monthly",
            price_kobo=200_000,
            validity_days=30,
            data_bytes=10**10,
            speed_ul_mbps=5,
            speed_dl_mbps=10,
            channels="desk",
            on_exhaustion="stop",
            state="on_sale",
        )
        s.add_all([customer, plan])
        for n, msisdn in enumerate((CALLER, FRIEND), start=1):
            s.add_all(
                [
                    Sim(
                        iccid=f"892340000000000000{n}",
                        imsi=f"62100000000000{n}",
                        batch="b",
                        state="in_use",
                    ),
                    Number(msisdn=msisdn, state="in_use"),
                ]
            )
        s.flush()
        for n, msisdn in enumerate((CALLER, FRIEND), start=1):
            s.add(
                Line(
                    customer_id=customer.customer_id,
                    iccid=f"892340000000000000{n}",
                    imsi=f"62100000000000{n}",
                    msisdn=msisdn,
                    plan_id=plan.plan_id,
                    state="active",
                )
            )
        s.flush()
        SqlLedgerRepository(s).append(new_posting(1, 2 * ONNET, EntryKind.TOP_UP, "test:top-up"))
    return TestClient(app)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with _client(tmp_path, "2026-11-01T00:00:00+00:00") as c:
        yield c


def _authorize(client: TestClient, call_id: str, dialled: str = FRIEND) -> dict[str, object]:
    response = client.post(
        "/v1/pay/calls/authorize",
        json={"call_id": call_id, "caller": f"sip:+{CALLER}@ims.example", "dialled": dialled},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_the_endpoints_need_the_key(client: TestClient) -> None:
    for path, body in (
        ("/v1/pay/calls/authorize", {"call_id": "c", "caller": CALLER, "dialled": FRIEND}),
        ("/v1/pay/calls/end", {"call_id": "c", "seconds": 1}),
        ("/v1/pay/sms/charge", {"message_id": "m", "sender": CALLER, "recipient": FRIEND}),
    ):
        assert client.post(path, json=body).status_code == 401


def test_a_call_is_limited_then_its_hold_shrinks_at_hang_up(client: TestClient) -> None:
    assert _authorize(client, "c1") == {"allowed": True, "max_seconds": 120, "reason": "limited"}
    assert _authorize(client, "c2")["allowed"] is False  # the first call holds it all
    ended = client.post(
        "/v1/pay/calls/end",
        json={"call_id": "c1", "seconds": 60},
        headers={**AUTH, "Idempotency-Key": "end-c1"},
    )
    assert ended.json() == {"ended": True}
    assert _authorize(client, "c2")["max_seconds"] == 60


def test_a_refused_call_says_why(client: TestClient) -> None:
    _authorize(client, "c1")
    assert _authorize(client, "c2") == {
        "allowed": False,
        "max_seconds": 0,
        "reason": "insufficient_balance",
    }


def test_emergency_calls_have_no_limit(client: TestClient) -> None:
    assert _authorize(client, "c1", dialled="tel:112") == {
        "allowed": True,
        "max_seconds": 0,
        "reason": "free_number",
    }


def test_before_charging_starts_calls_are_unlimited(tmp_path: Path) -> None:
    with _client(tmp_path, None) as c:
        assert _authorize(c, "c1")["reason"] == "charging_off"


def test_a_text_is_charged_once_and_one_to_another_network_is_refused(client: TestClient) -> None:
    def charge(message_id: str, to: str) -> dict[str, object]:
        response = client.post(
            "/v1/pay/sms/charge",
            json={"message_id": message_id, "sender": CALLER, "recipient": to},
            headers=AUTH,
        )
        assert response.status_code == 200, response.text
        body: dict[str, object] = response.json()
        return body

    price = DEFAULT_SETTINGS.sms_onnet_kobo
    expected = {"send": True, "reason": "charged", "charged_kobo": price}
    assert charge("m1", FRIEND) == expected
    assert charge("m1", FRIEND) == expected
    assert charge("m2", "2348031234567") == {
        "send": False,
        "reason": "refused_off_net",
        "charged_kobo": 0,
    }
    assert charge("m3", "555") == {"send": True, "reason": "free_self_care", "charged_kobo": 0}
    balance = client.get(f"/v1/pay/lines/{CALLER}/balance", headers=AUTH).json()
    assert balance["balance_kobo"] == 2 * ONNET - price


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/v1/pay/calls/authorize", {"call_id": "", "caller": CALLER, "dialled": FRIEND}),
        ("/v1/pay/calls/authorize", {"call_id": "c", "caller": CALLER}),
        ("/v1/pay/calls/end", {"call_id": "c", "seconds": -1}),
        ("/v1/pay/sms/charge", {"message_id": "m", "sender": CALLER, "recipient": FRIEND, "x": 1}),
    ],
)
def test_bad_requests_are_refused(client: TestClient, path: str, body: dict[str, object]) -> None:
    assert client.post(path, json=body, headers=AUTH).status_code == 422
