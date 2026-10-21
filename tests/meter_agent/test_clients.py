"""Unit tests for AssignmentCache client and MeterPoster client (M-08)."""

from __future__ import annotations

import logging

import httpx
import pytest
from pydantic import SecretStr

from services.meter_agent.assignments import HttpAssignmentCache
from services.meter_agent.ingest import HttpMeterPoster


def test_assignment_cache_success_and_refresh() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers.get("authorization") == "Bearer secret-token-123"
        return httpx.Response(
            200,
            json={
                "assignments": [
                    {"ue_ip": "10.45.0.2", "imsi": "621000000000001"},
                    {"ue_ip": "10.45.0.3", "imsi": "621000000000002"},
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    cache = HttpAssignmentCache(
        base_url="http://fake-link",
        api_key=SecretStr("secret-token-123"),
        client=client,
    )

    cache.refresh()
    assert calls == 1
    assert cache.imsi_for("10.45.0.2") == "621000000000001"
    assert cache.imsi_for("10.45.0.3") == "621000000000002"
    assert cache.imsi_for("10.45.0.99") is None


def test_assignment_cache_failure_keeps_old_mapping_and_never_raises() -> None:
    status = 200

    def handler(request: httpx.Request) -> httpx.Response:
        if status == 200:
            return httpx.Response(
                200,
                json={"assignments": [{"ue_ip": "10.45.0.2", "imsi": "621000000000001"}]},
            )
        if status == 401:
            return httpx.Response(401, json={"error": "unauthorized"})
        if status == 500:
            return httpx.Response(500, text="Internal Server Error")
        if status == 422:
            return httpx.Response(200, json="malformed not a dict")
        raise httpx.ConnectTimeout("connection timed out")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    cache = HttpAssignmentCache(
        base_url="http://fake-link",
        api_key="secret-token-123",
        client=client,
    )

    # Initial successful refresh
    cache.refresh()
    assert cache.imsi_for("10.45.0.2") == "621000000000001"

    # 401 Unauthorized: does not raise, keeps old mapping
    status = 401
    cache.refresh()
    assert cache.imsi_for("10.45.0.2") == "621000000000001"

    # 500 Server Error: does not raise, keeps old mapping
    status = 500
    cache.refresh()
    assert cache.imsi_for("10.45.0.2") == "621000000000001"

    # Malformed body: does not raise, keeps old mapping
    status = 422
    cache.refresh()
    assert cache.imsi_for("10.45.0.2") == "621000000000001"

    # Network timeout: does not raise, keeps old mapping
    status = 999
    cache.refresh()
    assert cache.imsi_for("10.45.0.2") == "621000000000001"


def test_assignment_cache_logs_no_keys_or_addresses(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"assignments": [{"ue_ip": "10.45.0.2", "imsi": "621000000000001"}]},
        )

    caplog.set_level(logging.DEBUG)
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    cache = HttpAssignmentCache(
        base_url="http://fake-link",
        api_key=SecretStr("super-secret-key-xyz"),
        client=client,
    )
    cache.refresh()

    for record in caplog.records:
        msg = record.getMessage()
        assert "super-secret-key-xyz" not in msg
        assert "10.45.0.2" not in msg
        assert "621000000000001" not in msg


def test_meter_poster_success() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers.get("authorization") == "Bearer poster-secret-key"
        assert "Idempotency-Key" in request.headers
        assert request.url.path == "/v1/usage"
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    poster = HttpMeterPoster(
        base_url="http://fake-meter-api",
        api_key=SecretStr("poster-secret-key"),
        client=client,
    )

    batch = [
        {
            "imsi": "621000000000001",
            "period_start": 1791820800,
            "period_end": 1791821100,
            "bytes_up": 1000,
            "bytes_down": 2000,
        }
    ]
    assert poster(batch) is True
    assert calls == 1


def test_meter_poster_failures_return_false_and_never_raise() -> None:
    status = 401

    def handler(request: httpx.Request) -> httpx.Response:
        if status == 401:
            return httpx.Response(401, json={"error": "unauthorized"})
        if status == 422:
            return httpx.Response(422, json={"error": "validation_error"})
        if status == 500:
            return httpx.Response(500, text="Internal Server Error")
        raise httpx.ConnectTimeout("connection timed out")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    poster = HttpMeterPoster(
        base_url="http://fake-meter-api",
        api_key=SecretStr("poster-secret-key"),
        client=client,
    )

    batch = [
        {
            "imsi": "621000000000001",
            "period_start": 1791820800,
            "period_end": 1791821100,
            "bytes_up": 100,
            "bytes_down": 200,
        }
    ]

    # 401
    assert poster(batch) is False
    # 422
    status = 422
    assert poster(batch) is False
    # 500
    status = 500
    assert poster(batch) is False
    # Timeout
    status = 999
    assert poster(batch) is False


def test_meter_poster_logs_no_keys_or_imsis(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    caplog.set_level(logging.DEBUG)
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    poster = HttpMeterPoster(
        base_url="http://fake-meter-api",
        api_key=SecretStr("super-secret-poster-token"),
        client=client,
    )
    batch = [
        {
            "imsi": "621000000000001",
            "period_start": 1791820800,
            "period_end": 1791821100,
            "bytes_up": 100,
            "bytes_down": 200,
        }
    ]
    poster(batch)

    for record in caplog.records:
        msg = record.getMessage()
        assert "super-secret-poster-token" not in msg
        assert "621000000000001" not in msg
