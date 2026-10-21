"""FastAPI dependencies for the meter_api module."""

from __future__ import annotations

import hmac
import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from common.errors import ApiError

from ..repositories.ports import UsageRepository
from ..repositories.sql import SqlUsageRepository

log = logging.getLogger("ratel.meter.auth")


def require_api_key(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> str:
    """Validate Bearer API key according to contracts/openapi.yaml."""
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(
            401,
            "unauthorized",
            "Invalid or missing API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise ApiError(
            401,
            "unauthorized",
            "Invalid or missing API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = getattr(request.app.state, "settings", None)
    expected_key = getattr(settings, "meter_api_key_value", None)
    if expected_key is None:
        # No key is configured, so no caller can be right. Never fall back to a built-in key.
        log.error("meter_api.key_not_configured")
        raise ApiError(
            401,
            "unauthorized",
            "Invalid or missing API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Constant-time comparison. The only accepted token is the configured key.
    is_valid = hmac.compare_digest(token.encode(), expected_key.encode())

    if not is_valid:
        raise ApiError(
            401,
            "unauthorized",
            "Invalid or missing API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token


def get_db_session(request: Request) -> Iterator[Session]:
    """Yield a database session from app.state.session_factory."""
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise RuntimeError("Database session factory is not configured on app.state")
    with factory() as session, session.begin():
        yield session


def get_usage_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> UsageRepository:
    """Provide a UsageRepository instance bound to the active session."""
    return SqlUsageRepository(session)
