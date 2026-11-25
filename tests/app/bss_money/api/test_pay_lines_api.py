"""Self-care by phone number for SMS 555 and USSD, over HTTP on SQLite (docs/catalogue.md)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bss_lines.models.lines import Bundle, Customer, CustomerSms, Line, Number, Plan, Sim
from app.bss_money.domain.entries import EntryKind, new_posting
from app.bss_money.repositories.sql import SqlLedgerRepository
from app.config import Settings
from app.db import Base
from app.main import create_app

PAY_KEY = "test-pay-key-not-a-real-key"
AUTH = {"Authorization": f"Bearer {PAY_KEY}"}
MSISDN = "2348000010010"
GB = 1_000_000_000


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'pay.db'}",  # type: ignore[arg-type]
            pay_api_key=PAY_KEY,  # type: ignore[arg-type]
        )
    )
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
            data_bytes=10 * GB,
            speed_ul_mbps=5,
            speed_dl_mbps=10,
            channels="desk",
            on_exhaustion="stop",
            state="on_sale",
        )
        s.add_all(
            [
                customer,
                plan,
                Sim(iccid="8923400000000000001", imsi="621000000000001", batch="b", state="in_use"),
                Number(msisdn=MSISDN, state="in_use"),
                Bundle(
                    name="Daily 500MB",
                    price_kobo=10_000,
                    data_bytes=GB // 2,
                    validity_days=1,
                    channels="desk,sms,ussd",
                ),
                Bundle(
                    name="Desk only",
                    price_kobo=10_000,
                    data_bytes=GB,
                    validity_days=1,
                    channels="desk",
                ),
            ]
        )
        s.flush()
        s.add(
            Line(
                customer_id=customer.customer_id,
                iccid="8923400000000000001",
                imsi="621000000000001",
                msisdn=MSISDN,
                plan_id=plan.plan_id,
                state="active",
            )
        )
        s.flush()
        SqlLedgerRepository(s).append(new_posting(1, 25_000, EntryKind.TOP_UP, "test:top-up"))
    with TestClient(app) as c:
        yield c


def _buy(client: TestClient, bundle_id: int, key: str, channel: str = "sms") -> object:
    return client.post(
        f"/v1/pay/lines/{MSISDN}/purchases",
        json={"bundle_id": bundle_id, "channel": channel},
        headers={**AUTH, "Idempotency-Key": key},
    )


def test_the_key_is_required(client: TestClient) -> None:
    assert client.get(f"/v1/pay/lines/{MSISDN}/balance").status_code == 401
    assert client.get("/v1/pay/airtime").status_code == 401


def test_airtime_options_follow_the_settings(client: TestClient) -> None:
    body = client.get("/v1/pay/airtime", headers=AUTH).json()
    assert body == {
        "presets_kobo": [10_000, 20_000, 50_000, 100_000],
        "card_min_kobo": 10_000,
        "card_max_kobo": 100_000_000,
    }


def test_buying_a_bundle_by_sms_takes_airtime_and_shows_in_the_balance(client: TestClient) -> None:
    before = client.get(f"/v1/pay/lines/{MSISDN}/balance", headers=AUTH).json()
    assert before == {"balance_kobo": 25_000, "data_bytes_left": 0, "data_valid_to": None}

    bought = _buy(client, 1, "sms-1")
    assert bought.status_code == 200, bought.text  # type: ignore[attr-defined]
    assert bought.json()["name"] == "Daily 500MB"  # type: ignore[attr-defined]
    assert bought.json()["balance_kobo"] == 15_000  # type: ignore[attr-defined]
    again = _buy(client, 1, "sms-1").json()  # type: ignore[attr-defined]
    assert again["replayed"] is True and again["balance_kobo"] == 15_000

    after = client.get(f"/v1/pay/lines/{MSISDN}/balance", headers=AUTH).json()
    assert after["balance_kobo"] == 15_000
    assert after["data_bytes_left"] == GB // 2
    assert after["data_valid_to"] is not None


def test_a_bundle_not_sold_on_the_channel_or_not_covered_is_refused(client: TestClient) -> None:
    assert _buy(client, 2, "k1").status_code == 409  # type: ignore[attr-defined]
    for n in range(2):
        assert _buy(client, 1, f"k{n + 2}").status_code == 200  # type: ignore[attr-defined]
    broke = _buy(client, 1, "k9")
    assert broke.status_code == 409  # type: ignore[attr-defined]
    assert "insufficient_funds" in broke.text  # type: ignore[attr-defined]


def test_an_unknown_number_is_not_found(client: TestClient) -> None:
    assert client.get("/v1/pay/lines/2348099999999/balance", headers=AUTH).status_code == 404
    assert client.get("/v1/pay/lines/12345/balance", headers=AUTH).status_code == 422


def test_bundles_can_be_listed_for_one_channel(client: TestClient) -> None:
    names = [
        b["name"]
        for b in client.get("/v1/pay/bundles?channel=ussd", headers=AUTH).json()["bundles"]
    ]
    assert names == ["Daily 500MB"]


WELCOME = (
    "Welcome to Ratelplus! Your number is 08000010010. "
    "Text MENU to 555 for balance, bundles and top-up."
)


def _queue(client: TestClient, state: str = "active") -> None:
    app = client.app
    with app.state.session_factory() as s, s.begin():  # type: ignore[attr-defined]
        s.get(Line, 1).state = state  # type: ignore[union-attr]
        s.add(CustomerSms(line_id=1, kind="welcome", dedupe_key="welcome:1", text=WELCOME))
        s.add(CustomerSms(line_id=1, kind="call", dedupe_key="call:9", text="Last call ..."))


def test_the_sms_due_come_oldest_first_with_their_text(client: TestClient) -> None:
    assert client.get("/v1/pay/customer-sms", headers=AUTH).json() == {"items": []}
    _queue(client)
    r = client.get("/v1/pay/customer-sms", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {
        "items": [
            {"sms_id": 1, "line_id": 1, "msisdn": MSISDN, "kind": "welcome", "text": WELCOME},
            {"sms_id": 2, "line_id": 1, "msisdn": MSISDN, "kind": "call", "text": "Last call ..."},
        ]
    }
    assert len(client.get("/v1/pay/customer-sms?limit=1", headers=AUTH).json()["items"]) == 1


def test_marking_one_sent_takes_it_off_the_list_and_a_repeat_changes_nothing(
    client: TestClient,
) -> None:
    _queue(client)
    first = client.post("/v1/pay/customer-sms/1/sent", headers=AUTH)
    assert first.status_code == 200 and first.json()["sms_id"] == 1
    again = client.post("/v1/pay/customer-sms/1/sent", headers={**AUTH, "Idempotency-Key": "k"})
    assert again.status_code == 200 and again.json() == first.json()
    items = client.get("/v1/pay/customer-sms", headers=AUTH).json()["items"]
    assert [i["sms_id"] for i in items] == [2]


@pytest.mark.parametrize("state", ["suspended", "terminated"])
def test_a_line_not_in_service_is_sent_nothing(client: TestClient, state: str) -> None:
    _queue(client, state=state)
    assert client.get("/v1/pay/customer-sms", headers=AUTH).json() == {"items": []}


def test_an_out_of_data_line_still_gets_its_sms(client: TestClient) -> None:
    _queue(client, state="out_of_data")
    assert len(client.get("/v1/pay/customer-sms", headers=AUTH).json()["items"]) == 2


def test_marking_an_sms_that_does_not_exist_is_404(client: TestClient) -> None:
    assert client.post("/v1/pay/customer-sms/99/sent", headers=AUTH).status_code == 404


def test_the_sms_queue_needs_the_key(client: TestClient) -> None:
    assert client.get("/v1/pay/customer-sms").status_code == 401
    assert client.post("/v1/pay/customer-sms/1/sent").status_code == 401
