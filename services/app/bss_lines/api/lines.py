"""FastAPI endpoints for the sell-to-activate flow.

These endpoints are internal to RatelBSS. They are NOT part of
contracts/openapi.yaml, which describes RatelLink and RatelMeter only.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.bss_lines.repositories.sql import SqlLinesRepository
from app.bss_lines.services.activation import ActivationError, activate_line
from app.bss_lines.services.ratel_link_client import RatelLinkClient, RatelLinkError
from app.config import Settings

router = APIRouter(prefix="/v1")


def get_db(request: Request) -> Iterator[Session]:
    """Provide a database session for the duration of the request."""
    factory = request.app.state.session_factory

    with factory() as session, session.begin():
        yield session


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Application settings, read once per process."""
    return Settings()


def get_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RatelLinkClient:
    """Create the RatelLink API client using application settings."""
    key = settings.ratel_link_api_key

    if key is None:
        raise HTTPException(
            status_code=503,
            detail="RatelLink API key is not configured",
        )

    return RatelLinkClient(
        settings.ratel_link_base_url,
        key.get_secret_value(),
    )


def get_lines_repo(
    session: Annotated[Session, Depends(get_db)],
) -> SqlLinesRepository:
    """Wrap the session in the repository the service expects."""
    return SqlLinesRepository(session)


class ActivateBody(BaseModel):
    """Request payload for activating a line."""

    line_id: int
    actor: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=120)


class ActivateResponse(BaseModel):
    """Response returned after a successful activation."""

    line_id: int
    state: str


@router.post("/lines/activate", response_model=ActivateResponse)
def post_activate(
    payload: ActivateBody,
    lines: Annotated[SqlLinesRepository, Depends(get_lines_repo)],
    client: Annotated[RatelLinkClient, Depends(get_client)],
) -> ActivateResponse:
    """Activate a line through the RatelLink client.

    TODO(auth, M-26): this route has no authentication and takes the audit
    ``actor`` from the request body. That must not be deployed before M-26 adds
    staff authentication. Anyone who can reach this route can claim to be any
    actor, and the audit log would record it.

    TODO(contract, M-02): this route and body will be replaced by whatever M-02
    specifies in contracts/openapi.yaml.
    """
    try:
        result = activate_line(
            lines,
            client,
            payload.line_id,
            actor=payload.actor,
            idempotency_key=payload.idempotency_key,
        )
    except ActivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RatelLinkError as exc:
        # RatelLink is downstream of us: a failure there is a gateway problem,
        # not a bug in the request.
        raise HTTPException(
            status_code=502,
            detail=f"RatelLink error: {exc}",
        ) from exc

    return ActivateResponse(
        line_id=result.line_id,
        state=result.to_state.value,
    )
