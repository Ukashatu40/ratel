"""The key check for the voucher redemption route."""

from __future__ import annotations

import hmac
import logging
from typing import Annotated

from fastapi import Header, Request

from common.errors import ApiError

log = logging.getLogger("ratel.bss.money.auth")


def _unauthorized() -> ApiError:
    return ApiError(
        401, "unauthorized", "Invalid or missing API key.", headers={"WWW-Authenticate": "Bearer"}
    )


def require_pay_key(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    """Accept only the redemption key (`PAY_API_KEY`), as `Authorization: Bearer <key>`.

    RatelPay's page sends no key: the reverse proxy adds it to this one route and replaces anything
    the browser sent. So this check does not stop a person who calls the proxy; it keeps the app's
    rule that every call is authenticated, and stops anything that reaches the app by another road.
    The protection against guessing is the limit of five failures per card number per hour.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise _unauthorized()
    token = authorization.removeprefix("Bearer ").strip()
    expected = getattr(getattr(request.app.state, "settings", None), "pay_api_key_value", None)
    if expected is None:
        # No key is configured, so no caller can be right. Never fall back to a built-in key.
        log.error("pay.key_not_configured")
        raise _unauthorized()
    if not token or not hmac.compare_digest(token.encode(), expected.encode()):
        raise _unauthorized()
