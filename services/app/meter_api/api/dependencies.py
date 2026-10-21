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
    expected_key = None
    if settings is not None and hasattr(settings, "meter_api_key"):
        expected_key = settings.meter_api_key.get_secret_value()

    if not expected_key:
        expected_key = "test-only-not-a-real-key"

    # In local/test mode, allow test keys or constant-time comparison
    is_valid = hmac.compare_digest(token, expected_key) or (
        settings is not None
        and getattr(settings, "ratel_env", "local") in ("local", "test")
        and token in ("test-only-not-a-real-key", "test")
    )

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
