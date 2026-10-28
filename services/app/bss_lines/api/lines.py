"""FastAPI endpoints for the line lifecycle: activate, suspend, reinstate (contract) and terminate.

`/lines/{line_id}/activate|suspend|reinstate` are the contract's `bss_activate_line`,
`bss_suspend_line` and `bss_reinstate_line`. Terminate and the lookups are internal to RatelBSS and
not in contracts/openapi.yaml yet.

Every route needs a signed-in staff member whose role allows the action (`api/deps.py`), and the
audit `actor` is taken from that session, never from the request.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.bss_lines.api.deps import get_db, get_settings, require
from app.bss_lines.api.desk import LineOut, line_out
from app.bss_lines.domain.staff import Permission
from app.bss_lines.models.lines import Line
from app.bss_lines.repositories.desk_ports import StaffRecord
from app.bss_lines.repositories.desk_sql import SqlLineSalesRepository
from app.bss_lines.repositories.idempotency import (
    IdempotencyConflictError,
    IdempotencyStore,
)
from app.bss_lines.repositories.sql import SqlLinesRepository
from app.bss_lines.services import line_sales
from app.bss_lines.services.activation import ActivationError, activate_line
from app.bss_lines.services.activation import LineNotFoundError as ActivationLineNotFound
from app.bss_lines.services.lifecycle import (
    LifecycleError,
    LifecycleResult,
    LineNotFoundError,
    StoredDataError,
    reinstate_line,
    suspend_line,
    terminate_line,
)
from app.bss_lines.services.ratel_link_client import RatelLinkClient, RatelLinkError
from app.config import Settings
from common.errors import ApiError

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


Reason = Literal["fraud", "non_payment", "customer_request", "lost_sim", "other"]
IdempotencyKeyHeader = Annotated[
    str | None, Header(alias="Idempotency-Key", min_length=1, max_length=120)
]
LineId = Annotated[int, Path(ge=1)]
Db = Annotated[Session, Depends(get_db)]


class ActivateLineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speed_ul_mbps: float | None = Field(default=None, gt=0)
    speed_dl_mbps: float | None = Field(default=None, gt=0)


class CareActionRequest(BaseModel):
    """The body of suspend and reinstate: why, from the fixed list, plus free text."""

    model_config = ConfigDict(extra="forbid")

    reason: Reason
    reason_text: str | None = Field(default=None, max_length=200)


def _key(header: str | None) -> str:
    """The caller's Idempotency-Key, or a fresh one: without a key a repeat is a new operation."""
    return header if header is not None else uuid.uuid4().hex


def _not_found() -> ApiError:
    return ApiError(404, "not_found", "No such line.")


def _refused(exc: Exception) -> ApiError:
    return ApiError(409, "conflict", str(exc))


def _same_key_other_line() -> ApiError:
    return ApiError(409, "conflict", "This Idempotency-Key was used for another line.")


def _network_said_no() -> ApiError:
    # Nothing was changed. The caller repeats the call with the same Idempotency-Key.
    return ApiError(
        502, "bad_gateway", "The network service did not accept the change. Nothing was changed."
    )


def _the_line(session: Session, line_id: int) -> LineOut:
    line = line_sales.get_line(SqlLineSalesRepository(session), line_id)
    if line is None:
        raise _not_found()
    return line_out(line)


@router.post("/lines/{line_id}/activate", response_model=LineOut)
def activate(
    line_id: LineId,
    body: ActivateLineRequest,
    staff: Annotated[StaffRecord, Depends(require(Permission.ACTIVATE_LINE))],
    session: Db,
    lines: Annotated[SqlLinesRepository, Depends(get_lines_repo)],
    client: Annotated[RatelLinkClient, Depends(get_client)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency_store)],
    idempotency_key: IdempotencyKeyHeader = None,
) -> LineOut:
    """Activate a line (contract `bss_activate_line`).

    A repeat with the same Idempotency-Key for the same line returns the first result and changes
    nothing. The same key for another line is 409. The audit actor is the signed-in staff member.
    """
    if body.speed_ul_mbps is not None or body.speed_dl_mbps is not None:
        # TODO(contract): whether a caller may override the plan's speeds is not decided.
        raise ApiError(422, "validation_error", "Overriding the plan's speeds is not supported.")
    try:
        activate_line(
            lines,
            client,
            idempotency,
            line_id,
            actor=f"staff:{staff.staff_id}",
            idempotency_key=_key(idempotency_key),
        )
    except ActivationLineNotFound:
        raise _not_found() from None
    except ActivationError as exc:
        raise _refused(exc) from None
    except IdempotencyConflictError:
        raise _same_key_other_line() from None
    except RatelLinkError:
        raise _network_said_no() from None
    return _the_line(session, line_id)


@router.post("/lines/{line_id}/suspend", response_model=LineOut)
def suspend(
    line_id: LineId,
    body: CareActionRequest,
    staff: Annotated[StaffRecord, Depends(require(Permission.SUSPEND_LINE))],
    session: Db,
    lines: Annotated[SqlLinesRepository, Depends(get_lines_repo)],
    client: Annotated[RatelLinkClient, Depends(get_client)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency_store)],
    idempotency_key: IdempotencyKeyHeader = None,
) -> LineOut:
    """Suspend a line with a reason (contract `bss_suspend_line`)."""
    try:
        suspend_line(
            lines,
            client,
            idempotency,
            line_id,
            actor=f"staff:{staff.staff_id}",
            reason=body.reason,
            reason_text=body.reason_text,
            idempotency_key=_key(idempotency_key),
        )
    except LineNotFoundError:
        raise _not_found() from None
    except StoredDataError:
        raise ApiError(500, "internal_error", "The stored data for this line is wrong.") from None
    except LifecycleError as exc:
        raise _refused(exc) from None
    except IdempotencyConflictError:
        raise _same_key_other_line() from None
    except RatelLinkError:
        raise _network_said_no() from None
    return _the_line(session, line_id)


@router.post("/lines/{line_id}/reinstate", response_model=LineOut)
def reinstate(
    line_id: LineId,
    body: CareActionRequest,
    staff: Annotated[StaffRecord, Depends(require(Permission.SUSPEND_LINE))],
    session: Db,
    lines: Annotated[SqlLinesRepository, Depends(get_lines_repo)],
    client: Annotated[RatelLinkClient, Depends(get_client)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency_store)],
    idempotency_key: IdempotencyKeyHeader = None,
) -> LineOut:
    """Reinstate a suspended line (contract `bss_reinstate_line`).

    If the stored `state_before_suspension` is wrong the answer is 500 and the caller does not
    retry: repeating the call cannot fix the data.
    """
    try:
        reinstate_line(
            lines,
            client,
            idempotency,
            line_id,
            actor=f"staff:{staff.staff_id}",
            reason=body.reason,
            reason_text=body.reason_text,
            idempotency_key=_key(idempotency_key),
        )
    except LineNotFoundError:
        raise _not_found() from None
    except StoredDataError:
        raise ApiError(500, "internal_error", "The stored data for this line is wrong.") from None
    except LifecycleError as exc:
        raise _refused(exc) from None
    except IdempotencyConflictError:
        raise _same_key_other_line() from None
    except RatelLinkError:
        raise _network_said_no() from None
    return _the_line(session, line_id)


# Terminate is not in the contract yet, so it keeps its internal body-based route.
class LifecycleBody(BaseModel):
    """Request payload for terminate."""

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
