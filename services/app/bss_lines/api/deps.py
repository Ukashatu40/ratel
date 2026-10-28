"""What the RatelBSS routes for staff share: the database session, and who is calling.

`current_staff` is the one place a staff request is authenticated. It reads the session cookie,
checks it, and gives the route the signed-in staff member, so the audit trail names a real person
taken from the server's own record and never from the request body.

Two protections beyond the cookie being `HttpOnly`, `Secure` and `SameSite=Strict`:
- every request that changes something must carry the header `X-Ratel-Desk`. A page on another
  site cannot add a custom header without the browser asking this server first (and this server
  answers no), so a forged form or image request is refused even from a browser that ignores
  `SameSite`;
- an answer to a signed-in staff member is marked `Cache-Control: no-store`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.bss_lines.domain.staff import COOKIE_NAME, Permission, Role, may
from app.bss_lines.repositories.desk_ports import StaffRecord
from app.bss_lines.repositories.desk_sql import SqlStaffRepository
from app.bss_lines.services.staff_auth import authenticate
from app.config import Settings
from common.errors import ApiError

CSRF_HEADER = "x-ratel-desk"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_db(request: Request) -> Iterator[Session]:
    """Provide a database session for the duration of the request."""
    factory = request.app.state.session_factory

    with factory() as session, session.begin():
        yield session


def get_settings(request: Request) -> Settings:
    """The settings the app was created with."""
    return cast(Settings, request.app.state.settings)


def now_utc(request: Request) -> datetime:
    """The time for this request. Tests set `app.state.clock`; they never sleep."""
    clock: Callable[[], datetime] | None = getattr(request.app.state, "clock", None)
    return clock() if clock is not None else datetime.now(UTC)


def _unauthorized() -> ApiError:
    return ApiError(
        401,
        "unauthorized",
        "Sign in to use this.",
        headers={"WWW-Authenticate": "Cookie"},
    )


def current_staff(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
) -> StaffRecord:
    """The signed-in staff member, or 401. Checked before anything else the route does."""
    response.headers["Cache-Control"] = "no-store"
    token = request.cookies.get(COOKIE_NAME, "")
    staff = authenticate(SqlStaffRepository(session), token, now_utc(request))
    if staff is None:
        raise _unauthorized()
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) is None:
        raise ApiError(403, "forbidden", f"The {CSRF_HEADER} header is required.")
    return staff


CurrentStaff = Annotated[StaffRecord, Depends(current_staff)]


def require(permission: Permission) -> Callable[[StaffRecord], StaffRecord]:
    """A dependency that lets through only staff whose role holds `permission`."""

    def check(staff: CurrentStaff) -> StaffRecord:
        if not may(Role(staff.role), permission):
            raise ApiError(403, "forbidden", "Your role may not do this.")
        return staff

    return check
