"""The public voucher redemption route, called by the RatelPay page (M-18).

`POST /v1/pay/vouchers/redeem` carries no API key: the page is a static file in a browser and
could not keep one secret. What protects it instead is the limit of five failed attempts per card
number per hour (services/vouchers.py), a per-address rate limit at the reverse proxy
(deploy/bss-app/nginx), and answers that tell a guesser nothing: every failure except a typo and
the limit is the same 400.

A refusal is **returned**, never raised. The transaction is committed when the service returns,
and raising here would not undo that, but the habit matters: a failed attempt has to stay on record.
Nothing in this module logs the request body.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.bss_money.domain.vouchers import is_pin
from app.bss_money.repositories.ports import RedemptionScope
from app.bss_money.services.vouchers import RedeemStatus, redeem_for_number
from common.errors import error_body

router = APIRouter(prefix="/v1/pay")

_NO_STORE = {"Cache-Control": "no-store"}  # a redeem answer is never kept by a cache
_RETRY_AFTER_SECONDS = "3600"  # the window the limit is counted over


class RedeemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    msisdn: str = Field(pattern=r"^[0-9]{10,15}$")
    card_number: str = Field(pattern=r"^[0-9]{20}$")
    pin: str = Field(pattern=r"^[0-9]{14}$", repr=False)


class RedeemResponse(BaseModel):
    amount_kobo: int
    balance_kobo: int


def _json(
    status: int, content: dict[str, object], headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        content=content, status_code=status, headers={**_NO_STORE, **(headers or {})}
    )


@router.post("/vouchers/redeem", response_model=RedeemResponse)
def post_redeem(payload: RedeemRequest, request: Request) -> JSONResponse:
    scope: RedemptionScope = request.app.state.redemption_scope
    if not is_pin(payload.pin):  # the check digit: a typo, told apart and not counted
        return _json(422, error_body("validation_error", "Invalid request. Fields: body.pin"))
    result = redeem_for_number(
        scope,
        msisdn=payload.msisdn,
        card_number=payload.card_number,
        pin=payload.pin,
        now=datetime.now(UTC),
    )
    if result.status is RedeemStatus.REDEEMED:
        body = RedeemResponse(amount_kobo=result.amount_kobo, balance_kobo=result.balance_kobo)
        return _json(200, body.model_dump())
    if result.status is RedeemStatus.TOO_MANY_ATTEMPTS:
        return _json(
            429,
            error_body("rate_limited", "Too many attempts. Try again later."),
            {"Retry-After": _RETRY_AFTER_SECONDS},
        )
    if result.status is RedeemStatus.MALFORMED:
        return _json(422, error_body("validation_error", "Invalid request."))
    return _json(400, error_body("voucher_refused", "This card cannot be used."))
