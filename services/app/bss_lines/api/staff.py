"""Sign in, sign out and "who am I" for RatelDesk staff.

`POST /v1/auth/login` takes an email and a password and, if they are right, sets the session cookie.
Every refusal (unknown email, wrong password, disabled or locked account) is the same 401, so the
answer tells a guesser nothing. The cookie is `HttpOnly` (script cannot read it), `Secure` (HTTPS
only) and `SameSite=Strict` (never sent from another site).

A refusal is **returned**, never raised: the failed-attempt count has to be saved, and an
exception would roll it back.

Nothing here logs an email, a password or a token.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.bss_lines.api.deps import CurrentStaff, get_db, get_settings, now_utc
from app.bss_lines.domain.staff import COOKIE_NAME
from app.bss_lines.repositories.desk_ports import StaffRecord
from app.bss_lines.repositories.desk_sql import SqlStaffRepository
from app.bss_lines.services.staff_auth import sign_in, sign_out
from app.config import Settings
from common.errors import error_body

router = APIRouter(prefix="/v1/auth")


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=1024, repr=False)


class StaffMe(BaseModel):
    staff_id: int
    email: str
    name: str
    role: str


def _me(staff: StaffRecord) -> StaffMe:
    return StaffMe(staff_id=staff.staff_id, email=staff.email, name=staff.name, role=staff.role)


@router.post("/login", response_model=StaffMe)
def login(
    body: LoginRequest,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Sign in. Sets the session cookie; the answer is who signed in."""
    signed_in = sign_in(SqlStaffRepository(session), body.email, body.password, now_utc(request))
    if signed_in is None:
        return JSONResponse(
            status_code=401,
            content=error_body("unauthorized", "Email or password is not right."),
            headers={"Cache-Control": "no-store"},
        )
    response = JSONResponse(
        content=_me(signed_in.staff).model_dump(), headers={"Cache-Control": "no-store"}
    )
    response.set_cookie(
        COOKIE_NAME,
        signed_in.token,
        max_age=signed_in.max_age_seconds,
        httponly=True,
        secure=settings.staff_cookie_secure,
        samesite="strict",
        path="/",
    )
    return response


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    """End this session. Always 204, so it can be called without being signed in."""
    sign_out(SqlStaffRepository(session), request.cookies.get(COOKIE_NAME, ""))
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/me", response_model=StaffMe)
def me(staff: CurrentStaff) -> StaffMe:
    """Who is signed in (RatelDesk asks this when it loads)."""
    return _me(staff)
