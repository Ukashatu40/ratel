"""Top-ups paid through a gateway (M-19): start a payment, believe the provider, credit once.

The order that makes it safe:

1. **Start.** A pending row is written and committed *before* the provider is called, so a crash
   leaves a pending row and not a customer who paid for nothing. The provider's checkout page
   is then stored on the row. A retry with the same Idempotency-Key is the same payment.
2. **Notification (webhook).** Its signature is checked on the raw bytes first, and nothing else is
   read from an unsigned request. A signed notification only says "go and look".
3. **Settle.** The provider is asked what became of the reference (outside any transaction, because
   it is a network call). Only a `success` for the **same amount in naira** is believed. Then,
   in one transaction with the payment row locked: the wallet is credited (a ledger entry whose
   reference is the payment, so even a bug could not credit it twice) and the row is marked
   succeeded. Delivered twice, or at the same moment twice, it credits once.

A webhook is not needed for this to work: `settle_pending` (run by the rating job every five
minutes) and a customer's own status check settle a payment the same way, which is what makes
the lab work without a public notification address.

Nothing here logs a key, a signature, a body, a phone number or a checkout address.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.bss_money.domain.entries import new_posting
from app.bss_money.domain.payments import (
    ABANDON_AFTER_SECONDS,
    CURRENCY,
    GatewayError,
    Outcome,
    PaymentGateway,
    PaymentStatus,
    check_amount,
    new_provider_ref,
    new_public_id,
)
from app.bss_money.domain.vouchers import is_msisdn
from app.bss_money.repositories.ports import DuplicateKey, PaymentScope, StoredPayment
from app.bss_money.services.ledger import post_entry
from common.logging import log_event

log = logging.getLogger("ratel.bss.money.payments")

# A customer's own status check re-asks the provider only once the payment is this old, so a page
# polling every second does not become a flood of calls to the provider.
POLL_AFTER_SECONDS = 15
SETTLE_LIMIT = 50  # payments settled per run of the rating job


class PaymentRefused(Exception):
    """The payment cannot be started (a number that cannot be topped up, an amount out of range)."""


class GatewayUnavailable(Exception):
    """The provider could not be reached. A payment being started was marked failed."""


class InvalidSignature(Exception):
    """A notification whose signature is not the provider's."""


class SettleStatus(StrEnum):
    CREDITED = "credited"
    ALREADY = "already"  # it had been credited before: nothing changed
    PENDING = "pending"  # the provider says it has not completed yet
    FAILED = "failed"
    UNKNOWN = "unknown"  # no payment of ours has this reference
    MISMATCH = "mismatch"  # the provider says success, for another amount or currency: not credited


@dataclass(frozen=True)
class PaymentView:
    """What the customer's page may see: nothing about the line or its owner (TOP-2)."""

    public_id: str
    status: PaymentStatus
    amount_kobo: int
    checkout_url: str | None


def start_payment(
    scope: PaymentScope,
    gateway: PaymentGateway,
    *,
    msisdn: str,
    amount_kobo: int,
    idempotency_key: str,
    callback_url: str,
    payer_email: str,
    minimum: int,
    maximum: int,
) -> PaymentView:
    """Start a payment for the line with this number and return where the customer pays."""
    if not is_msisdn(msisdn) or not idempotency_key.strip():
        raise PaymentRefused("the request is not valid")
    try:
        amount = check_amount(amount_kobo, minimum, maximum)
    except ValueError as exc:
        raise PaymentRefused(str(exc)) from None

    with scope() as repositories:
        earlier = repositories.payments.by_idempotency_key(idempotency_key)
        if earlier is None:
            line_id = repositories.lines.line_id_for_msisdn(msisdn)
            if line_id is None:
                raise PaymentRefused("this number cannot be topped up")
            try:
                payment = repositories.payments.add(
                    public_id=new_public_id(),
                    line_id=line_id,
                    provider=gateway.name,
                    provider_ref=new_provider_ref(),
                    idempotency_key=idempotency_key,
                    amount_kobo=amount,
                )
            except DuplicateKey:  # the same key raced us and won
                earlier = repositories.payments.by_idempotency_key(idempotency_key)
                if earlier is None:
                    raise
    if earlier is not None:
        # The same key again is the same payment, whatever this request says, and the provider is
        # called only by the request that created it: a second call with the same reference would be
        # refused by the provider and must never be allowed to mark the first one failed. A retry
        # that raced the first may see no checkout page yet; it asks again, or starts anew.
        return _view(earlier)

    try:
        checkout = gateway.initialize(
            amount_kobo=payment.amount_kobo,
            reference=payment.provider_ref,
            email=payer_email,
            callback_url=callback_url,
        )
    except GatewayError as exc:
        with scope() as repositories:
            repositories.payments.mark_failed(payment.payment_id, None)
        log_event(
            log,
            logging.ERROR,
            "payment.start_failed",
            payment_id=payment.payment_id,
            reason=str(exc),
        )
        raise GatewayUnavailable("the payment provider is not available") from None
    with scope() as repositories:
        repositories.payments.set_checkout(payment.payment_id, checkout.url)
    log_event(
        log,
        logging.INFO,
        "payment.started",
        payment_id=payment.payment_id,
        amount_kobo=payment.amount_kobo,
    )
    return PaymentView(payment.public_id, PaymentStatus.PENDING, payment.amount_kobo, checkout.url)


def handle_webhook(
    scope: PaymentScope, gateway: PaymentGateway, *, raw_body: bytes, signature: str, now: datetime
) -> SettleStatus | None:
    """A provider notification. Raises `InvalidSignature` before reading anything from it.

    Returns what became of the payment it names, or None for an event that is not a charge.
    """
    if not signature or not gateway.signature_valid(raw_body, signature):
        raise InvalidSignature
    event = gateway.parse_event(raw_body)
    if event is None:
        return None
    return settle_payment(scope, gateway, event.reference, now)


def settle_payment(
    scope: PaymentScope, gateway: PaymentGateway, reference: str, now: datetime
) -> SettleStatus:
    """Ask the provider about `reference` and, if it truly succeeded, credit the wallet once."""
    with scope() as repositories:
        payment = repositories.payments.by_reference(reference)
    if payment is None:
        log_event(log, logging.WARNING, "payment.unknown_reference")
        return SettleStatus.UNKNOWN
    if payment.status != PaymentStatus.PENDING.value:
        return (
            SettleStatus.ALREADY
            if payment.status == PaymentStatus.SUCCEEDED.value
            else SettleStatus.FAILED
        )

    try:
        verification = gateway.verify(reference)  # a network call: no transaction is open
    except GatewayError as exc:
        log_event(
            log,
            logging.ERROR,
            "payment.verify_failed",
            payment_id=payment.payment_id,
            reason=str(exc),
        )
        raise GatewayUnavailable("the payment provider is not available") from None

    with scope() as repositories:
        locked = repositories.payments.by_reference(reference, lock=True)
        if locked is None or locked.status != PaymentStatus.PENDING.value:
            return SettleStatus.ALREADY  # another request settled it while we asked the provider
        if verification.outcome is Outcome.PENDING:
            if (now - locked.created_at).total_seconds() > ABANDON_AFTER_SECONDS:
                repositories.payments.mark_failed(locked.payment_id, verification.provider_txn_id)
                return SettleStatus.FAILED
            return SettleStatus.PENDING
        if verification.outcome is Outcome.FAILED:
            repositories.payments.mark_failed(locked.payment_id, verification.provider_txn_id)
            log_event(log, logging.INFO, "payment.failed", payment_id=locked.payment_id)
            return SettleStatus.FAILED
        if verification.amount_kobo != locked.amount_kobo or verification.currency != CURRENCY:
            # The provider says it was paid, but not what we asked for. Nothing is credited, and a
            # person has to look: this is either a bug or someone tampering.
            repositories.payments.mark_failed(locked.payment_id, verification.provider_txn_id)
            log_event(
                log,
                logging.ERROR,
                "payment.amount_mismatch",
                payment_id=locked.payment_id,
                expected_kobo=locked.amount_kobo,
                got_kobo=verification.amount_kobo,
            )
            return SettleStatus.MISMATCH
        post_entry(
            repositories.ledger,
            new_posting(
                locked.line_id, locked.amount_kobo, "top_up", f"payment-{locked.payment_id}"
            ),
        )
        repositories.payments.mark_succeeded(locked.payment_id, verification.provider_txn_id, now)
    log_event(
        log, logging.INFO, "payment.credited", payment_id=locked.payment_id, line_id=locked.line_id
    )
    return SettleStatus.CREDITED


def settle_pending(scope: PaymentScope, gateway: PaymentGateway, now: datetime) -> int:
    """Settle payments that are still pending after a minute. Returns how many were credited.

    This is what makes the system work without a webhook, and what catches a notification that never
    came. One payment's trouble (the provider down, an odd answer) does not stop the others.
    """
    with scope() as repositories:
        references = repositories.payments.pending_references(
            now - timedelta(seconds=60), SETTLE_LIMIT
        )
    credited = 0
    for reference in references:
        try:
            if settle_payment(scope, gateway, reference, now) is SettleStatus.CREDITED:
                credited += 1
        except GatewayUnavailable:
            break  # the provider is down: the rest would fail too, and the next run retries
        except Exception as exc:
            log_event(log, logging.ERROR, "payment.settle_failed", exc_type=type(exc).__name__)
    return credited


def get_payment(
    scope: PaymentScope, gateway: PaymentGateway | None, public_id: str, now: datetime
) -> PaymentView | None:
    """A payment's status for the customer's page. None if there is no such payment.

    A pending one that is old enough is settled first, so the page does not depend on a webhook.
    """
    with scope() as repositories:
        payment = repositories.payments.by_public_id(public_id)
    if payment is None:
        return None
    if (
        gateway is not None
        and payment.status == PaymentStatus.PENDING.value
        and (now - payment.created_at).total_seconds() >= POLL_AFTER_SECONDS
    ):
        try:
            settle_payment(scope, gateway, payment.provider_ref, now)
        except GatewayUnavailable:
            pass  # show what we know; the page asks again
        with scope() as repositories:
            payment = repositories.payments.by_public_id(public_id) or payment
    return _view(payment)


def _view(payment: StoredPayment) -> PaymentView:
    return PaymentView(
        payment.public_id, PaymentStatus(payment.status), payment.amount_kobo, payment.checkout_url
    )
