"""A payment provider whose answers a test decides."""

from __future__ import annotations

from app.bss_money.domain.payments import (
    Checkout,
    GatewayError,
    Outcome,
    Verification,
    WebhookEvent,
)


class FakeGateway:
    """A provider whose answers the test decides."""

    name = "fake"

    def __init__(self) -> None:
        self.initialized: list[dict[str, object]] = []
        self.verified: list[str] = []
        self.fail_initialize = False
        self.fail_verify = False
        self.outcome = Outcome.SUCCESS
        self.amount_kobo: int | None = None  # None: whatever was asked
        self.currency = "NGN"
        self.asked: dict[str, int] = {}

    def initialize(
        self, *, amount_kobo: int, reference: str, email: str, callback_url: str
    ) -> Checkout:
        if self.fail_initialize:
            raise GatewayError("the provider could not be reached (ConnectError)")
        self.initialized.append(
            {"amount_kobo": amount_kobo, "reference": reference, "email": email}
        )
        self.asked[reference] = amount_kobo
        return Checkout(url=f"https://checkout.example.invalid/{reference}")

    def verify(self, reference: str) -> Verification:
        self.verified.append(reference)
        if self.fail_verify:
            raise GatewayError("the provider could not be reached (ReadTimeout)")
        amount = self.asked.get(reference, 0) if self.amount_kobo is None else self.amount_kobo
        return Verification(self.outcome, amount, self.currency, "txn-1")

    def signature_valid(self, raw_body: bytes, signature: str) -> bool:
        return signature == "good-signature"

    def parse_event(self, raw_body: bytes) -> WebhookEvent | None:
        text = raw_body.decode()
        return WebhookEvent(text.removeprefix("charge:")) if text.startswith("charge:") else None
