"""Request-ID middleware and request logging shared by both FastAPI apps."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from common.logging import log_event, request_id_var

log = logging.getLogger("ratel.http")


def install_request_context(app: FastAPI) -> None:
    @app.middleware("http")
    async def _ctx(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        route = request.scope.get("route")
        # Log the route template, not the raw path: raw paths contain IMSIs.
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
        response.headers["x-request-id"] = rid
        return response
