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

TEST_KEY = "test-only-not-a-real-key"
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
