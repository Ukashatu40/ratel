"""The error shape from the Build Plan: {"error": {"code": "...", "message": "..."}}."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("ratel.errors")

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


class ApiError(Exception):
    """Raise this for expected, client-visible failures.

    `headers` are added to the response, for example `WWW-Authenticate` on a 401.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = dict(headers) if headers else None


def error_body(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _json(
    status_code: int, code: str, message: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content=error_body(code, message), headers=dict(headers or {})
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _json(exc.status_code, exc.code, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo the rejected input: it may contain Ki, OPc, PINs or personal data.
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        return _json(422, "validation_error", "Invalid request. Fields: " + ", ".join(fields))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "http_error")
        return _json(exc.status_code, code, str(exc.detail), exc.headers)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Log the exception type only. Messages and tracebacks can carry sensitive values.
        log.error(
            "unhandled_error",
            extra={"event": "http.unhandled_error", "exc_type": type(exc).__name__},
        )
        return _json(500, "internal_error", "Internal error")
