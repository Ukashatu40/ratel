"""Tests for the RatelLinkClient: request shape, headers, status handling."""

from __future__ import annotations

import json

import pytest

from app.bss_lines.client import RatelLinkClient, RatelLinkError


def test_activate_sends_expected_body_and_headers(httpx_mock) -> None:
    httpx_mock.add_response(
        url="http://mock/v1/lines/621000000000001/activate",
        method="POST",
        status_code=200,
        json={},
    )
    client = RatelLinkClient("http://mock", "test-key")
    client.activate(
        "621000000000001",
        msisdn="2348000000001",
        speed_ul_mbps=10,
        speed_dl_mbps=20,
        voice=True,
        idempotency_key="key-1",
    )
    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.headers["Idempotency-Key"] == "key-1"
    body = json.loads(request.read())
    assert body == {
        "msisdn": "2348000000001",
        "speed_ul_mbps": 10,
        "speed_dl_mbps": 20,
        "voice": True,
    }


@pytest.mark.parametrize("status", [401, 404, 422, 503])
def test_activate_raises_on_known_errors(httpx_mock, status: int) -> None:
    httpx_mock.add_response(status_code=status)
    client = RatelLinkClient("http://mock", "test-key")
    with pytest.raises(RatelLinkError) as exc:
        client.activate(
            "621000000000001",
            msisdn="2348000000001",
            speed_ul_mbps=10,
            speed_dl_mbps=20,
            voice=True,
            idempotency_key="k",
        )
    assert exc.value.status == status


def test_activate_raises_on_unexpected_status(httpx_mock) -> None:
    httpx_mock.add_response(status_code=500)
    client = RatelLinkClient("http://mock", "test-key")
    with pytest.raises(RatelLinkError) as exc:
        client.activate(
            "621000000000001",
            msisdn="2348000000001",
            speed_ul_mbps=10,
            speed_dl_mbps=20,
            voice=True,
            idempotency_key="k",
        )
    assert exc.value.status == 500
