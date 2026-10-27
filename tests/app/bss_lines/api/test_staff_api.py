"""Sign-in over HTTP: the cookie, the refusals, the header against forged requests, sign-out."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bss_lines.api.deps import CSRF_HEADER
from app.bss_lines.domain.staff import COOKIE_NAME, MAX_FAILED_LOGINS, SESSION_IDLE_LIMIT
from app.db import Base
from tests.app.bss_lines.desk_helpers import PASSWORD, add_staff, make_app, signed_in, utc

T0 = utc(2026, 11, 2, 9, 0)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self):  # type: ignore[no-untyped-def]
        return self.now


@pytest.fixture(autouse=True)
def _cheap_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("common.passwords._N", 2**10)


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def app(factory: sessionmaker[Session], clock: Clock) -> FastAPI:
    return make_app(factory, clock)


def _login(client: TestClient, email: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/v1/auth/login", json={"email": email, "password": password})


def test_login_sets_a_cookie_script_cannot_read_and_says_who_signed_in(
    app: FastAPI, factory: sessionmaker[Session]
) -> None:
    email = add_staff(factory, "admin")
    response = _login(TestClient(app), email)
    assert response.status_code == 200
    assert response.json() == {
        "staff_id": 1,
        "email": email,
        "name": "Test admin",
        "role": "admin",
    }
    cookie = response.headers["set-cookie"].lower()
    assert f"{COOKIE_NAME}=" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert "max-age=28800" in cookie and "path=/" in cookie
    assert response.headers["cache-control"] == "no-store"
    assert "password" not in response.text.lower()


def test_the_cookie_is_secure_unless_the_settings_say_otherwise(
    factory: sessionmaker[Session],
) -> None:
    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings())  # the default
    app.state.session_factory = factory
    email = add_staff(factory)
    assert "secure" in _login(TestClient(app), email).headers["set-cookie"].lower()


def test_every_refusal_is_the_same_401_with_no_cookie(
    app: FastAPI, factory: sessionmaker[Session]
) -> None:
    email = add_staff(factory)
    client = TestClient(app)
    answers = {
        (
            r.status_code,
            r.text,
            "set-cookie" in r.headers,
        )
        for r in (
            _login(client, email, "wrong password entirely"),
            _login(client, "nobody@example.test"),
            _login(client, "not an email"),
        )
    }
    assert len(answers) == 1
    status, body, cookie_set = answers.pop()
    assert status == 401 and not cookie_set
    assert "wrong password" not in body and email not in body


def test_a_locked_account_refuses_even_the_right_password(
    app: FastAPI, factory: sessionmaker[Session]
) -> None:
    email = add_staff(factory)
    client = TestClient(app)
    for _ in range(MAX_FAILED_LOGINS):
        assert _login(client, email, "wrong password entirely").status_code == 401
    assert _login(client, email).status_code == 401


def test_the_body_is_checked(app: FastAPI) -> None:
    client = TestClient(app)
    for body in ({}, {"email": "a@b.cd"}, {"email": "a@b.cd", "password": ""}, {"x": 1}):
        assert client.post("/v1/auth/login", json=body).status_code == 422


def test_me_tells_a_signed_in_member_who_they_are_and_nobody_else_anything(
    app: FastAPI, factory: sessionmaker[Session]
) -> None:
    assert TestClient(app).get("/v1/auth/me").status_code == 401
    email = add_staff(factory)
    me = signed_in(app, email).get("/v1/auth/me")
    assert me.status_code == 200 and me.json()["email"] == email
    assert me.headers["cache-control"] == "no-store"


def test_a_401_asks_for_a_cookie_not_a_bearer_key(app: FastAPI) -> None:
    response = TestClient(app).get("/v1/auth/me")
    assert response.headers["www-authenticate"] == "Cookie"
    assert response.json()["error"]["code"] == "unauthorized"


def test_a_bearer_api_key_does_not_open_a_staff_route(
    factory: sessionmaker[Session],
) -> None:
    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(meter_api_key="meter-key-value", pay_api_key="pay-key-value"))
    app.state.session_factory = factory
    client = TestClient(app)
    for key in ("meter-key-value", "pay-key-value"):
        response = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {key}"})
        assert response.status_code == 401


def test_a_changing_request_needs_the_header_a_forged_page_cannot_add(
    app: FastAPI, factory: sessionmaker[Session]
) -> None:
    email = add_staff(factory)
    client = signed_in(app, email)
    del client.headers[CSRF_HEADER]
    # a read does not need it
    assert client.get("/v1/auth/me").status_code == 200
    # a change does, even with a valid cookie
    forged = client.post("/v1/customers", json={})
    assert forged.status_code == 403 and forged.json()["error"]["code"] == "forbidden"
    client.headers[CSRF_HEADER] = "1"
    assert client.post("/v1/customers", json={}).status_code == 422  # past the gate


def test_logout_ends_the_session_everywhere_and_is_harmless_without_one(
    app: FastAPI, factory: sessionmaker[Session]
) -> None:
    email = add_staff(factory)
    client = signed_in(app, email)
    stolen_cookie = client.cookies.get(COOKIE_NAME)
    assert client.post("/v1/auth/logout").status_code == 204
    assert client.get("/v1/auth/me").status_code == 401
    # a copy of the old cookie is dead too: the session is gone on the server, not only the browser
    other = TestClient(app)
    other.cookies.set(COOKIE_NAME, stolen_cookie)
    assert other.get("/v1/auth/me").status_code == 401
    assert TestClient(app).post("/v1/auth/logout").status_code == 204


def test_a_session_goes_stale_with_the_clock(
    app: FastAPI, factory: sessionmaker[Session], clock: Clock
) -> None:
    email = add_staff(factory)
    client = signed_in(app, email)
    clock.now = T0 + SESSION_IDLE_LIMIT + timedelta(seconds=1)
    assert client.get("/v1/auth/me").status_code == 401


def test_a_disabled_member_is_signed_out_at_once(
    app: FastAPI, factory: sessionmaker[Session]
) -> None:
    from app.bss_lines.repositories.desk_sql import SqlStaffRepository
    from app.bss_lines.services.staff_auth import set_active

    email = add_staff(factory)
    client = signed_in(app, email)
    with factory() as session, session.begin():
        set_active(SqlStaffRepository(session), email, False)
    assert client.get("/v1/auth/me").status_code == 401
