"""FastAPI endpoints for the sell-to-activate flow.

These endpoints are internal to RatelBSS. They are NOT part of
contracts/openapi.yaml, which describes RatelLink and RatelMeter only.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.bss_lines.client import RatelLinkClient
from app.bss_lines.services import ActivationError, activate_line
from app.config import Settings

router = APIRouter(prefix="/v1")


def get_db(request: Request) -> Iterator[Session]:
    """Provide a database session for the duration of the request."""
    factory = request.app.state.session_factory

    with factory() as session, session.begin():
        yield session


def get_settings() -> Settings:
    """Return application settings."""
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


class ActivateBody(BaseModel):
    """Request payload for activating a line."""

    line_id: int
    actor: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=120)


class ActivateResponse(BaseModel):
    """Response returned after a successful activation."""

    line_id: int
    state: str


@router.post(
    "/lines/activate",
    response_model=ActivateResponse,
)
def post_activate(
    payload: ActivateBody,
    session: Annotated[Session, Depends(get_db)],
    client: Annotated[RatelLinkClient, Depends(get_client)],
) -> ActivateResponse:
    """Activate a line through the RatelLink client."""
    try:
        result = activate_line(
            session,
            client,
            payload.line_id,
            actor=payload.actor,
            idempotency_key=payload.idempotency_key,
        )
    except ActivationError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return ActivateResponse(
        line_id=result.line_id,
        state=result.to_state.value,
    )
