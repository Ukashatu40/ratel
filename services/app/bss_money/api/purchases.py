"""Buying a plan or a bundle for a line from its wallet, by a signed-in staff member (M-26).

`POST /v1/lines/{line_id}/purchases` (contract `bss_buy_offer`). The wallet is debited, VAT is its
own ledger entry, and the line gets an allowance bucket; a line that was out of data or expired
comes back by itself on the rating job's next run. RatelPay cannot call this: it is a staff
session route, and letting an anonymous caller spend a customer's wallet is a decision for the PRD.

The Idempotency-Key is required and becomes the ledger reference, so a repeat returns the first
purchase and changes nothing; the same key for a different price is refused.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from app.bss_lines.api.deps import now_utc, require
from app.bss_lines.domain.staff import Permission
from app.bss_lines.repositories.desk_ports import StaffRecord
from app.bss_money.domain.purchase import OfferKind
from app.bss_money.repositories.ports import PurchaseScope
from app.bss_money.services import purchase
from app.config import Settings
from common.errors import ApiError
from common.timeutil import to_epoch

router = APIRouter(prefix="/v1")

Seller = Annotated[StaffRecord, Depends(require(Permission.SELL_OFFER))]
RequiredKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]


class PurchaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_kind: OfferKind
    offer_id: int = Field(ge=1)


class PurchaseOut(BaseModel):
    price_kobo: int
    net_kobo: int
    vat_kobo: int
    balance_kobo: int
    valid_to: int | None
    replayed: bool


@router.post("/lines/{line_id}/purchases", response_model=PurchaseOut)
def buy(
    request: Request,
    line_id: Annotated[int, Path(ge=1)],
    body: PurchaseRequest,
    _staff: Seller,
    idempotency_key: RequiredKey,
) -> PurchaseOut:
    """Buy the plan or bundle from the line's wallet."""
    scope: PurchaseScope = request.app.state.purchase_scope
    settings: Settings = request.app.state.settings
    try:
        result = purchase.buy_offer(
            scope,
            line_id=line_id,
            kind=body.offer_kind,
            offer_id=body.offer_id,
            reference=f"desk:{idempotency_key}",
            now=now_utc(request),
            vat_rate_bps=settings.vat_rate_bps,
        )
    except purchase.LineNotFound:
        raise ApiError(404, "not_found", "No such line.") from None
    except purchase.LineCannotBuy:
        raise ApiError(409, "conflict", "This line cannot buy in its current state.") from None
    except purchase.OfferNotAvailable:
        raise ApiError(409, "conflict", "That plan or bundle is not on sale.") from None
    except purchase.ReferenceReused:
        raise ApiError(
            409, "conflict", "This Idempotency-Key was used for a different purchase."
        ) from None
    except purchase.InsufficientFunds as exc:
        raise ApiError(
            409,
            "insufficient_funds",
            f"The wallet is {exc.shortfall_kobo} kobo short of the price.",
        ) from None
    return PurchaseOut(
        price_kobo=result.price_kobo,
        net_kobo=result.net_kobo,
        vat_kobo=result.vat_kobo,
        balance_kobo=result.balance_kobo,
        valid_to=None if result.valid_to is None else to_epoch(result.valid_to),
        replayed=result.replayed,
    )
