"""The Paystack adapter against a mock of Paystack's API (it has not met the real one yet).

The signature vector below was made with `openssl dgst -sha512 -hmac`, not with the code under test.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.bss_money.domain.payments import GatewayError, Outcome
from app.bss_money.gateways.paystack import PaystackGateway

KEY = "sk_test_example_not_a_real_key"
BODY = b'{"event":"charge.success","data":{"reference":"rpabc123"}}'
SIGNATURE = (
    "7c67358cb022b408953ca4c54b31a9a65b831f6bf746d66b1702b2fd00588ee9"
    "9de27fda330bc38bcbd720550f8ad8d03c479c66ceb6c4993355f040e582786f"
)


class Paystack:
    """A mock Paystack: records each request and answers from a script."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.document: object = {"status": True, "data": {}}
        self.raises: Exception | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raises is not None:
            raise self.raises
        return httpx.Response(self.status, json=self.document)

    def gateway(self) -> PaystackGateway:
        client = httpx.Client(
            base_url="https://api.paystack.test", transport=httpx.MockTransport(self.handler)
        )
        return PaystackGateway(KEY, client=client)


@pytest.fixture
def paystack() -> Paystack:
    return Paystack()


def test_initialize_posts_the_amount_in_kobo_with_the_key_and_returns_the_checkout_page(
    paystack: Paystack,
) -> None:
    paystack.document = {
        "status": True,
        "data": {
            "authorization_url": "https://checkout.paystack.test/abc",
            "access_code": "x",
            "reference": "r",
        },
    }

    checkout = paystack.gateway().initialize(
        amount_kobo=150_000,
        reference="rpabc",
        email="pay@example.invalid",
        callback_url="https://pay.example.invalid/",
    )

    assert checkout.url == "https://checkout.paystack.test/abc"
    [request] = paystack.requests
    assert (request.method, request.url.path) == ("POST", "/transaction/initialize")
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {
        "email": "pay@example.invalid",
        "amount": 150_000,  # an integer number of kobo, never a decimal
        "currency": "NGN",
        "reference": "rpabc",
        "callback_url": "https://pay.example.invalid/",
    }


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"authorization_url": 5},
        {"authorization_url": "http://insecure.example/x"},
        {"authorization_url": ""},
    ],
)
def test_a_checkout_page_that_is_missing_or_not_https_is_refused(
    paystack: Paystack, data: dict[str, object]
) -> None:
    paystack.document = {"status": True, "data": data}
    with pytest.raises(GatewayError):
        paystack.gateway().initialize(
            amount_kobo=1, reference="r", email="e@x.invalid", callback_url="https://x.invalid/"
        )


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
def test_an_error_from_paystack_is_a_gateway_error_without_its_body_or_the_key(
    paystack: Paystack, status: int
) -> None:
    paystack.status = status
    paystack.document = {"status": False, "message": f"secret detail {KEY}"}
    with pytest.raises(GatewayError) as caught:
        paystack.gateway().verify("rpabc")
    assert str(status) in str(caught.value)
    assert KEY not in str(caught.value) and "secret detail" not in str(caught.value)


def test_a_network_failure_is_a_gateway_error_that_names_only_its_kind(paystack: Paystack) -> None:
    paystack.raises = httpx.ConnectError(f"cannot reach https://api.paystack.test?key={KEY}")
    with pytest.raises(GatewayError) as caught:
        paystack.gateway().verify("rpabc")
    assert "ConnectError" in str(caught.value)
    assert KEY not in str(caught.value) and "api.paystack" not in str(caught.value)


def test_an_unreadable_answer_is_a_gateway_error(paystack: Paystack) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not json</html>")

    client = httpx.Client(
        base_url="https://api.paystack.test", transport=httpx.MockTransport(broken)
    )
    with pytest.raises(GatewayError):
        PaystackGateway(KEY, client=client).verify("rpabc")


@pytest.mark.parametrize(
    ("paystack_status", "outcome"),
    [
        ("success", Outcome.SUCCESS),
        ("SUCCESS", Outcome.SUCCESS),
        ("failed", Outcome.FAILED),
        ("abandoned", Outcome.FAILED),
        ("reversed", Outcome.FAILED),
        ("pending", Outcome.PENDING),
        ("ongoing", Outcome.PENDING),
        ("processing", Outcome.PENDING),
        ("something new", Outcome.PENDING),  # an unknown word is never taken for a success
        ("", Outcome.PENDING),
    ],
)
def test_the_status_words_map_to_an_outcome_and_only_success_is_a_success(
    paystack: Paystack, paystack_status: str, outcome: Outcome
) -> None:
    paystack.document = {
        "status": True,
        "data": {
            "status": paystack_status,
            "amount": 150_000,
            "currency": "ngn",
            "id": 4099260516,
            "reference": "rpabc",
        },
    }

    verification = paystack.gateway().verify("rpabc")

    assert verification.outcome is outcome
    assert (verification.amount_kobo, verification.currency, verification.provider_txn_id) == (
        150_000,
        "NGN",
        "4099260516",
    )
    assert paystack.requests[0].url.path == "/transaction/verify/rpabc"
    assert paystack.requests[0].method == "GET"


def test_a_reference_paystack_does_not_know_yet_is_pending_not_an_error(paystack: Paystack) -> None:
    paystack.status = 404
    paystack.document = {"status": False, "message": "Transaction reference not found"}
    assert paystack.gateway().verify("rpabc").outcome is Outcome.PENDING


@pytest.mark.parametrize("amount", ["150000", 1500.5, None, True])
def test_an_amount_that_is_not_a_whole_number_of_kobo_counts_as_zero_and_so_never_matches(
    paystack: Paystack, amount: object
) -> None:
    paystack.document = {
        "status": True,
        "data": {"status": "success", "amount": amount, "currency": "NGN"},
    }
    assert paystack.gateway().verify("rpabc").amount_kobo == 0


def test_a_known_signature_is_accepted() -> None:
    assert PaystackGateway(KEY).signature_valid(BODY, SIGNATURE)
    assert PaystackGateway(KEY).signature_valid(BODY, SIGNATURE.upper())  # hex has no case
    assert PaystackGateway(KEY).signature_valid(BODY, f"  {SIGNATURE}\n")


@pytest.mark.parametrize(
    "case",
    ["empty", "garbage", "one byte of the body changed", "another key", "a prefix", "truncated"],
)
def test_anything_else_is_refused(case: str) -> None:
    gateway = PaystackGateway(KEY)
    body, signature, other = BODY, SIGNATURE, PaystackGateway("sk_test_another_key")
    if case == "empty":
        assert not gateway.signature_valid(body, "")
    elif case == "garbage":
        assert not gateway.signature_valid(body, "not a signature")
    elif case == "one byte of the body changed":
        assert not gateway.signature_valid(body.replace(b"abc123", b"abc124"), signature)
    elif case == "another key":
        assert not other.signature_valid(body, signature)
    elif case == "a prefix":
        assert not gateway.signature_valid(body, signature[:64])
    else:
        assert not gateway.signature_valid(body, signature[:-1])


def test_the_signature_is_over_the_raw_bytes_not_the_parsed_json() -> None:
    reformatted = json.dumps(json.loads(BODY), indent=2).encode()  # the same JSON, other bytes
    assert not PaystackGateway(KEY).signature_valid(reformatted, SIGNATURE)


def test_only_a_successful_charge_is_an_event() -> None:
    gateway = PaystackGateway(KEY)
    event = gateway.parse_event(BODY)
    assert event is not None and event.reference == "rpabc123"
    for body in (
        b'{"event":"transfer.success","data":{"reference":"x"}}',
        b'{"event":"charge.failed","data":{"reference":"x"}}',
        b'{"event":"charge.success","data":{}}',
        b'{"event":"charge.success","data":{"reference":""}}',
        b'{"event":"charge.success","data":{"reference":5}}',
        b'{"event":"charge.success"}',
        b"[1, 2]",
        b"not json",
        b"",
    ):
        assert gateway.parse_event(body) is None, body


def test_a_key_is_required() -> None:
    with pytest.raises(ValueError):
        PaystackGateway("")
