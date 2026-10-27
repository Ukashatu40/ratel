"""The payment routes end to end on SQLite: the real Paystack adapter against a mock of Paystack."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bss_money.gateways.paystack import PaystackGateway
from app.bss_money.models.ledger import LedgerEntry
from app.bss_money.models.payments import Payment
from app.bss_money.repositories.sql import SqlLedgerRepository
from app.config import Settings
from app.db import Base
from app.main import create_app
from tests.app.bss_money.rating_data import seed_line

PAY_KEY = "test-pay-key-not-a-real-key"
AUTH = {"Authorization": f"Bearer {PAY_KEY}"}  # what the reverse proxy adds
PAYSTACK_KEY = "sk_test_example_not_a_real_key"
MSISDN = "2348000000001"
URL = "/v1/pay/payments"
HOOK = "/v1/pay/webhooks/paystack"


class MockPaystack:
    def __init__(self) -> None:
        self.amounts: dict[str, int] = {}
        self.calls: list[str] = []
        self.status = "success"
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(f"{request.method} {request.url.path}")
        if self.down:
            raise httpx.ConnectError("down")
        if request.url.path == "/transaction/initialize":
            body = json.loads(request.content)
            self.amounts[body["reference"]] = body["amount"]
            url = f"https://checkout.paystack.test/{body['reference']}"
            return httpx.Response(200, json={"status": True, "data": {"authorization_url": url}})
        reference = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": {
                    "status": self.status,
                    "amount": self.amounts.get(reference, 0),
                    "currency": "NGN",
                    "id": 7,
                },
            },
        )


class Shop:
    def __init__(self, client: TestClient, paystack: MockPaystack) -> None:
        self.client = client
        self.paystack = paystack
        self.factory = client.app.state.session_factory  # type: ignore[attr-defined]
        with self.factory() as session, session.begin():
            seed_line(session)

    def start(self, amount: int = 150_000, key: str = "key-1", msisdn: str = MSISDN):  # type: ignore[no-untyped-def]
        return self.client.post(
            URL,
            json={"msisdn": msisdn, "amount_kobo": amount},
            headers={**AUTH, "Idempotency-Key": key},
        )

    def reference(self) -> str:
        with self.factory() as session:
            return session.scalars(select(Payment.provider_ref)).one()

    def webhook(self, body: bytes | None = None, *, signature: str | None = None, headers=AUTH):  # type: ignore[no-untyped-def]
        raw = (
            body
            if body is not None
            else json.dumps(
                {"event": "charge.success", "data": {"reference": self.reference()}}
            ).encode()
        )
        sig = (
            hmac.new(PAYSTACK_KEY.encode(), raw, hashlib.sha512).hexdigest()
            if signature is None
            else signature
        )
        return self.client.post(HOOK, content=raw, headers={**headers, "x-paystack-signature": sig})

    def balance(self) -> int | None:
        with self.factory() as session:
            return SqlLedgerRepository(session).balance(1)

    def count(self, table: type) -> int:
        with self.factory() as session:
            return session.scalar(select(func.count()).select_from(table)) or 0


def _app(tmp_path: Path, **overrides: object) -> tuple[TestClient, MockPaystack]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'bss.db'}",  # type: ignore[arg-type]
        pay_api_key=PAY_KEY,  # type: ignore[arg-type]
        paystack_secret_key=PAYSTACK_KEY,  # type: ignore[arg-type]
        payment_callback_url="https://pay.example.invalid/",
        payment_email_domain="example.invalid",
        **overrides,  # type: ignore[arg-type]
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    paystack = MockPaystack()
    client = httpx.Client(
        base_url="https://api.paystack.test", transport=httpx.MockTransport(paystack.handler)
    )
    app.state.payment_gateway = PaystackGateway(PAYSTACK_KEY, client=client)
    return TestClient(app), paystack


@pytest.fixture
def shop(tmp_path: Path) -> Iterator[Shop]:
    client, paystack = _app(tmp_path)
    with client:
        yield Shop(client, paystack)


def test_starting_a_payment_answers_with_the_checkout_page_and_nothing_personal(shop: Shop) -> None:
    response = shop.start()

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"payment_id", "status", "amount_kobo", "checkout_url"}
    assert (body["status"], body["amount_kobo"]) == ("pending", 150_000)
    assert body["checkout_url"] == f"https://checkout.paystack.test/{shop.reference()}"
    assert response.headers["cache-control"] == "no-store"
    assert MSISDN not in response.text  # the number is not echoed
    assert shop.balance() is None


def test_the_same_idempotency_key_is_the_same_payment_and_paystack_is_called_once(
    shop: Shop,
) -> None:
    first = shop.start(key="retry").json()
    again = shop.start(key="retry").json()
    assert again == first
    assert shop.paystack.calls == ["POST /transaction/initialize"]


def test_a_start_without_the_proxy_key_is_refused(shop: Shop) -> None:
    response = shop.client.post(
        URL, json={"msisdn": MSISDN, "amount_kobo": 150_000}, headers={"Idempotency-Key": "k"}
    )
    assert response.status_code == 401
    assert shop.count(Payment) == 0


@pytest.mark.parametrize("headers", [{}, {"Idempotency-Key": ""}])
def test_a_start_needs_an_idempotency_key(shop: Shop, headers: dict[str, str]) -> None:
    response = shop.client.post(
        URL, json={"msisdn": MSISDN, "amount_kobo": 150_000}, headers={**AUTH, **headers}
    )
    assert response.status_code == 422
    assert shop.count(Payment) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"msisdn": "08000000001", "amount_kobo": 150_000},
        {"msisdn": MSISDN, "amount_kobo": "150000"},
        {"msisdn": MSISDN, "amount_kobo": 150000.5},
        {"msisdn": MSISDN, "amount_kobo": 0},
        {"msisdn": MSISDN},
        {"msisdn": MSISDN, "amount_kobo": 150_000, "email": "me@example.invalid"},
    ],
)
def test_a_badly_shaped_start_is_a_422_and_stores_nothing(
    shop: Shop, payload: dict[str, object]
) -> None:
    response = shop.client.post(URL, json=payload, headers={**AUTH, "Idempotency-Key": "k"})
    assert response.status_code == 422
    assert shop.count(Payment) == 0


@pytest.mark.parametrize("case", ["unknown number", "below the minimum", "above the maximum"])
def test_what_cannot_be_started_is_one_400_that_says_nothing_about_the_line(
    shop: Shop, case: str
) -> None:
    kwargs = {
        "unknown number": {"msisdn": "2348099999999"},
        "below the minimum": {"amount": 9_999},
        "above the maximum": {"amount": 100_000_001},
    }[case]
    response = shop.start(**kwargs)  # type: ignore[arg-type]
    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "payment_refused", "message": "This payment cannot be started."}
    }
    assert shop.count(Payment) == 0


def test_payments_answer_503_until_the_deployment_configures_them(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'x.db'}", pay_api_key=PAY_KEY)  # type: ignore[arg-type]
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        started = client.post(
            URL,
            json={"msisdn": MSISDN, "amount_kobo": 150_000},
            headers={**AUTH, "Idempotency-Key": "k"},
        )
        hook = client.post(
            HOOK, content=b"{}", headers={**AUTH, "x-paystack-signature": "anything"}
        )
        assert (started.status_code, hook.status_code) == (503, 503)
        assert started.json()["error"]["code"] == "unavailable"


def test_if_paystack_is_down_the_start_is_a_503_and_nothing_is_charged(shop: Shop) -> None:
    shop.paystack.down = True
    response = shop.start()
    assert response.status_code == 503
    assert shop.count(LedgerEntry) == 0


def test_the_status_page_shows_the_status_and_nothing_about_the_line(shop: Shop) -> None:
    started = shop.start().json()

    response = shop.client.get(f"{URL}/{started['payment_id']}", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "payment_id": started["payment_id"],
        "status": "pending",
        "amount_kobo": 150_000,
    }
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("payment_id", ["short", "x" * 70, "a-valid-looking-but-unknown-id"])
def test_an_unknown_payment_is_a_404(shop: Shop, payment_id: str) -> None:
    assert shop.client.get(f"{URL}/{payment_id}", headers=AUTH).status_code == 404


def test_a_signed_notification_is_verified_with_paystack_and_credits_the_wallet_once(
    shop: Shop,
) -> None:
    started = shop.start().json()

    first = shop.webhook()
    second = shop.webhook()

    assert (first.status_code, first.json()) == (200, {"received": True})
    assert second.status_code == 200
    assert shop.balance() == 150_000
    assert shop.count(LedgerEntry) == 1
    assert (
        shop.paystack.calls.count(f"GET /transaction/verify/{shop.reference()}") == 1
    )  # the 2nd needed none
    status = shop.client.get(f"{URL}/{started['payment_id']}", headers=AUTH).json()
    assert status["status"] == "succeeded"


def test_a_notification_with_a_wrong_or_missing_signature_is_a_401_and_nothing_is_asked_or_credited(
    shop: Shop,
) -> None:
    shop.start()
    shop.paystack.calls.clear()

    assert shop.webhook(signature="0" * 128).status_code == 401
    assert shop.webhook(signature="").status_code == 401
    no_header = shop.client.post(HOOK, content=b"{}", headers=AUTH)
    assert no_header.status_code == 401

    assert shop.paystack.calls == []
    assert shop.balance() is None


def test_the_signature_is_over_the_exact_bytes_that_were_sent(shop: Shop) -> None:
    shop.start()
    raw = json.dumps({"event": "charge.success", "data": {"reference": shop.reference()}}).encode()
    signature = hmac.new(PAYSTACK_KEY.encode(), raw, hashlib.sha512).hexdigest()
    reformatted = json.dumps(json.loads(raw), indent=2).encode()  # the same JSON, other bytes

    assert shop.webhook(reformatted, signature=signature).status_code == 401
    assert shop.webhook(raw, signature=signature).status_code == 200


def test_a_correctly_signed_notification_still_needs_the_proxy_key(shop: Shop) -> None:
    shop.start()
    assert shop.webhook(headers={}).status_code == 401
    assert shop.balance() is None


def test_a_notification_about_something_else_is_acknowledged_and_ignored(shop: Shop) -> None:
    shop.start()
    shop.paystack.calls.clear()
    response = shop.webhook(
        json.dumps({"event": "transfer.success", "data": {"reference": "x"}}).encode()
    )
    assert (response.status_code, response.json()) == (200, {"received": True})
    assert shop.paystack.calls == []


def test_a_notification_for_a_reference_we_never_made_is_acknowledged_and_changes_nothing(
    shop: Shop,
) -> None:
    shop.start()
    response = shop.webhook(
        json.dumps({"event": "charge.success", "data": {"reference": "rp-nobody"}}).encode()
    )
    assert response.status_code == 200
    assert shop.balance() is None


def test_a_notification_that_lies_is_not_believed_because_paystack_is_asked(shop: Shop) -> None:
    shop.start()
    shop.paystack.status = "failed"
    assert shop.webhook().status_code == 200
    assert shop.balance() is None


def test_if_paystack_cannot_be_asked_the_notification_gets_a_503_so_it_is_delivered_again(
    shop: Shop,
) -> None:
    shop.start()
    shop.paystack.down = True
    assert shop.webhook().status_code == 503
    assert shop.balance() is None

    shop.paystack.down = False
    assert shop.webhook().status_code == 200  # the redelivery
    assert shop.balance() == 150_000


def test_neither_answers_nor_logs_hold_the_paystack_key_a_signature_or_the_checkout_address(
    shop: Shop, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    started = shop.start()
    raw = json.dumps({"event": "charge.success", "data": {"reference": shop.reference()}}).encode()
    signature = hmac.new(PAYSTACK_KEY.encode(), raw, hashlib.sha512).hexdigest()
    answers = [
        started.text,
        shop.webhook(raw, signature=signature).text,
        shop.webhook(raw, signature="bad").text,
    ]

    everything = " ".join(answers) + " ".join(
        f"{r.getMessage()} {r.__dict__}" for r in caplog.records
    )
    assert PAYSTACK_KEY not in everything and PAY_KEY not in everything
    assert signature not in everything
    assert "checkout.paystack.test" not in " ".join(
        f"{r.getMessage()} {r.__dict__}" for r in caplog.records
    )
    assert MSISDN not in everything
