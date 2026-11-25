"""Self-care by phone number, for the SMS short number 647 and USSD (docs/catalogue.md).

Like the other RatelPay routes these carry the key the reverse proxy adds (`require_pay_key`), and
the proxy lets only the voice VM reach them (deploy/bss-app/nginx). They are not public: a caller
who could reach them could read any line's balance.

The customer SMS queue (docs/customer-sms.md) is here for the same reason: the voice VM sends them.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.bss_lines.api.deps import now_utc
from app.bss_money.api.dependencies import require_pay_key
from app.bss_money.domain.purchase import OfferKind
from app.bss_money.repositories.ports import CatalogScope, CatalogueScope, PurchaseScope
from app.bss_money.services import catalogue, pay_lines, purchase
from app.bss_money.services.catalog import bundles_on_sale
from app.bss_money.services.pay_lines import PayLineScope
from app.config import Settings
from common.errors import ApiError
from common.timeutil import to_epoch

router = APIRouter(prefix="/v1/pay", dependencies=[Depends(require_pay_key)])

Msisdn = Annotated[str, Path(pattern=r"^234[0-9]{10}$")]
RequiredKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]
OptionalKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=100)]


class AirtimeOut(BaseModel):
    presets_kobo: list[int]
    card_min_kobo: int
    card_max_kobo: int


class BalanceOut(BaseModel):
    balance_kobo: int
    data_bytes_left: int
    data_valid_to: int | None


class BuyBundleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: int = Field(ge=1)
    channel: Literal["sms", "ussd"]


class BoughtOut(BaseModel):
    name: str
    price_kobo: int
    balance_kobo: int
    valid_to: int | None
    replayed: bool


class CustomerSmsOut(BaseModel):
    sms_id: int
    line_id: int
    msisdn: str
    kind: str
    text: str


class CustomerSmsListOut(BaseModel):
    items: list[CustomerSmsOut]


class CustomerSmsSentOut(BaseModel):
    sms_id: int
    sent_at: int


def _unknown() -> ApiError:
    return ApiError(404, "not_found", "No live line has this number.")


@router.get("/airtime", response_model=AirtimeOut)
def get_airtime(request: Request) -> AirtimeOut:
    """The airtime amounts the menus offer and the card payment limits."""
    settings: Settings = request.app.state.settings
    scope: CatalogueScope = request.app.state.catalogue_scope
    low, high = catalogue.card_limits(
        scope, floor_kobo=settings.payment_min_kobo, ceiling_kobo=settings.payment_max_kobo
    )
    with scope() as repository:
        presets = catalogue.settings_or_default(repository).airtime_presets_kobo
    return AirtimeOut(
        presets_kobo=[p for p in presets if low <= p <= high], card_min_kobo=low, card_max_kobo=high
    )


@router.get("/lines/{msisdn}/balance", response_model=BalanceOut)
def get_balance(request: Request, msisdn: Msisdn) -> BalanceOut:
    """The line's airtime and the data it has left now."""
    scope: PayLineScope = request.app.state.pay_line_scope
    try:
        result = pay_lines.balance(scope, msisdn, now_utc(request))
    except pay_lines.UnknownNumber:
        raise _unknown() from None
    return BalanceOut(
        balance_kobo=result.balance_kobo,
        data_bytes_left=result.data_bytes_left,
        data_valid_to=None if result.data_valid_to is None else to_epoch(result.data_valid_to),
    )


@router.post("/lines/{msisdn}/purchases", response_model=BoughtOut)
def buy_bundle(request: Request, msisdn: Msisdn, body: BuyBundleIn, key: RequiredKey) -> BoughtOut:
    """Buy a bundle from the line's airtime. The bundle must be on sale on this channel."""
    catalog: CatalogScope = request.app.state.catalog_scope
    offer = next((b for b in bundles_on_sale(catalog) if b.bundle_id == body.bundle_id), None)
    if offer is None or body.channel not in offer.channels:
        raise ApiError(409, "conflict", "That bundle is not on sale here.")
    settings: Settings = request.app.state.settings
    try:
        line_id = pay_lines.line_id(request.app.state.pay_line_scope, msisdn)
        purchase_scope: PurchaseScope = request.app.state.purchase_scope
        result = purchase.buy_offer(
            purchase_scope,
            line_id=line_id,
            kind=OfferKind.BUNDLE,
            offer_id=offer.bundle_id,
            reference=f"{body.channel}:{key}",
            now=now_utc(request),
            vat_rate_bps=settings.vat_rate_bps,
        )
    except (pay_lines.UnknownNumber, purchase.LineNotFound):
        raise _unknown() from None
    except purchase.LineCannotBuy:
        raise ApiError(409, "conflict", "This line cannot buy in its current state.") from None
    except purchase.OfferNotAvailable:
        raise ApiError(409, "conflict", "That bundle is not on sale here.") from None
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
    return BoughtOut(
        name=offer.name,
        price_kobo=result.price_kobo,
        balance_kobo=result.balance_kobo,
        valid_to=None if result.valid_to is None else to_epoch(result.valid_to),
        replayed=result.replayed,
    )


@router.get("/customer-sms", response_model=CustomerSmsListOut)
def list_customer_sms(
    request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> CustomerSmsListOut:
    """SMS to customers not sent yet (welcome, call summaries), oldest first, with their text."""
    due = pay_lines.sms_due(request.app.state.pay_line_scope, limit)
    return CustomerSmsListOut(
        items=[
            CustomerSmsOut(
                sms_id=s.sms_id, line_id=s.line_id, msisdn=s.msisdn, kind=s.kind, text=s.text
            )
            for s in due
        ]
    )


@router.post("/customer-sms/{sms_id}/sent", response_model=CustomerSmsSentOut)
def mark_customer_sms_sent(
    request: Request,
    sms_id: Annotated[int, Path(ge=1, le=2_147_483_647)],
    key: OptionalKey = None,
) -> CustomerSmsSentOut:
    """Record that the SMS went to the SMS centre. A repeat changes nothing."""
    del key  # marking sent is idempotent by itself; the key is accepted like every state change
    try:
        sent_at = pay_lines.mark_sms_sent(
            request.app.state.pay_line_scope, sms_id, now_utc(request)
        )
    except pay_lines.NoSuchSms:
        raise ApiError(404, "not_found", "There is no such SMS.") from None
    return CustomerSmsSentOut(sms_id=sms_id, sent_at=to_epoch(sent_at))
