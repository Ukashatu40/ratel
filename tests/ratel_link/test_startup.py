"""What RatelLink checks and logs at startup. It reports, it never changes anything, and a
database that is not up yet does not stop the service."""

import logging

import pytest
from fastapi.testclient import TestClient

from ratel_link.auth import KeyPolicy, create_system
from ratel_link.config import Settings
from ratel_link.main import create_app
from ratel_link.models import ApiKeyRecord
from tests.ratel_link.fakes import FakeClock, InMemoryApiKeyRepository


def _events(caplog: pytest.LogCaptureFixture, name: str) -> list[dict[str, object]]:
    return [r.__dict__ for r in caplog.records if r.__dict__.get("event") == name]


def test_startup_warns_about_keys_close_to_expiry(caplog: pytest.LogCaptureFixture) -> None:
    repo, clock = InMemoryApiKeyRepository(), FakeClock()
    token = create_system(repo, "bss-app", "RatelBSS", clock(), KeyPolicy())
    clock.advance(days=80)
    caplog.set_level(logging.INFO)
    with TestClient(create_app(Settings(), api_keys=repo, clock=clock)) as client:
        assert client.get("/healthz").status_code == 200
    (event,) = _events(caplog, "api_key.expiring")
    assert (event["api_key_id"], event["api_key_generation"], event["days_left"]) == (
        "bss-app",
        1,
        10,
    )
    assert token not in caplog.text and token.split(".", 1)[1] not in caplog.text


def test_startup_is_quiet_when_nothing_is_close_to_expiry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo, clock = InMemoryApiKeyRepository(), FakeClock()
    create_system(repo, "bss-app", "RatelBSS", clock(), KeyPolicy())
    caplog.set_level(logging.INFO)
    with TestClient(create_app(Settings(), api_keys=repo, clock=clock)):
        pass
    assert _events(caplog, "api_key.expiring") == []
    assert _events(caplog, "startup.checks.failed") == []


def test_a_broken_database_is_logged_by_type_and_does_not_stop_startup(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Down(InMemoryApiKeyRepository):
        def list_all(self) -> list[ApiKeyRecord]:
            raise ConnectionError("mongodb://user:hunter2@127.0.0.1 refused")

    caplog.set_level(logging.INFO)
    with TestClient(create_app(Settings(), api_keys=Down(), clock=FakeClock())) as client:
        assert client.get("/healthz").status_code == 200  # still serving
    (event,) = _events(caplog, "startup.checks.failed")
    assert event["exc_type"] == "ConnectionError"
    assert "hunter2" not in caplog.text


def test_startup_does_not_need_a_database_to_build_the_app() -> None:
    # Building (not starting) the real app must not connect: contract and drift tests rely on it.
    app = create_app(Settings())
    assert app.state.api_keys is not None
