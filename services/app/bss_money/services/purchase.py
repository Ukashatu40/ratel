"""Buying a plan or a bundle from the wallet (M-16), and renewing a plan when a top-up covers it.

One transaction does all of it, so a purchase is whole or not at all:
- the line is locked (two purchases for one line take turns, so the wallet cannot be overdrawn);
- the wallet is debited by the offer's price, as two ledger entries: the purchase and, on its own,
  the VAT (docs/PRODUCT_RULES.md), both under one reference;
- one allowance bucket is created, valid from now for the offer's validity.

It does **not** touch the line's state or RatelLink. A line that was out of data or expired is
brought back by the rating job, which sees the new allowance on its next run (and retries if
RatelLink was down), so a RatelLink outage never undoes a payment.

Idempotent: the same `reference` again changes nothing and returns the first result (`replayed`).
Nothing here logs a name, a phone number or a balance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from app.bss_lines.domain.state_machine import LineState
from app.bss_money.domain.allowance import bucket_for
from app.bss_money.domain.entries import new_posting
from app.bss_money.domain.plans import Bundle, Plan
from app.bss_money.domain.purchase import OfferKind, split_vat
from app.bss_money.repositories.ports import PurchaseRepositories, PurchaseScope
from app.bss_money.services.ledger import post_entry
from common.logging import log_event

log = logging.getLogger("ratel.bss.money.purchase")

# TODO(PRD): which states may buy. A suspended line is a care decision and a terminated one is over.
_CANNOT_BUY = frozenset({LineState.SUSPENDED, LineState.TERMINATED})


class PurchaseError(Exception):
    """A purchase that was refused. Nothing was changed."""


class LineNotFound(PurchaseError):
    pass


class LineCannotBuy(PurchaseError):
    pass


class OfferNotAvailable(PurchaseError):
    pass


class InsufficientFunds(PurchaseError):
    def __init__(self, shortfall_kobo: int) -> None:
        super().__init__("the wallet does not cover the price")
        self.shortfall_kobo = shortfall_kobo


@dataclass(frozen=True)
class PurchaseResult:
    price_kobo: int
    net_kobo: int
    vat_kobo: int
    balance_kobo: int
    bucket_id: int | None  # None when this was a replay of an earlier purchase
    valid_to: datetime | None
    replayed: bool = False


def buy_offer(
    scope: PurchaseScope,
    *,
    line_id: int,
    kind: OfferKind,
    offer_id: int,
    reference: str,
    now: datetime,
    vat_rate_bps: int,
) -> PurchaseResult:
    """Debit the line's wallet for the offer and create its allowance bucket."""
    _require_utc(now)
    with scope() as repositories:
        line = repositories.purchases.lock_line(line_id)
        if line is None:
            raise LineNotFound("no such line")
        if line.state in _CANNOT_BUY:
            raise LineCannotBuy("this line cannot buy in its current state")
        offer = _offer(repositories, kind, offer_id)
        return _buy_locked(repositories, line_id, kind, offer, reference, now, vat_rate_bps)


def renew_plan_if_covered(
    scope: PurchaseScope, *, line_id: int, now: datetime, vat_rate_bps: int
) -> PurchaseResult | None:
    """Buy the line's own plan again, if it ran out and the wallet covers it. None if not.

    Only for a line that is out of data or expired, has no allowance left or coming, and whose plan
    is still on sale and costs something. Bought at most once per second per line (the reference
    carries the time), and once it is bought the line has allowance, so the next run does nothing.

    TODO(PRD): automatic renewal is a product decision. It is off unless the deployment turns it on
    (RATING_AUTO_RENEW), and it is what makes "top up and data returns" work without a customer
    choosing a bundle.
    """
    _require_utc(now)
    with scope() as repositories:
        line = repositories.purchases.lock_line(line_id)
        if line is None or line.state not in (LineState.OUT_OF_DATA, LineState.EXPIRED):
            return None
        if any(
            b.remaining_bytes > 0 and (b.is_valid_at(now) or b.valid_from > now)
            for b in repositories.purchases.buckets(line_id)
        ):
            return None  # allowance is there, or on its way: nothing to buy
        plan = repositories.purchases.get_offer(OfferKind.PLAN, line.plan.plan_id)
        if plan is None or plan.price_kobo <= 0:
            return None
        balance = repositories.ledger.balance(line_id) or 0
        if balance < plan.price_kobo:
            return None
        reference = f"auto-renew-{line_id}-{int(now.timestamp())}"
        return _buy_locked(
            repositories, line_id, OfferKind.PLAN, plan, reference, now, vat_rate_bps
        )


def _offer(repositories: PurchaseRepositories, kind: OfferKind, offer_id: int) -> Plan | Bundle:
    try:
        offer = repositories.purchases.get_offer(kind, offer_id)
    except ValueError:  # a stored row that does not pass the offer's own rules
        raise OfferNotAvailable("this offer cannot be sold") from None
    if offer is None:
        raise OfferNotAvailable("no such offer on sale")
    if offer.price_kobo <= 0:
        # TODO(PRD): free offers. The ledger refuses a zero entry, and a purchase with no entry
        # could not be made idempotent, so they are not sold until the PRD says how.
        raise OfferNotAvailable("free offers cannot be bought yet")
    return offer


def _buy_locked(
    repositories: PurchaseRepositories,
    line_id: int,
    kind: OfferKind,
    offer: Plan | Bundle,
    reference: str,
    now: datetime,
    vat_rate_bps: int,
) -> PurchaseResult:
    price = offer.price_kobo
    net, vat = split_vat(price, vat_rate_bps)
    earlier = repositories.ledger.find(line_id, "purchase", reference)
    if earlier is not None:  # the same reference again: the first purchase stands, nothing changes
        earlier_vat = repositories.ledger.find(line_id, "vat", reference)
        net_paid = -earlier.amount_kobo
        vat_paid = 0 if earlier_vat is None else -earlier_vat.amount_kobo
        balance_now = repositories.ledger.balance(line_id) or 0
        return PurchaseResult(
            net_paid + vat_paid, net_paid, vat_paid, balance_now, None, None, replayed=True
        )
    balance = repositories.ledger.balance(line_id) or 0
    if balance < price:
        raise InsufficientFunds(price - balance)
    post_entry(repositories.ledger, new_posting(line_id, -net, "purchase", reference))
    if vat > 0:
        post_entry(repositories.ledger, new_posting(line_id, -vat, "vat", reference))
    bucket = bucket_for(offer, 0, now)
    bucket_id = repositories.purchases.add_bucket(line_id, bucket)
    log_event(
        log,
        logging.INFO,
        "purchase.completed",
        line_id=line_id,
        kind=kind.value,
        offer_id=getattr(offer, "plan_id", None) or getattr(offer, "bundle_id", None),
        price_kobo=price,
        vat_kobo=vat,
        bucket_id=bucket_id,
    )
    return PurchaseResult(price, net, vat, balance - price, bucket_id, bucket.valid_to)


def _require_utc(now: datetime) -> None:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (UTC)")
