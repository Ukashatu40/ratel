"""Top-ups paid through a payment gateway: the states, the amounts, and what a gateway must do.

Pure: no database, no clock, no network. The rules (Build Plan, RatelBSS: money; PRODUCT_RULES.md,
Payments):
- Credit a payment only after **verifying the webhook's signature and re-querying the transaction
  with the provider**. The webhook says "go and look"; the re-query is what is believed.
- `provider_ref` is unique, so a webhook delivered twice credits once.
- One payment row per provider transaction: provider, amount_kobo, status and line_id.
- One gateway for the first release. The interface below is what any gateway has to provide, so a
  second one is an adapter and no rule changes (decision 6: Paystack first; OPay after the demo).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

CURRENCY = "NGN"
# TODO(PRD): the lowest and highest amount a customer may pay. These are sanity bounds, settings in
# the deployment (PAYMENT_MIN_KOBO, PAYMENT_MAX_KOBO), not product values.
DEFAULT_MIN_KOBO = 10_000  # 100 naira
DEFAULT_MAX_KOBO = 100_000_000  # 1,000,000 naira
# A payment that has not been completed this long after it was started is given up.
ABANDON_AFTER_SECONDS = 24 * 60 * 60


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"  # verified with the provider and credited, exactly once
    FAILED = "failed"  # the provider says it did not go through, or it was never completed


class Outcome(StrEnum):
    """What the provider says about a transaction when asked."""

    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


@dataclass(frozen=True)
class Verification:
    outcome: Outcome
    amount_kobo: int
    currency: str
    provider_txn_id: str | None


@dataclass(frozen=True)
class Checkout:
    """Where to send the customer to pay."""

    url: str


@dataclass(frozen=True)
class WebhookEvent:
    """A provider notification that matters: a charge went through. Others are not modelled."""

    reference: str


class GatewayError(Exception):
    """The provider could not be reached or answered something unusable. Carries no body or key."""


class PaymentGateway(Protocol):
    """What the app needs from a payment provider."""

    name: str

    def initialize(
        self, *, amount_kobo: int, reference: str, email: str, callback_url: str
    ) -> Checkout:
        """Start a transaction for `reference` and return where the customer pays."""
        ...

    def verify(self, reference: str) -> Verification:
        """Ask the provider what became of `reference`. This is the answer that is believed."""
        ...

    def signature_valid(self, raw_body: bytes, signature: str) -> bool:
        """Is `signature` the provider's signature of exactly these bytes? Constant time."""
        ...

    def parse_event(self, raw_body: bytes) -> WebhookEvent | None:
        """The event, if the body is a successful charge; None for any other event or garbage."""
        ...


def new_provider_ref() -> str:
    """A reference nobody can guess, using only letters and digits (providers restrict the rest)."""
    return "rp" + secrets.token_hex(20)


def new_public_id() -> str:
    """The id RatelPay is given. Anyone who has it can read the payment, so it cannot be guessed."""
    return secrets.token_urlsafe(24)


def check_amount(amount_kobo: object, minimum: int, maximum: int) -> int:
    """The amount if it is a whole number of kobo inside the allowed range, else ValueError."""
    if isinstance(amount_kobo, bool) or not isinstance(amount_kobo, int):
        raise ValueError("the amount must be a whole number of kobo")
    if not minimum <= amount_kobo <= maximum:
        raise ValueError("the amount is outside the allowed range")
    return amount_kobo
