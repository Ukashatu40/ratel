"""FastAPI endpoints for the sell-to-activate flow.

These endpoints are internal to RatelBSS and are not in contracts/openapi.yaml; the contract's
versions (bss_activate_line, bss_suspend_line, bss_reinstate_line) replace them.

Every route needs a signed-in staff member whose role allows the action (`api/deps.py`), and the
audit `actor` is taken from that session, never from the request.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.bss_lines.api.deps import get_db, get_settings, require
from app.bss_lines.domain.staff import Permission
from app.bss_lines.models.lines import Line
from app.bss_lines.repositories.desk_ports import StaffRecord
from app.bss_lines.repositories.idempotency import (
    IdempotencyConflictError,
    IdempotencyStore,
)
from app.bss_lines.repositories.sql import SqlLinesRepository
from app.bss_lines.services.activation import ActivationError, activate_line
from app.bss_lines.services.lifecycle import (
    LifecycleError,
    LifecycleResult,
    reinstate_line,
    suspend_line,
    terminate_line,
)
from app.bss_lines.services.ratel_link_client import RatelLinkClient, RatelLinkError
from app.config import Settings

__all__ = ["get_client", "get_db", "get_lines_repo", "get_settings", "router"]

router = APIRouter(prefix="/v1")


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
    return SqlLinesRepository(session, request_commits=True)


def get_idempotency_store(request: Request) -> IdempotencyStore:
    """The Idempotency-Key store, set on app.state by create_app."""
    store = getattr(request.app.state, "idempotency_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Idempotency store not configured")
    return store  # type: ignore[no-any-return]


class ActivateBody(BaseModel):
    """Request payload for activating a line."""

    line_id: int
    idempotency_key: str = Field(min_length=1, max_length=120)


class ActivateResponse(BaseModel):
    """Response returned after a successful activation."""

    line_id: int
    state: str


@router.post("/lines/activate", response_model=ActivateResponse)
def post_activate(
    payload: ActivateBody,
    staff: Annotated[StaffRecord, Depends(require(Permission.ACTIVATE_LINE))],
    lines: Annotated[SqlLinesRepository, Depends(get_lines_repo)],
    client: Annotated[RatelLinkClient, Depends(get_client)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency_store)],
) -> ActivateResponse:
    """Activate a line through the RatelLink client.

    A repeat with the same Idempotency-Key for the same line returns the first
    result and changes nothing (M-26). A repeat for a different line is 409.

    The audit actor is the signed-in staff member.

    TODO(contract, M-02): this route and body will be replaced by whatever M-02
    specifies in contracts/openapi.yaml.
    """
    try:
        result = activate_line(
            lines,
            client,
            idempotency,
            payload.line_id,
            actor=f"staff:{staff.staff_id}",
            idempotency_key=payload.idempotency_key,
        )
    except ActivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RatelLinkError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"RatelLink error: {exc}",
        ) from exc

    return ActivateResponse(
        line_id=result.line_id,
        state=result.to_state.value,
    )


class LifecycleBody(BaseModel):
    """Request payload for suspend, reinstate and terminate."""

    line_id: int
    idempotency_key: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=40)
    reason_text: str | None = Field(default=None, max_length=200)


class LifecycleResponse(BaseModel):
    """Response returned after a lifecycle change."""

    line_id: int
    from_state: str
    to_state: str


def _lifecycle_response(result: LifecycleResult) -> LifecycleResponse:
    return LifecycleResponse(
        line_id=result.line_id,
        from_state=result.from_state.value,
        to_state=result.to_state.value,
    )


@router.post("/lines/suspend", response_model=LifecycleResponse)
def post_suspend(
    payload: LifecycleBody,
    staff: Annotated[StaffRecord, Depends(require(Permission.SUSPEND_LINE))],
    lines: Annotated[SqlLinesRepository, Depends(get_lines_repo)],
    client: Annotated[RatelLinkClient, Depends(get_client)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency_store)],
) -> LifecycleResponse:
    """Suspend a line with a reason.

    A repeat with the same Idempotency-Key for the same line returns the first
    result. A repeat for a different line is 409.
    """
    try:
        result = suspend_line(
            lines,
            client,
            idempotency,
            payload.line_id,
            actor=f"staff:{staff.staff_id}",
            reason=payload.reason,
            reason_text=payload.reason_text,
            idempotency_key=payload.idempotency_key,
        )
    except LifecycleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RatelLinkError as exc:
        raise HTTPException(status_code=502, detail=f"RatelLink error: {exc}") from exc

    return _lifecycle_response(result)


@router.post("/lines/reinstate", response_model=LifecycleResponse)
def post_reinstate(
    payload: LifecycleBody,
    staff: Annotated[StaffRecord, Depends(require(Permission.SUSPEND_LINE))],
    lines: Annotated[SqlLinesRepository, Depends(get_lines_repo)],
    client: Annotated[RatelLinkClient, Depends(get_client)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency_store)],
) -> LifecycleResponse:
    """Reinstate a suspended line.

    A repeat with the same Idempotency-Key for the same line returns the first
    result. A repeat for a different line is 409.
    """
    try:
        result = reinstate_line(
            lines,
            client,
            idempotency,
            payload.line_id,
            actor=f"staff:{staff.staff_id}",
            reason=payload.reason,
            reason_text=payload.reason_text,
            idempotency_key=payload.idempotency_key,
        )
    except LifecycleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RatelLinkError as exc:
        raise HTTPException(status_code=502, detail=f"RatelLink error: {exc}") from exc

    return _lifecycle_response(result)


@router.post("/lines/terminate", response_model=LifecycleResponse)
def post_terminate(
    payload: LifecycleBody,
    staff: Annotated[StaffRecord, Depends(require(Permission.TERMINATE_LINE))],
    lines: Annotated[SqlLinesRepository, Depends(get_lines_repo)],
    client: Annotated[RatelLinkClient, Depends(get_client)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency_store)],
) -> LifecycleResponse:
    """Terminate a line.

    A repeat with the same Idempotency-Key for the same line returns the first
    result. A repeat for a different line is 409.
    """
    try:
        result = terminate_line(
            lines,
            client,
            idempotency,
            payload.line_id,
            actor=f"staff:{staff.staff_id}",
            reason=payload.reason,
            reason_text=payload.reason_text,
            idempotency_key=payload.idempotency_key,
        )
    except LifecycleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RatelLinkError as exc:
        raise HTTPException(status_code=502, detail=f"RatelLink error: {exc}") from exc

    return _lifecycle_response(result)


# --- M-26 line lookup ------------------------------------------------------------


class LineLookupResponse(BaseModel):
    """One line's identifying and state fields. No keys, no usage."""

    line_id: int
    imsi: str
    iccid: str
    msisdn: str
    plan_id: int
    state: str
    state_before_suspension: str | None
    expires_at: str | None


def _line_lookup_response(line: Line) -> LineLookupResponse:
    return LineLookupResponse(
        line_id=line.line_id,
        imsi=line.imsi,
        iccid=line.iccid,
        msisdn=line.msisdn,
        plan_id=line.plan_id,
        state=line.state,
        state_before_suspension=line.state_before_suspension,
        expires_at=line.expires_at.isoformat() if line.expires_at is not None else None,
    )


@router.get("/lines/lookup", response_model=LineLookupResponse)
def get_line_by_identifier(
    _staff: Annotated[StaffRecord, Depends(require(Permission.READ))],
    lines: Annotated[SqlLinesRepository, Depends(get_lines_repo)],
    msisdn: str | None = None,
    iccid: str | None = None,
    imsi: str | None = None,
) -> LineLookupResponse:
    """Look a line up by exactly one of msisdn, iccid or imsi.

    Answers 422 if zero or more than one identifier is given, 404 if no line
    matches. The indexes on line.msisdn, line.iccid and line.imsi make each
    lookup one indexed read, so the under-a-second criterion holds with
    100,000 rows in the table.
    """
    supplied = sum(x is not None for x in (msisdn, iccid, imsi))
    if supplied != 1:
        raise HTTPException(
            status_code=422,
            detail="exactly one of msisdn, iccid, imsi must be given",
        )
    line = lines.find_by_identifier(msisdn=msisdn, iccid=iccid, imsi=imsi)
    if line is None:
        raise HTTPException(status_code=404, detail="No line with that identifier")
    return _line_lookup_response(line)


@router.get("/lines/lookup/{line_id}", response_model=LineLookupResponse)
def get_line_by_id(
    line_id: int,
    _staff: Annotated[StaffRecord, Depends(require(Permission.READ))],
    lines: Annotated[SqlLinesRepository, Depends(get_lines_repo)],
) -> LineLookupResponse:
    """Look a line up by its id."""
    line = lines.find_by_identifier(line_id=line_id)
    if line is None:
        raise HTTPException(status_code=404, detail=f"No line with id {line_id}")
    return _line_lookup_response(line)
