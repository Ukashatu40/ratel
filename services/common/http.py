"""Request-ID middleware and request logging shared by both FastAPI apps."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from common.logging import log_context_var, log_event, request_id_var

log = logging.getLogger("ratel.http")


def install_request_context(app: FastAPI) -> None:
    @app.middleware("http")
    async def _ctx(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        rid_token = request_id_var.set(rid)
        context_token = log_context_var.set({})
        start = time.perf_counter()
        try:
            response = await call_next(request)
            route = request.scope.get("route")
            # Log the route template, not the raw path: raw paths contain IMSIs.
            # Headers are never logged: Authorization carries the API key.
            template = getattr(route, "path", "unmatched")
            log_event(
                log,
                logging.INFO,
                "http.request",
                method=request.method,
                route=template,
                status=response.status_code,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
                request_id=rid,
            )
        finally:
            log_context_var.reset(context_token)
            request_id_var.reset(rid_token)
        response.headers["x-request-id"] = rid
        return response
