"""Paystack, as a `PaymentGateway`.

What it does, and what it deliberately does not:
- `initialize` starts a transaction and returns the page the customer pays on.
- `verify` asks Paystack what became of a reference. It is the answer that is believed: a webhook
  only tells us to ask.
- `signature_valid` checks a webhook's `x-paystack-signature`, the HMAC-SHA512 of the **raw bytes**
  of the body keyed with the secret key, in constant time.
- Nothing here logs a body, a key or a customer's details, and an error carries only its kind.

The endpoints and the status words follow Paystack's public API (initialize, verify, webhooks).
Paystack's documentation could not be fetched while this was written, so the adapter is proven
against a mock of that API only: **it must be tried once against Paystack's test mode** (a test key
and a test card) before anyone relies on it. See docs/runbooks/bss-app.md, "Payments".
"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx

from app.bss_money.domain.payments import (
    CURRENCY,
    Checkout,
    GatewayError,
    Outcome,
    Verification,
    WebhookEvent,
)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# Only a payment Paystack has given back (or cancelled) is over. "abandoned" (not finished yet) and
# "failed" (the last card attempt was declined) are not here on purpose: the customer can still try
# another card on the same payment, and a failure marked final would leave them charged for nothing
# (decided 2026-10-28; "abandoned" found against Paystack's test mode). Such a payment stays pending
# until ABANDON_AFTER_SECONDS gives it up, and is never credited without a verified success.
_FAILED = {"reversed", "cancelled"}


class PaystackGateway:
    name = "paystack"

    def __init__(
        self,
        secret_key: str,
        *,
        base_url: str = "https://api.paystack.co",
        client: httpx.Client | None = None,
    ) -> None:
        if not secret_key:
            raise ValueError("a Paystack secret key is required")
        self._secret = secret_key.encode()
        self._client = client or httpx.Client(
            base_url=base_url, timeout=_TIMEOUT, follow_redirects=False
        )
        self._headers = {"Authorization": f"Bearer {secret_key}", "Accept": "application/json"}

    def initialize(
        self, *, amount_kobo: int, reference: str, email: str, callback_url: str
    ) -> Checkout:
        body = {
            "email": email,
            "amount": amount_kobo,  # Paystack takes the smallest unit, which is kobo
            "currency": CURRENCY,
            "reference": reference,
            "callback_url": callback_url,
        }
        data = self._call("POST", "/transaction/initialize", json=body)
        url = data.get("authorization_url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise GatewayError("the provider gave no checkout page")
        return Checkout(url=url)

    def verify(self, reference: str) -> Verification:
        try:
            data = self._call("GET", f"/transaction/verify/{reference}")
        except _NotFound:
            # Paystack does not know the reference yet: the customer has not got as far as paying.
            return Verification(Outcome.PENDING, 0, CURRENCY, None)
        status = str(data.get("status", "")).lower()
        amount = data.get("amount")
        txn_id = data.get("id")
        outcome = (
            Outcome.SUCCESS
            if status == "success"
            else Outcome.FAILED
            if status in _FAILED
            else Outcome.PENDING
        )
        return Verification(
            outcome=outcome,
            amount_kobo=amount if isinstance(amount, int) and not isinstance(amount, bool) else 0,
            currency=str(data.get("currency", "")).upper(),
            provider_txn_id=None if txn_id is None else str(txn_id)[:64],
        )

    def signature_valid(self, raw_body: bytes, signature: str) -> bool:
        expected = hmac.new(self._secret, raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected.encode(), signature.strip().lower().encode())

    def parse_event(self, raw_body: bytes) -> WebhookEvent | None:
        try:
            document = json.loads(raw_body)
        except ValueError:
            return None
        if not isinstance(document, dict) or document.get("event") != "charge.success":
            return None
        data = document.get("data")
        reference = data.get("reference") if isinstance(data, dict) else None
        if not isinstance(reference, str) or not reference:
            return None
        return WebhookEvent(reference=reference)

    def _call(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
        try:
            response = self._client.request(method, path, headers=self._headers, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            raise GatewayError(
                f"the provider could not be reached ({type(exc).__name__})"
            ) from None
        if response.status_code == 404:
            raise _NotFound
        if response.status_code >= 400:
            raise GatewayError(f"the provider refused the call (HTTP {response.status_code})")
        try:
            document = response.json()
        except ValueError:
            raise GatewayError("the provider answered something unreadable") from None
        data = document.get("data") if isinstance(document, dict) else None
        if not isinstance(data, dict) or document.get("status") is False:
            raise GatewayError("the provider answered without a result")
        return data


class _NotFound(GatewayError):
    """The provider does not know this reference."""

    def __init__(self) -> None:
        super().__init__("unknown reference")
