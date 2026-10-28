"""Helpers for tests that call RatelDesk's routes as a signed-in staff member."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.bss_lines.api.deps import CSRF_HEADER
from app.bss_lines.repositories.desk_sql import SqlStaffRepository
from app.bss_lines.services.staff_auth import create_staff
from app.config import Settings
from app.main import create_app

PASSWORD = "a fine long test password"  # synthetic: belongs to no real account


def make_app(
    factory: sessionmaker[Session], clock: Callable[[], datetime] | None = None
) -> FastAPI:
    app = create_app(Settings(staff_cookie_secure=False))
    app.state.session_factory = factory
    if clock is not None:
        app.state.clock = clock
    return app


def add_staff(factory: sessionmaker[Session], role: str = "agent", email: str | None = None) -> str:
    """A staff account with a known password. Returns its email."""
    email = email or f"{role}@example.test"
    with factory() as session, session.begin():
        create_staff(
            SqlStaffRepository(session),
            email=email,
            name=f"Test {role}",
            role=role,
            password=PASSWORD,
        )
    return email


def signed_in(app: FastAPI, email: str) -> TestClient:
    """A client with the session cookie and the header every changing request needs."""
    client = TestClient(app)
    client.headers[CSRF_HEADER] = "1"
    response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)
