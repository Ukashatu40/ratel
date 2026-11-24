"""The list of bundles RatelPay shows (`GET /v1/pay/bundles`, contract `bss_list_bundles`).

Like the other RatelPay routes it carries the key the reverse proxy adds (`require_pay_key`). It
holds prices and sizes only: no line, customer or channel list. Buying a bundle is not built here.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.bss_money.api.dependencies import require_pay_key
from app.bss_money.domain.plans import Bundle
from app.bss_money.repositories.ports import CatalogScope
from app.bss_money.services.catalog import bundles_on_sale

router = APIRouter(prefix="/v1/pay", dependencies=[Depends(require_pay_key)])


class BundleOut(BaseModel):
    bundle_id: int
    name: str
    price_kobo: int
    data_bytes: int
    validity_days: int


class BundleList(BaseModel):
    bundles: list[BundleOut]


def _out(bundle: Bundle) -> BundleOut:
    return BundleOut(
        bundle_id=bundle.bundle_id,
        name=bundle.name,
        price_kobo=bundle.price_kobo,
        data_bytes=bundle.data_bytes,
        validity_days=bundle.validity_days,
    )


@router.get("/bundles", response_model=BundleList)
def get_bundles(
    request: Request,
    channel: Annotated[Literal["desk", "pay", "sms", "ussd"] | None, Query()] = None,
) -> JSONResponse:
    """Bundles on sale; with `channel`, only those sold on that channel (docs/catalogue.md)."""
    scope: CatalogScope = request.app.state.catalog_scope
    on_sale = bundles_on_sale(scope)
    if channel is not None:
        on_sale = [b for b in on_sale if channel in b.channels]
    body = BundleList(bundles=[_out(b) for b in on_sale])
    return JSONResponse(body.model_dump(), headers={"Cache-Control": "no-store"})
