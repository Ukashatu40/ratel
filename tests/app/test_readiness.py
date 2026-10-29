"""`/readyz`: ready only when the app can do its job, and it never says why."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import readiness
from app.config import Settings
from app.db import Base
from app.main import create_app

KEY = "test-key-not-a-real-key"


class FakeRedis:
    def __init__(self, answer: object = True) -> None:
        self.answer = answer

    def ping(self) -> object:
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture(autouse=True)
def _migrated(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unit tests build tables directly, so they stand in for "the database is at head"."""
    monkeypatch.setattr(readiness, "migrations_current", lambda engine: True)


def make(tmp_path: Path, **settings: object) -> TestClient:
    app = create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'r.db'}", **settings)  # type: ignore[arg-type]
    )
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


def deployed(tmp_path: Path, **changes: object) -> TestClient:
    """An app as a server runs it (not local or test): keys set, Redis answering."""
    settings = {
        "ratel_env": "lab",
        "meter_api_key": KEY,
        "pay_api_key": KEY,
        "ratel_link_api_key": KEY,
    } | changes
    client = make(tmp_path, **settings)
    client.app.state.redis = FakeRedis()  # type: ignore[attr-defined]
    return client


def test_a_local_app_with_a_working_database_is_ready(tmp_path: Path) -> None:
    response = make(tmp_path).get("/readyz")
    assert (response.status_code, response.json()) == (200, {"status": "ready"})
    assert response.headers["cache-control"] == "no-store"


def test_a_deployed_app_with_everything_in_place_is_ready(tmp_path: Path) -> None:
    assert deployed(tmp_path).get("/readyz").status_code == 200


def test_readiness_needs_no_sign_in_and_liveness_is_separate(tmp_path: Path) -> None:
    client = deployed(tmp_path)
    client.app.state.redis = FakeRedis(ConnectionError("down"))  # type: ignore[attr-defined]
    assert client.get("/readyz").status_code == 503
    assert client.get("/healthz").status_code == 200  # the process is up; it is not ready


def test_no_database_means_not_ready(tmp_path: Path) -> None:
    client = make(tmp_path)
    client.app.state.engine = create_engine("sqlite:////nonexistent-dir/x.db")  # type: ignore[attr-defined]
    assert client.get("/readyz").status_code == 503


def test_a_database_behind_the_code_means_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(readiness, "migrations_current", lambda engine: False)
    assert make(tmp_path).get("/readyz").status_code == 503


@pytest.mark.parametrize("answer", [False, ConnectionError("down")])
def test_redis_not_answering_means_not_ready(tmp_path: Path, answer: object) -> None:
    client = deployed(tmp_path)
    client.app.state.redis = FakeRedis(answer)  # type: ignore[attr-defined]
    assert client.get("/readyz").status_code == 503


def test_a_deployed_app_without_the_ratellink_key_is_not_ready(tmp_path: Path) -> None:
    assert deployed(tmp_path, ratel_link_api_key=None).get("/readyz").status_code == 503
    assert deployed(tmp_path, ratel_link_api_key="  ").get("/readyz").status_code == 503


def test_the_answer_never_says_why_and_the_log_names_only_the_component(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = deployed(tmp_path)
    client.app.state.redis = FakeRedis(ConnectionError("secret-host-10.0.0.9 refused"))  # type: ignore[attr-defined]
    with caplog.at_level(logging.ERROR):
        response = client.get("/readyz")
    assert response.json() == {"status": "unavailable"}
    logged = " ".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "readiness.failed" in logged
    assert "redis" in logged
    assert "secret-host" not in logged
    assert "10.0.0.9" not in logged
    assert "ConnectionError" in logged  # the type, which names no host


def test_every_check_runs_even_when_one_fails(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = deployed(tmp_path, ratel_link_api_key=None)
    client.app.state.redis = FakeRedis(False)  # type: ignore[attr-defined]
    with caplog.at_level(logging.ERROR):
        client.get("/readyz")
    logged = " ".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "redis" in logged and "ratel_link_key" in logged
