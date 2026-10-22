"""HTTP and contract compliance tests for RatelMeter API."""

from __future__ import annotations

import logging
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.db import Base
from app.main import create_app

TEST_KEY = "unit-test-key-0000000000000000"
AUTH_HEADER = {"Authorization": f"Bearer {TEST_KEY}"}


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    settings = Settings(
        ratel_env="test",
        database_url=SecretStr("sqlite:///:memory:"),
        meter_api_key=SecretStr(TEST_KEY),
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)

    with TestClient(app) as test_client:
        yield test_client


def test_unauthorized_without_key(client: TestClient) -> None:
    res_post = client.post("/v1/usage", json={"records": []})
    assert res_post.status_code == 401
    assert res_post.json()["error"]["code"] == "unauthorized"

    res_get = client.get("/v1/usage?from=1791820800&to=1791821100")
    assert res_get.status_code == 401
    assert res_get.json()["error"]["code"] == "unauthorized"


def test_ingest_and_query_lifecycle(client: TestClient) -> None:
    batch = {
        "records": [
            {
                "imsi": "621000000000001",
                "period_start": 1791820800,
                "period_end": 1791821100,
                "bytes_up": 1048576,
                "bytes_down": 5242880,
            }
        ]
    }

    # Ingest batch
    res_post = client.post(
        "/v1/usage",
        headers={**AUTH_HEADER, "Idempotency-Key": "test-key-1"},
        json=batch,
    )
    assert res_post.status_code == 200
    assert res_post.json() == {}

    # Query usage
    res_get = client.get(
        "/v1/usage?from=1791820800&to=1791821100&imsi=621000000000001",
        headers=AUTH_HEADER,
    )
    assert res_get.status_code == 200
    data = res_get.json()
    assert len(data["records"]) == 1
    assert data["records"][0]["imsi"] == "621000000000001"
    assert data["records"][0]["bytes_up"] == 1048576
    assert data["next_cursor"] is None


def test_replay_overwrites_existing_record(client: TestClient) -> None:
    first_batch = {
        "records": [
            {
                "imsi": "621000000000001",
                "period_start": 1791820800,
                "period_end": 1791821100,
                "bytes_up": 100,
                "bytes_down": 200,
            }
        ]
    }
    client.post("/v1/usage", headers=AUTH_HEADER, json=first_batch)

    # Replay with new byte numbers
    second_batch = {
        "records": [
            {
                "imsi": "621000000000001",
                "period_start": 1791820800,
                "period_end": 1791821100,
                "bytes_up": 500,
                "bytes_down": 600,
            }
        ]
    }
    client.post("/v1/usage", headers=AUTH_HEADER, json=second_batch)

    res = client.get(
        "/v1/usage?from=1791820800&to=1791821100",
        headers=AUTH_HEADER,
    )
    data = res.json()
    assert len(data["records"]) == 1
    assert data["records"][0]["bytes_up"] == 500
    assert data["records"][0]["bytes_down"] == 600


def test_invalid_batch_rejected(client: TestClient) -> None:
    # Negative bytes
    bad_batch = {
        "records": [
            {
                "imsi": "621000000000001",
                "period_start": 1791820800,
                "period_end": 1791821100,
                "bytes_up": -10,
                "bytes_down": 200,
            }
        ]
    }
    res = client.post("/v1/usage", headers=AUTH_HEADER, json=bad_batch)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


def test_no_imsi_in_logs(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    """M-11 / M-12 acceptance criterion: No IMSI in operational logs."""
    test_imsi = "621000000000001"
    batch = {
        "records": [
            {
                "imsi": test_imsi,
                "period_start": 1791820800,
                "period_end": 1791821100,
                "bytes_up": 100,
                "bytes_down": 200,
            }
        ]
    }

    with caplog.at_level(logging.DEBUG):
        client.post("/v1/usage", headers=AUTH_HEADER, json=batch)
        client.get(
            f"/v1/usage?from=1791820800&to=1791821100&imsi={test_imsi}",
            headers=AUTH_HEADER,
        )

    for record in caplog.records:
        if record.name.startswith("ratel."):
            assert test_imsi not in record.message


def _app_client(**settings: object) -> TestClient:
    app = create_app(
        Settings(ratel_env="test", database_url=SecretStr("sqlite:///:memory:"), **settings)  # type: ignore[arg-type]
    )
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


@pytest.mark.parametrize("token", ["test-only-not-a-real-key", "test", "", "CHANGE_ME", "anything"])
def test_with_no_key_configured_nothing_gets_in(token: str) -> None:
    # No built-in or "test" keys: an unconfigured API refuses every caller.
    client = _app_client()
    assert (
        client.get(
            "/v1/usage?from=1&to=2", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/v1/usage", json={"records": []}, headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("configured", ["", "   ", "CHANGE_ME"])
def test_an_empty_or_placeholder_key_counts_as_not_configured(configured: str) -> None:
    client = _app_client(meter_api_key=SecretStr(configured))
    for token in (configured.strip() or "x", "CHANGE_ME"):
        res = client.get("/v1/usage?from=1&to=2", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401


def test_only_the_configured_key_is_accepted() -> None:
    client = _app_client(meter_api_key=SecretStr(TEST_KEY))
    ok = client.get("/v1/usage?from=1&to=2", headers=AUTH_HEADER)
    assert ok.status_code == 200
    for wrong in ("test", "test-only-not-a-real-key", TEST_KEY + "x", TEST_KEY[:-1]):
        bad = client.get("/v1/usage?from=1&to=2", headers={"Authorization": f"Bearer {wrong}"})
        assert bad.status_code == 401


def test_a_token_with_non_ascii_characters_is_a_401_not_a_crash() -> None:
    client = _app_client(meter_api_key=SecretStr(TEST_KEY))
    res = client.get(
        "/v1/usage?from=1&to=2", headers={"Authorization": "Bearer caf\u00e9".encode("latin-1")}
    )
    assert res.status_code == 401


@pytest.mark.parametrize("env", ["lab", "staging", "production"])
def test_a_deployed_app_without_a_key_refuses_to_start(env: str) -> None:
    with pytest.raises(RuntimeError, match="METER_API_KEY"):
        create_app(Settings(ratel_env=env, database_url=SecretStr("sqlite:///:memory:")))  # type: ignore[arg-type]


@pytest.mark.parametrize("env", ["lab", "staging", "production"])
def test_a_deployed_app_with_a_key_starts(env: str) -> None:
    app = create_app(
        Settings(
            ratel_env=env,  # type: ignore[arg-type]
            database_url=SecretStr("sqlite:///:memory:"),
            meter_api_key=SecretStr(TEST_KEY),
        )
    )
    assert app is not None


def test_the_same_interval_twice_in_one_batch_is_accepted_and_the_last_one_kept(
    client: TestClient,
) -> None:
    rec = {
        "imsi": "621000000000001",
        "period_start": 1791820800,
        "period_end": 1791821100,
        "bytes_up": 1,
        "bytes_down": 2,
    }
    batch = {"records": [rec, {**rec, "bytes_up": 7, "bytes_down": 8}]}
    res = client.post("/v1/usage", json=batch, headers={**AUTH_HEADER, "Idempotency-Key": "dup-1"})
    assert res.status_code == 200
    got = client.get("/v1/usage?from=1791820800&to=1791821100", headers=AUTH_HEADER).json()
    assert [(r["bytes_up"], r["bytes_down"]) for r in got["records"]] == [(7, 8)]
