"""FastAPI dependencies for authentication: `require_api_key` and the auth-first route class.

Authentication logic itself is in services/authentication.py. This file only adapts it to HTTP.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from common.errors import ApiError
from common.logging import bind_log_context, log_event
from ratel_link.services.authentication import ApiPrincipal, Rejected, authenticate

log = logging.getLogger("ratel.link.auth")


_PRINCIPAL_SCOPE_KEY = "ratel_link.principal"


def _unauthorized() -> ApiError:
    # One response for every failure, so a caller learns nothing about why.
    return ApiError(
        401, "unauthorized", "Invalid or missing API key.", headers={"WWW-Authenticate": "Bearer"}
    )


async def require_api_key(request: Request) -> ApiPrincipal:
    """Reject the request with 401 unless it carries a valid `Authorization: Bearer <key>`.

    Put on the /v1 router (main.new_v1_router), so every route added there is protected by
    default. Reads the repository and clock from `app.state`. The lookup is blocking, so it runs
    in a thread. The result is kept in the request's ASGI scope, so asking twice costs one lookup.
    The scope belongs to this one request by definition, unlike `request.state`, which a server
    could in principle share.
    """
    cached = request.scope.get(_PRINCIPAL_SCOPE_KEY)
    if isinstance(cached, ApiPrincipal):
        return cached
    state = request.app.state
    result = await run_in_threadpool(
        authenticate, request.headers.get("authorization"), state.api_keys, state.clock()
    )
    if isinstance(result, Rejected):
        fields: dict[str, str] = {"reason": result.reason.value}
        if result.api_key_id is not None:
            fields["api_key_id"] = result.api_key_id
        log_event(log, logging.WARNING, "auth.rejected", **fields)
        raise _unauthorized()
    request.scope[_PRINCIPAL_SCOPE_KEY] = result
    bind_log_context(api_key_id=result.api_key_id, api_key_generation=result.generation)
    return result


class AuthFirstRoute(APIRoute):
    """Authenticate before FastAPI reads or validates the request body.

    A router-level dependency alone runs after the body has been parsed, so an unauthenticated
    request with malformed JSON would get 422 instead of 401, and the server would read a body it
    should have refused. This runs the same check first. The dependency stays as well.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def authenticate_first(request: Request) -> Response:
            await require_api_key(request)
            return await handler(request)

        return authenticate_first
