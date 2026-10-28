"""The payment routes RatelPay calls, and the gateway's webhook (M-19).

- `POST /v1/pay/payments`: start a payment for a phone number; answers where the customer pays.
- `GET /v1/pay/payments/{payment_id}`: its status. Holds nothing about the line or its owner
  (TOP-2), because anyone who has the id can read it.
- `POST /v1/pay/webhooks/paystack`: Paystack's notification. Its signature is checked on the raw
  bytes before anything is read, and what it says is only believed after the provider is asked.

Like the voucher route, these carry the key the reverse proxy adds (`require_pay_key`), and every
answer is `no-store`. Nothing here logs a body, a signature or a checkout address. The routes answer
503 until the deployment configures a gateway (docs/runbooks/bss-app.md, "Payments").
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from starlette.concurrency import run_in_threadpool

from app.bss_money.api.dependencies import require_pay_key
from app.bss_money.domain.payments import PaymentGateway
from app.bss_money.repositories.ports import PaymentScope
from app.bss_money.services.payments import (
    GatewayUnavailable,
    InvalidSignature,
    PaymentRefused,
    PaymentView,
    get_payment,
    handle_webhook,
    start_payment,
)
from common.errors import error_body

router = APIRouter(prefix="/v1/pay", dependencies=[Depends(require_pay_key)])

_NO_STORE = {"Cache-Control": "no-store"}


class StartPaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    msisdn: str = Field(pattern=r"^234[0-9]{10}$")
    amount_kobo: StrictInt = Field(ge=1)


def _json(status: int, content: dict[str, object]) -> JSONResponse:
    return JSONResponse(content=content, status_code=status, headers=_NO_STORE)


def _unavailable() -> JSONResponse:
    return _json(503, error_body("unavailable", "Payments are not available right now."))


def _body(view: PaymentView, *, with_checkout: bool) -> dict[str, object]:
    body: dict[str, object] = {
        "payment_id": view.public_id,
        "status": view.status.value,
        "amount_kobo": view.amount_kobo,
    }
    if with_checkout and view.checkout_url:
        body["checkout_url"] = view.checkout_url
    return body


def _setup(request: Request) -> tuple[PaymentScope, PaymentGateway | None]:
    return request.app.state.payment_scope, request.app.state.payment_gateway


@router.post("/payments")
def post_payment(
    payload: StartPaymentRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=120)],
) -> JSONResponse:
    scope, gateway = _setup(request)
    settings = request.app.state.settings
    if gateway is None or not settings.payments_enabled:
        return _unavailable()
    try:
        view = start_payment(
            scope,
            gateway,
            msisdn=payload.msisdn,
            amount_kobo=payload.amount_kobo,
            idempotency_key=idempotency_key,
            callback_url=settings.payment_callback_url,
            payer_email=settings.payment_payer_email,
            minimum=settings.payment_min_kobo,
            maximum=settings.payment_max_kobo,
        )
    except PaymentRefused:
        return _json(400, error_body("payment_refused", "This payment cannot be started."))
    except GatewayUnavailable:
        return _unavailable()
    return _json(200, _body(view, with_checkout=True))


@router.get("/payments/{payment_id}")
def get_payment_status(payment_id: str, request: Request) -> JSONResponse:
    scope, gateway = _setup(request)
    if not 16 <= len(payment_id) <= 64:  # not an id we could have made: do not even look
        return _json(404, error_body("not_found", "Unknown payment."))
    view = get_payment(scope, gateway, payment_id, datetime.now(UTC))
    if view is None:
        return _json(404, error_body("not_found", "Unknown payment."))
    return _json(200, _body(view, with_checkout=False))


@router.post("/webhooks/paystack")
async def post_paystack_webhook(
    request: Request,
    signature: Annotated[str, Header(alias="x-paystack-signature")] = "",
) -> JSONResponse:
    scope, gateway = _setup(request)
    if gateway is None or gateway.name != "paystack":
        return _unavailable()
    raw = await request.body()  # the signature is over exactly these bytes
    try:
        await run_in_threadpool(
            handle_webhook, scope, gateway, raw_body=raw, signature=signature, now=datetime.now(UTC)
        )
    except InvalidSignature:
        return _json(401, error_body("unauthorized", "Invalid signature."))
    except GatewayUnavailable:
        return _unavailable()  # a 5xx makes Paystack deliver it again later
    return _json(200, {"received": True})
